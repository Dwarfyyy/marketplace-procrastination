import asyncio
import json
import logging
import os

import aio_pika

from core.db import SessionLocal
from services.product_events import apply_product_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCHANGE = os.getenv("RABBITMQ_EXCHANGE", "neomarket.events")
QUEUE = os.getenv("RABBITMQ_MODERATION_QUEUE", "moderation.product.events")
ROUTING_KEY = os.getenv("RABBITMQ_ROUTING_KEY_MODERATION_PRODUCT", "moderation.product.*")


def _rabbitmq_url() -> str:
	host = os.getenv("RABBITMQ_HOST", "localhost")
	port = os.getenv("RABBITMQ_PORT", "5672")
	user = os.getenv("RABBITMQ_USER", "guest")
	password = os.getenv("RABBITMQ_PASSWORD", "guest")
	return f"amqp://{user}:{password}@{host}:{port}/"


async def main() -> None:
	connection = await aio_pika.connect_robust(_rabbitmq_url())
	async with connection:
		channel = await connection.channel()
		exchange = await channel.declare_exchange(
			EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
		)
		queue = await channel.declare_queue(QUEUE, durable=True)
		await queue.bind(exchange, routing_key=ROUTING_KEY)
		logger.info("Listening on queue %s (routing_key=%s)", QUEUE, ROUTING_KEY)

		async with queue.iterator() as queue_iter:
			async for message in queue_iter:
				async with message.process():
					payload = json.loads(message.body.decode("utf-8"))
					async with SessionLocal() as db:
						await apply_product_event(db, payload)


if __name__ == "__main__":
	asyncio.run(main())
