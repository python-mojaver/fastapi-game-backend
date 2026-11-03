from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from database import get_db
from models import User
from routes.auth import get_current_user_from_token, security

router = APIRouter(
    prefix="/daily",
    tags=["Daily Reward"]
)

# ==========================================
# DAILY REWARDS (30 روز)
# ==========================================
DAILY_REWARDS = {
    1: 10000, 2: 20000, 3: 30000, 4: 40000, 5: 50000,
    6: 60000, 7: 80000, 8: 90000, 9: 100000, 10: 110000,
    11: 120000, 12: 130000, 13: 140000, 14: 180000, 15: 190000,
    16: 200000, 17: 210000, 18: 220000, 19: 230000, 20: 240000,
    21: 280000, 22: 290000, 23: 300000, 24: 310000, 25: 320000,
    26: 330000, 27: 340000, 28: 380000, 29: 390000, 30: 450000
}

# تهران = UTC + 3:30
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)



def utc_now():
    """دریافت زمان فعلی UTC"""
    return datetime.now(timezone.utc)


def get_today_tehran_start_utc(now_utc: datetime) -> datetime:
    """
    شروع 'امروز تهران' را به UTC برمی‌گرداند.
    00:00 تهران = 20:30 UTC روز قبل
    """
    tehran_now = now_utc + TEHRAN_OFFSET
    tehran_today_midnight = tehran_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return tehran_today_midnight - TEHRAN_OFFSET


@router.get("/status")
def get_daily_reward_status(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    current_user = get_current_user_from_token(credentials, db)
    now_utc = utc_now()
    
    # مقداردهی اولیه
    if current_user.daily_reward_day is None or current_user.daily_reward_day <= 0:
        current_user.daily_reward_day = 1
        db.commit()
    
    can_claim = True
    remaining_seconds = 0
    
    # بررسی آخرین دریافت
    if current_user.last_daily_reward:
        last_claim = current_user.last_daily_reward
        
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)

        today_start_utc = get_today_tehran_start_utc(now_utc)

        if last_claim >= today_start_utc:
            can_claim = False
            tomorrow_start_utc = today_start_utc + timedelta(days=1)
            remaining_seconds = max(0, int((tomorrow_start_utc - now_utc).total_seconds()))
    
    current_day = int(current_user.daily_reward_day)
    reward_amount = DAILY_REWARDS.get(current_day, 10000)
    
    return {
        "success": True,
        "current_day": current_day,
        "reward_amount": reward_amount,
        "can_claim": can_claim,
        "remaining_seconds": remaining_seconds,
        "remaining_hours": round(remaining_seconds / 3600, 1),
        "last_claim_date": last_claim.strftime("%Y-%m-%d %H:%M:%S UTC") if current_user.last_daily_reward else None,
        "server_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total_coins": current_user.coins or 0
    }


@router.post("/claim")
def claim_daily_reward(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    current_user = get_current_user_from_token(credentials, db)
    now_utc = utc_now()
    
    # مقداردهی اولیه
    if current_user.daily_reward_day is None or current_user.daily_reward_day <= 0:
        current_user.daily_reward_day = 1
    
    # بررسی آخرین دریافت با منطق 00:00 تهران
    if current_user.last_daily_reward:
        last_claim = current_user.last_daily_reward
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)

        today_start_utc = get_today_tehran_start_utc(now_utc)

        if last_claim >= today_start_utc:
            tomorrow_start_utc = today_start_utc + timedelta(days=1)
            remaining_seconds = max(0, int((tomorrow_start_utc - now_utc).total_seconds()))
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "جایزه امروز را دریافت کرده‌اید. جایزه بعدی ساعت 00:00 به وقت تهران.",
                    "remaining_seconds": remaining_seconds,
                    "remaining_hours": round(remaining_seconds / 3600, 1)
                }
            )
    
    # روز فعلی کاربر (هر چند روز نیامده باشد، همین روز باقی می‌ماند)
    current_day = int(current_user.daily_reward_day)
    
    # دریافت جایزه
    reward_amount = DAILY_REWARDS.get(current_day, 10000)
    
    # اعمال جایزه
    if current_user.coins is None:
        current_user.coins = 0
    current_user.coins += reward_amount
    
    # ذخیره زمان دریافت (به UTC)
    current_user.last_daily_reward = now_utc
    
    # رفتن به روز بعد (اگر به 30 رسید، دور می‌زند)
    next_day = current_day + 1
    if next_day > 30:
        next_day = 1
    
    current_user.daily_reward_day = next_day
    
    db.commit()
    
    return {
        "success": True,
        "message": f"شما {reward_amount:,} سکه جایزه دریافت کردید",
        "reward": str(reward_amount),          # ✅ string بدون کاما
        "reward_amount": reward_amount,        # integer
        "reward_string": f"{reward_amount:,}", # با کاما برای نمایش
        "claimed_day": current_day,
        "next_day": next_day,
        "total_coins": int(current_user.coins),
        "claimed_at": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    }
