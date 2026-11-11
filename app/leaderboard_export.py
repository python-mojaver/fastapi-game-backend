import csv
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from pydantic import BaseModel, PositiveInt, ValidationError

from broker import broker_connection, publish_job
from database import SessionLocal, data_dir
from leaderboard_data import leaderboard_rows

QUEUE_NAME = "leaderboard.exports"
logger = logging.getLogger(__name__)


class LeaderboardExport(BaseModel):
    job_id: UUID
    user_id: PositiveInt


def export_path(job: LeaderboardExport) -> Path:
    return data_dir / "exports" / str(job.user_id) / f"{job.job_id}.csv"


def enqueue_export(job: LeaderboardExport) -> None:
    publish_job(QUEUE_NAME, job.model_dump_json())


def write_export(job: LeaderboardExport) -> None:
    path = export_path(job)
    # اگر پیام دوباره برسد، فایل آمادهٔ همین درخواست را نگه می‌داریم.
    if path.is_file():
        return

    with SessionLocal() as db:
        rows = leaderboard_rows(db, job.user_id, limit=100)

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ("rank", "username", "coins", "level")
    # فایل نهایی را بعد از کامل شدن CSV جایگزین می‌کنیم تا کاربر فایل ناقص نگیرد.
    output = NamedTemporaryFile(
        mode="w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False
    )
    temporary_path = Path(output.name)
    try:
        with output:
            writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def consume_export(channel, method, properties, body) -> None:
    try:
        job = LeaderboardExport.model_validate_json(body)
    except ValidationError:
        logger.warning("Rejecting invalid leaderboard export message")
        channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
        return

    # اگر نوشتن فایل خطا بدهد، پیام بدون تأیید می‌ماند و دوباره قابل تحویل است.
    write_export(job)
    channel.basic_ack(delivery_tag=method.delivery_tag)
    logger.info("Leaderboard export %s is ready", job.job_id)


def run_worker() -> None:
    with broker_connection() as connection:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue=QUEUE_NAME,
            on_message_callback=consume_export,
            auto_ack=False,
        )
        logger.info("Waiting for jobs on %s", QUEUE_NAME)
        channel.start_consuming()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run_worker()
    except KeyboardInterrupt:
        pass
