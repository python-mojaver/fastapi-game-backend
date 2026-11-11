from sqlalchemy.orm import Session

from models import User


def leaderboard_rows(db: Session, current_user_id: int, limit: int) -> list[dict]:
    users = db.query(User).filter(User.is_active == True).order_by(User.coins.desc()).limit(limit).all()
    return [
        {
            "rank": rank,
            "username": user.username,
            "coins": round(user.coins, 2),
            "level": user.level,
            "is_current_user": user.id == current_user_id,
        }
        for rank, user in enumerate(users, 1)
    ]
