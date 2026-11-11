import logging
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert

from broker import broker_connection, publish_job
from database import SessionLocal
from models import RegistrationJob, User

REGISTRATION_QUEUE = "game.registrations"
logger = logging.getLogger(__name__)


class RegistrationMessage(BaseModel):
    job_id: UUID


def enqueue_registration(job_id: UUID) -> None:
    # جزئیات ثبت‌نام در دیتابیس است و فقط شناسهٔ درخواست را به صف می‌فرستیم.
    message = RegistrationMessage(job_id=job_id)
    publish_job(REGISTRATION_QUEUE, message.model_dump_json())


def create_player(job_id: UUID) -> None:
    with SessionLocal.begin() as db:
        # وضعیت را در همین تراکنش عوض می‌کنیم تا تحویل دوبارهٔ پیام، حساب تکراری نسازد.
        username = db.execute(
            update(RegistrationJob)
            .where(
                RegistrationJob.id == str(job_id),
                RegistrationJob.status.in_(("queued", "publish_unconfirmed")),
            )
            .values(status="processing")
            .returning(RegistrationJob.username)
        ).scalar_one_or_none()
        if username is None:
            return

        # خود دیتابیس جلوی ساخت دو حساب با یک نام کاربری را می‌گیرد.
        user_id = db.execute(
            insert(User)
            .values(username=username)
            .on_conflict_do_nothing(index_elements=[User.username])
            .returning(User.id)
        ).scalar_one_or_none()
        db.execute(
            update(RegistrationJob)
            .where(RegistrationJob.id == str(job_id))
            .values(status="created" if user_id is not None else "username_taken", user_id=user_id)
        )


def consume_registration(channel, method, properties, body) -> None:
    try:
        message = RegistrationMessage.model_validate_json(body)
    except ValidationError:
        logger.warning("Rejecting invalid registration message")
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
        return

    # تأیید پیام بعد از ثبت نتیجه در دیتابیس فرستاده می‌شود.
    create_player(message.job_id)
    channel.basic_ack(delivery_tag=method.delivery_tag)
    logger.info("Registration %s processed", message.job_id)


def run_worker() -> None:
    with broker_connection() as connection:
        channel = connection.channel()
        channel.queue_declare(queue=REGISTRATION_QUEUE, durable=True)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue=REGISTRATION_QUEUE,
            on_message_callback=consume_registration,
            auto_ack=False,
        )
        logger.info("Waiting for jobs on %s", REGISTRATION_QUEUE)
        channel.start_consuming()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run_worker()
    except KeyboardInterrupt:
        pass
