"""Issue short-lived tokens for the synthetic player in the local demo."""
from datetime import datetime, timedelta, timezone
from secrets import token_hex

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User

router = APIRouter(prefix="/demo", tags=["Demo session"])
security = HTTPBearer()
signing_key = token_hex(32)
DEMO_PLAYER = "demo-player"


@router.post("/session")
def create_session(db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=DEMO_PLAYER).one()
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(user.id), "exp": expiry, "aud": "local-game-demo"},
        signing_key, algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        claims = jwt.decode(
            credentials.credentials, signing_key, algorithms=["HS256"],
            audience="local-game-demo", options={"require": ["sub", "exp"]},
        )
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Invalid or expired demo token") from None
    user = db.get(User, user_id)
    if user is None or user.username != DEMO_PLAYER or not user.is_active:
        raise HTTPException(401, "Unknown demo player")
    return user
