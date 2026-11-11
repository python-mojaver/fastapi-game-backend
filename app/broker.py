import os

import pika

DEFAULT_AMQP_URL = "amqp://game_demo:local_demo_only@127.0.0.1:5672/%2F"


def broker_connection():
    parameters = pika.URLParameters(os.environ.get("RABBITMQ_URL", DEFAULT_AMQP_URL))
    parameters.socket_timeout = 3
    parameters.stack_timeout = 5
    parameters.blocked_connection_timeout = 5
    return pika.BlockingConnection(parameters)


def publish_job(queue_name: str, body: str) -> None:
    with broker_connection() as connection:
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        # قبل از پاسخ به کاربر، منتظر تأیید دریافت پیام از RabbitMQ می‌مانیم.
        channel.confirm_delivery()
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=body.encode(),
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
            mandatory=True,
        )
