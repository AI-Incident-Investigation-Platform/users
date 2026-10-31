import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid7

import aio_pika
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import cfg
from src.core.db.db import engine, session_maker
from src.core.db.models import Base, User
from src.core.rabbitmq.connection import RabbitmqConnection
from src.main import app as users_app
from src.main import container
from src.worker.auth_events.consumer import AuthEventsConsumer
from tests.support.tokens import ACCOUNTS, issue_access_token

ORIGIN = "http://testserver"


@dataclass(frozen=True)
class SignedInUser:
    user_id: UUID
    session_id: UUID
    headers: dict[str, str]


type SignIn = Callable[[], Awaitable[SignedInUser]]


class AuthEvents:
    """На месте auth: публикует события о пользователях в exchange auth."""

    def __init__(self, exchange: aio_pika.abc.AbstractExchange) -> None:
        self._exchange = exchange

    async def publish(
        self,
        event_type: str,
        user_id: UUID,
        email: str,
        occurred_at: datetime | None = None,
        body: bytes | None = None,
    ) -> None:
        payload = (
            body
            or json.dumps(
                {
                    "event_id": str(uuid7()),
                    "type": event_type,
                    "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
                    "user_id": str(user_id),
                    "email": email,
                }
            ).encode()
        )
        await self._exchange.publish(
            aio_pika.Message(payload, content_type="application/json"), routing_key=event_type
        )


type Register = Callable[[str], Awaitable[SignedInUser]]


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    # ASGI-транспорт не запускает lifespan: потребитель событий стартует здесь
    await AuthEventsConsumer(container, await container.get(RabbitmqConnection)).run()
    yield users_app
    await container.close()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", headers={"Origin": ORIGIN}
    ) as c:
        yield c


@pytest.fixture
async def sign_in(app: FastAPI) -> SignIn:
    """Пользователь с живой сессией, как после входа в auth: токен в куке и пропуск в кэше."""
    cache = await container.get(Redis)

    async def make() -> SignedInUser:
        user_id, session_id = uuid7(), uuid7()
        await cache.set(f"{cfg.auth.session_key_prefix}{session_id}", 1, ex=900)
        token = issue_access_token(user_id, session_id)
        return SignedInUser(user_id, session_id, {"Cookie": f"access_token={token}"})

    return make


@pytest.fixture
async def auth_events(app: FastAPI) -> AsyncIterator[AuthEvents]:
    connection = await aio_pika.connect(cfg.rabbitmq.url)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        cfg.auth_events.exchange, aio_pika.ExchangeType.TOPIC, durable=True
    )
    yield AuthEvents(exchange)
    await connection.close()


async def wait_for(check: Callable[[], Awaitable[bool]], timeout: float = 5) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not await check():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("событие auth не обработано")
        await asyncio.sleep(0.05)


async def profile_email(user_id: UUID) -> str | None:
    async with session_maker() as session:
        return await session.scalar(select(User.email).where(User.id == user_id))


@pytest.fixture
async def register(sign_in: SignIn, auth_events: AuthEvents) -> Register:
    """Пользователь, о регистрации которого auth уже сообщил: профиль создан."""

    async def make(email: str) -> SignedInUser:
        user = await sign_in()
        ACCOUNTS[str(user.user_id)] = email
        await auth_events.publish("user.registered", user.user_id, email)

        async def created() -> bool:
            return await profile_email(user.user_id) is not None

        await wait_for(created)
        return user

    return make


@pytest.fixture
async def db(app: FastAPI) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture(autouse=True)
async def clean_state(app: FastAPI) -> AsyncIterator[None]:
    yield
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    await (await container.get(Redis)).flushdb()
    ACCOUNTS.clear()
