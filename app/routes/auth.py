"""ورود آزمایشی و ثبت‌نام بازیکن از طریق صف."""
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pika.exceptions import AMQPError
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from database import get_db
from models import RegistrationJob, User
from registration_worker import enqueue_registration

router = APIRouter(prefix="/demo", tags=["Demo session"])
security = HTTPBearer()
signing_key = token_hex(32)
DEMO_PLAYER = "demo-player"


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9][a-z0-9_-]*$")


@router.post("/register", status_code=202)
def register_player(
    registration: RegistrationRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    job_id = uuid4()
    # Worker با شناسهٔ پیام دنبال این رکورد می‌گردد، پس اول آن را ذخیره می‌کنیم.
    db.add(RegistrationJob(id=str(job_id), username=registration.username, status="queued"))
    db.commit()

    status_url = request.url_for("registration_status", job_id=str(job_id)).path
    try:
        enqueue_registration(job_id)
    except AMQPError as error:
        # ممکن است Worker پیام را گرفته باشد. نتیجهٔ ثبت‌شده را بازنویسی نمی‌کنیم.
        db.execute(
            update(RegistrationJob)
            .where(RegistrationJob.id == str(job_id), RegistrationJob.status == "queued")
            .values(status="publish_unconfirmed")
        )
        db.commit()
        raise HTTPException(
            503,
            detail={
                "message": "Could not confirm the registration request with RabbitMQ",
                "job_id": str(job_id),
                "status_url": status_url,
            },
        ) from error

    response.headers["Location"] = status_url
    return {"job_id": job_id, "status_url": status_url}


@router.get("/register/{job_id}")
def registration_status(job_id: UUID, db: Session = Depends(get_db)):
    job = db.get(RegistrationJob, str(job_id))
    if job is None:
        raise HTTPException(404, "Registration request not found")
    return {"job_id": job.id, "username": job.username, "status": job.status, "user_id": job.user_id}


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
