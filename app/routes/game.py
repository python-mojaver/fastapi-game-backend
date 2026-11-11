from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pika.exceptions import AMQPError
from sqlalchemy.orm import Session

from database import SessionLocal
from leaderboard_data import leaderboard_rows
from leaderboard_export import LeaderboardExport, enqueue_export, export_path
from models import User
from routes.auth import get_current_user_from_token
from redis_client import get_redis

router = APIRouter(prefix="/game")

LEVELS = {
    1:  {"coins": 5000,      "profit": 1500,  "max_energy": 1000,  "click_value": 1},
    2:  {"coins": 2500000,   "profit": 3000,  "max_energy": 2000,  "click_value": 2},
    3:  {"coins": 6000000,   "profit": 3500,  "max_energy": 3000,  "click_value": 3},
    4:  {"coins": 11250000,  "profit": 5000,  "max_energy": 4000,  "click_value": 4},
    5:  {"coins": 19125000,  "profit": 7500,  "max_energy": 5000,  "click_value": 5},
    6:  {"coins": 31000000,  "profit": 10500, "max_energy": 6000,  "click_value": 6},
    7:  {"coins": 49000000,  "profit": 15000, "max_energy": 7000,  "click_value": 7},
    8:  {"coins": 76000000,  "profit": 20000, "max_energy": 8000,  "click_value": 8},
    9:  {"coins": 116500000, "profit": 25000, "max_energy": 9000,  "click_value": 9},
    10: {"coins": 150000000, "profit": 40000, "max_energy": 10000, "click_value": 10},
}

LEVEL_UP_MESSAGES = {
    2: "به مرحله دوم وارد شدید.",
    3: "به مرحله سوم وارد شدید.",
    4: "به مرحله چهارم وارد شدید.",
    5: "به مرحله پنجم وارد شدید.",
    6: "به مرحله ششم وارد شدید.",
    7: "به مرحله هفتم وارد شدید.",
    8: "به مرحله هشتم وارد شدید.",
    9: "به مرحله نهم وارد شدید.",
    10: "به مرحله دهم وارد شدید.",
}

MAX_LEVEL = 10
REGEN_TIME = 108
REGEN_AMOUNT = 10


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def calculate_level(coins: int) -> int:
    current_level = 1
    for lvl in range(1, MAX_LEVEL + 1):
        if coins >= LEVELS[lvl]["coins"]:
            current_level = lvl
        else:
            break
    return current_level


def check_level_up(user, db: Session):
    new_level = calculate_level(user.coins)
    level_up_message = None
    if user.level != new_level:
        level_up_message = LEVEL_UP_MESSAGES.get(new_level)
        user.level = new_level
        level_data = LEVELS[new_level]
        user.profit_per_hour = level_data["profit"]
        new_max = level_data["max_energy"]
        user.max_energy = new_max
        if user.energy > new_max:
            user.energy = new_max
    return level_up_message


# ============================================================
# RATE LIMITING - با Redis (جایگزین RAM دیکشنری)
# ============================================================
def check_rate_limit(user_id: int, max_clicks: int = 60, time_window: int = 5):
    r = get_redis()
    key = f"click_rate:{user_id}"
    try:
        pipe = r.pipeline()
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - time_window
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, time_window + 1)
        results = pipe.execute()
        click_count = results[1]
        if click_count >= max_clicks:
            raise HTTPException(429, detail=f"Too many clicks! Wait {time_window}s.")
    except HTTPException:
        raise
    except Exception:
        pass  # اگر Redis در دسترس نبود، ادامه بده


def update_energy(user: User, db: Session):
    now = datetime.now(timezone.utc)
    if user.last_energy_update is None:
        user.last_energy_update = now
        db.commit()
        return
    if user.last_energy_update.tzinfo is None:
        user.last_energy_update = user.last_energy_update.replace(tzinfo=timezone.utc)
    if user.last_energy_update > now:
        user.last_energy_update = now
        db.commit()
        return
    seconds_passed = int((now - user.last_energy_update).total_seconds())
    if seconds_passed >= 10800:
        user.energy = user.max_energy
        user.last_energy_update = now
        db.commit()
        return
    regen_count = seconds_passed // REGEN_TIME
    if regen_count > 0:
        added = regen_count * REGEN_AMOUNT
        user.energy = min(user.max_energy, user.energy + added)
        user.last_energy_update += timedelta(seconds=regen_count * REGEN_TIME)
        db.commit()


def check_daily_reset(user: User, db: Session):
    now = datetime.now(timezone.utc)
    if user.last_daily_reset is None:
        user.last_daily_reset = now
        user.daily_clicks = 0
        db.commit()
        return
    if user.last_daily_reset.tzinfo is None:
        user.last_daily_reset = user.last_daily_reset.replace(tzinfo=timezone.utc)
    if user.last_daily_reset.date() < now.date():
        user.daily_clicks = 0
        user.last_daily_reset = now
        db.commit()


# ============================================================
# GET /game/me
# ============================================================
@router.get("/me")
def get_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "User not found")

    update_energy(user, db)
    check_daily_reset(user, db)

    now = datetime.now(timezone.utc)
    seconds_until_next = REGEN_TIME
    if user.last_energy_update and user.energy < user.max_energy:
        if user.last_energy_update.tzinfo is None:
            user.last_energy_update = user.last_energy_update.replace(tzinfo=timezone.utc)
        seconds_passed = int((now - user.last_energy_update).total_seconds())
        seconds_until_next = max(1, REGEN_TIME - (seconds_passed % REGEN_TIME))

    current_level = calculate_level(user.coins)
    if user.level != current_level:
        level_data = LEVELS[current_level]
        user.level = current_level
        user.profit_per_hour = level_data["profit"]
        user.max_energy = level_data["max_energy"]
        db.commit()

    current_level_data = LEVELS.get(current_level, {})
    next_level_num = current_level + 1
    current_level_coins = current_level_data.get("coins", 0)
    next_level_coins = LEVELS.get(next_level_num, {}).get("coins", None)
    click_value = current_level_data.get("click_value", 1)
    profit_unlocked = (user.referral_count or 0) >= 2
    current_profit = current_level_data.get("profit", 1500) if profit_unlocked else 0

    if next_level_coins is not None:
        coins_above = max(0, user.coins - current_level_coins)
        coins_range = next_level_coins - current_level_coins
        progress_percent = min(100, int((coins_above / coins_range) * 100))
        level_progress = round(coins_above / coins_range, 4)
        coins_to_next = max(0, next_level_coins - user.coins)
    else:
        progress_percent = 100
        level_progress = 1.0
        coins_to_next = 0

    return {
        "status": "success",
        "user_id": user.id,
        "id": user.id,
        "username": user.username,
        "coins": round(user.coins, 2),
        "level": current_level,
        "click_value": click_value,
        "xp": user.xp,
        "energy": user.energy,
        "max_energy": user.max_energy,
        "profit_per_hour": user.profit_per_hour,
        "profit": current_profit,
        "profit_unlocked": profit_unlocked,
        "referral_count": user.referral_count or 0,
        "daily_clicks": user.daily_clicks or 0,
        "daily_clicks_limit": 5000,
        "seconds_until_next_energy": seconds_until_next,
        "regen_amount": REGEN_AMOUNT,
        "regen_time": REGEN_TIME,
        "last_energy_update": user.last_energy_update.isoformat() if user.last_energy_update else None,
        "current_level_xp": current_level_coins,
        "next_level_xp": next_level_coins,
        "current_level_coins": current_level_coins,
        "next_level_coins": next_level_coins,
        "progress_percent": progress_percent,
        "level_progress": level_progress,
        "coins_to_next_level": coins_to_next,
    }


# ============================================================
# POST /game/click
# هر کلیک = click_value سکه + click_value انرژی کم میشه
# مثال: لول 8 → click_value=8 → 8 سکه + 8 انرژی کم
# ============================================================
@router.post("/click")
def click(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "User not found")

    check_rate_limit(user.id)
    check_daily_reset(user, db)
    update_energy(user, db)

    if user.daily_clicks >= 5000:
        raise HTTPException(429, "Daily limit reached!")

    level_data = LEVELS.get(user.level, {})
    click_value = level_data.get("click_value", 1)
    energy_cost = click_value  # لول 8 = 8 انرژی کم میشه

    if user.energy < energy_cost:
        raise HTTPException(400, "انرژی کافی نیست!")

    user.energy -= energy_cost
    user.coins += click_value
    user.daily_clicks = (user.daily_clicks or 0) + 1

    level_up_msg = check_level_up(user, db)
    db.commit()

    response = {
        "coins": round(user.coins, 2),
        "energy": user.energy,
        "max_energy": user.max_energy,
        "level": user.level,
        "click_value": click_value,
        "profit_per_hour": user.profit_per_hour,
    }
    if level_up_msg:
        response["level_up_message"] = level_up_msg
    return response


# ============================================================
# POST /game/auto-click
# cooldown با Redis (جایگزین last_auto_click دیکشنری)
# ============================================================
@router.post("/auto-click")
def auto_click(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "کاربر پیدا نشد")

    update_energy(user, db)

    AUTO_CLICK_ENERGY = 50
    AUTO_CLICK_COOLDOWN = 10
    AUTO_CLICK_REWARD = 50

    #  Redis cooldown (جایگزین last_auto_click RAM)
    r = get_redis()
    cooldown_key = f"auto_click:{user.id}"
    try:
        ttl = r.ttl(cooldown_key)
        if ttl > 0:
            raise HTTPException(429, f"لطفاً {ttl} ثانیه صبر کنید")
        r.setex(cooldown_key, AUTO_CLICK_COOLDOWN, "1")
    except HTTPException:
        raise
    except Exception:
        pass

    if user.energy < AUTO_CLICK_ENERGY:
        raise HTTPException(400, "انرژی کافی برای اتوکلیک ندارید")

    user.energy -= AUTO_CLICK_ENERGY
    user.coins += AUTO_CLICK_REWARD
    level_up_msg = check_level_up(user, db)
    db.commit()

    response = {
        "success": True,
        "message": f"تبریک {AUTO_CLICK_REWARD} سکه از طریق کلیک خودکار کسب کردید",
        "reward": AUTO_CLICK_REWARD,
        "energy_used": AUTO_CLICK_ENERGY,
        "remaining_energy": user.energy,
        "total_coins": round(user.coins, 2),
        "cooldown": AUTO_CLICK_COOLDOWN,
    }
    if level_up_msg:
        response["level_up_message"] = level_up_msg
    return response


# ============================================================
# POST /game/collect-profit
# ============================================================
@router.post("/collect-profit")
def collect_profit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "User not found")

    now = datetime.now(timezone.utc)
    if user.last_profit_collect:
        if user.last_profit_collect.tzinfo is None:
            user.last_profit_collect = user.last_profit_collect.replace(tzinfo=timezone.utc)
        hours_passed = min(3.0, (now - user.last_profit_collect).total_seconds() / 3600)
        profit_to_add = int(user.profit_per_hour * hours_passed)
    else:
        profit_to_add = 0
        user.last_profit_collect = now

    if profit_to_add > 0:
        user.coins += profit_to_add
        user.last_profit_collect = now
        db.commit()

    return {
        "collected_profit": profit_to_add,
        "total_coins": round(user.coins, 2),
        "profit_per_hour": user.profit_per_hour,
    }


# ============================================================
# جدول رتبه‌بندی
# ============================================================
@router.get("/leaderboard")
def get_leaderboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
    limit: int = 100
):
    result = leaderboard_rows(db, current_user.id, limit)
    user_rank = db.query(User).filter(
        User.coins > current_user.coins, User.is_active == True
    ).count() + 1
    return {
        "leaderboard": result,
        "current_user_rank": user_rank,
        "current_user_coins": round(current_user.coins, 2)
    }


@router.post("/leaderboard/exports", status_code=202, tags=["Leaderboard exports"])
def request_leaderboard_export(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user_from_token),
):
    job = LeaderboardExport(job_id=uuid4(), user_id=current_user.id)
    try:
        enqueue_export(job)
    except AMQPError as error:
        raise HTTPException(503, "Could not confirm the export request with RabbitMQ") from error

    download_url = request.url_for("download_leaderboard_export", job_id=str(job.job_id)).path
    # پاسخ ۲۰۲ یعنی درخواست وارد صف شده و فایل در آدرس اعلام‌شده قابل پیگیری است.
    response.headers["Location"] = download_url
    return {"job_id": job.job_id, "download_url": download_url}


@router.get("/leaderboard/exports/{job_id}", tags=["Leaderboard exports"])
def download_leaderboard_export(
    job_id: UUID,
    current_user: User = Depends(get_current_user_from_token),
):
    path = export_path(LeaderboardExport(job_id=job_id, user_id=current_user.id))
    if not path.is_file():
        raise HTTPException(404, "Export is not ready or does not exist")
    return FileResponse(path, media_type="text/csv", filename="leaderboard.csv")
