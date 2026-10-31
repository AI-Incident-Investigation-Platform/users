import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPError

from src.config import cfg

log = logging.getLogger(__name__)


class RabbitmqConnection:
    """Соединение с брокером: старт ждёт его доступности, дальше соединение переподключается само.

    Пока брокера нет, сервис не стартует: воркер без очереди бесполезен, а startup-проба
    перезапустит под.
    """

    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None

    async def connect(self) -> AbstractRobustConnection:
        while self._connection is None:
            try:
                self._connection = await aio_pika.connect_robust(
                    cfg.rabbitmq.url, timeout=cfg.rabbitmq.connect_timeout_seconds
                )
            except (AMQPError, OSError, TimeoutError) as exc:
                log.warning(
                    "Не удалось подключиться к RabbitMQ, повторю",
                    extra={
                        "event": "rabbitmq.connect_failed",
                        "error": {"type": type(exc).__name__},
                    },
                )
                await asyncio.sleep(cfg.rabbitmq.reconnect_delay_seconds)
        return self._connection

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
