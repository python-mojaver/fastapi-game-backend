from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User
from routes.auth import get_current_user_from_token

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


# =========================
# نشست دیتابیس
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# محاسبهٔ سطح بازیکن
# =========================
def calculate_level(coins: float):
    if coins >= 5000000:
        return 10
    elif coins >= 3500000:
        return 9
    elif coins >= 2200000:
        return 8
    elif coins >= 1500000:
        return 7
    elif coins >= 1000000:
        return 6
    elif coins >= 700000:
        return 5
    elif coins >= 450000:
        return 4
    elif coins >= 250000:
        return 3
    elif coins >= 100000:
        return 2
    return 1


# =========================
# ده بازیکن اول و رتبهٔ بازیکن فعلی
# =========================
@router.get("/")
def get_leaderboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token)
):
    # 10 نفر اول
    top_users = (
        db.query(User)
        .order_by(User.coins.desc())
        .limit(10)
        .all()
    )

    leaderboard = []

    for index, user in enumerate(top_users, start=1):
        leaderboard.append({
            "rank": index,
            "username": user.username,
            "level": calculate_level(user.coins),
            "coins": round(user.coins, 2)
        })

    # رتبه واقعی
    better_users_count = (
        db.query(User)
        .filter(User.coins > current_user.coins)
        .count()
    )

    current_rank = better_users_count + 1

    return {
        "top_10": leaderboard,
        "current_user": {
            "rank": current_rank,
            "username": current_user.username,
            "level": calculate_level(current_user.coins),
            "coins": round(current_user.coins, 2)
        }
    }
