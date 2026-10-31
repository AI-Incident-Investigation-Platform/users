import logging

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractQueue
from dishka import AsyncContainer
from opentelemetry import context, propagate, trace
from pydantic import ValidationError

from src.config import cfg
from src.core.errors import (
    AppError,
    ErrorReport,
    IntegrationTimeoutError,
    IntegrationUnavailableError,
    PersistenceUnavailableError,
)
from src.core.rabbitmq.connection import RabbitmqConnection
from src.worker.auth_events.dto import UserEvent
from src.worker.auth_events.enums import EventOutcome
from src.worker.auth_events.metrics import AUTH_EVENTS
from src.worker.auth_events.schemas import UserEventMessage
from src.worker.auth_events.service import AuthEventsService

log = logging.getLogger(__name__)

ATTEMPT_HEADER = "x-attempt"


class AuthEventsConsumer:
    """Принимает события auth о пользователях и решает их судьбу по исходу записи.

    Временный отказ (БД, кэш) — копия события в retry-очередь с задержкой и ack
    оригинала, пока не исчерпан лимит попыток; битое событие, непредвиденная
    ошибка и исчерпанные попытки — dead-letter. Retry и dead-letter — очереди
    рядом с основной, сообщение в них идёт через exchange по умолчанию.
    """

    def __init__(self, container: AsyncContainer, connection: RabbitmqConnection) -> None:
        self._container = container
        self._connection = connection
        self._channel: AbstractChannel | None = None
        self._tracer = trace.get_tracer(__name__)

    async def run(self) -> None:
        """Ждёт брокер и начинает приём; HTTP-часть сервиса работает и без него."""
        connection = await self._connection.connect()
        self._channel = await connection.channel()
        await self._channel.set_qos(prefetch_count=cfg.auth_events.prefetch)
        queue = await self._declare_topology(self._channel)
        await queue.consume(self.handle)
        log.info(
            "Начат приём событий auth",
            extra={"event": "auth_events.consuming_started", "queue": cfg.auth_events.queue},
        )

    async def handle(self, message: AbstractIncomingMessage) -> None:
        headers = message.headers or {}
        attempt = int(str(headers.get(ATTEMPT_HEADER, 1)))
        token = context.attach(propagate.extract({k: str(v) for k, v in headers.items()}))
        try:
            with self._tracer.start_as_current_span("auth_events.apply"):
                await self._process(message, attempt)
        finally:
            context.detach(token)

    async def _process(self, message: AbstractIncomingMessage, attempt: int) -> None:
        try:
            body = UserEventMessage.model_validate_json(message.body)
        except ValidationError:
            await message.reject(requeue=False)
            self._record(EventOutcome.DEAD, "unknown", attempt, message.message_id)
            return
        event = UserEvent(
            event_id=body.event_id,
            type=body.type,
            occurred_at=body.occurred_at,
            user_id=body.user_id,
            email=body.email.lower(),
        )
        try:
            async with self._container() as request:
                service = await request.get(AuthEventsService)
                outcome = await service.apply(event)
        except (
            IntegrationUnavailableError,
            IntegrationTimeoutError,
            PersistenceUnavailableError,
        ) as exc:
            if attempt < cfg.auth_events.max_attempts:
                await self._retry(message, attempt + 1)
                await message.ack()
                self._record(EventOutcome.RETRIED, event.type, attempt, event.event_id, exc)
            else:
                await message.reject(requeue=False)
                self._record(EventOutcome.DEAD, event.type, attempt, event.event_id, exc)
        except Exception as exc:
            await message.reject(requeue=False)
            self._record(EventOutcome.DEAD, event.type, attempt, event.event_id, exc)
        else:
            await message.ack()
            AUTH_EVENTS.labels(event.type.value, outcome.value).inc()

    async def _retry(self, message: AbstractIncomingMessage, attempt: int) -> None:
        if self._channel is None:
            raise RuntimeError("consumer is not started")
        await self._channel.default_exchange.publish(
            aio_pika.Message(
                message.body,
                message_id=message.message_id,
                content_type=message.content_type,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={**(message.headers or {}), ATTEMPT_HEADER: attempt},
            ),
            routing_key=f"{cfg.auth_events.queue}.retry",
        )

    @staticmethod
    def _record(
        outcome: EventOutcome,
        event_type: str,
        attempt: int,
        event_id: str | None,
        exc: Exception | None = None,
    ) -> None:
        AUTH_EVENTS.labels(event_type, outcome.value).inc()
        fields: dict[str, object] = {
            "event": f"auth_events.{outcome.value}",
            "auth_event": {"event_id": event_id, "type": event_type, "attempt": attempt},
        }
        if exc is not None:
            fields["error"] = ErrorReport.from_exception(exc).to_log()
        if outcome == EventOutcome.DEAD:
            log.error(
                "Событие auth не обработано и отправлено в dead-letter",
                exc_info=exc if exc is not None and not isinstance(exc, AppError) else None,
                extra=fields,
            )
        else:
            log.warning("Событие auth отложено на повтор", extra=fields)

    @staticmethod
    async def _declare_topology(channel: AbstractChannel) -> AbstractQueue:
        events = cfg.auth_events
        exchange = await channel.declare_exchange(
            events.exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        await channel.declare_queue(
            f"{events.queue}.dead",
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-message-ttl": events.dead_letter_ttl_days * 86_400_000,
            },
        )
        await channel.declare_queue(
            f"{events.queue}.retry",
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-message-ttl": events.retry_delay_seconds * 1000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": events.queue,
            },
        )
        queue = await channel.declare_queue(
            events.queue,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": f"{events.queue}.dead",
            },
        )
        await queue.bind(exchange, routing_key="user.*")
        return queue
