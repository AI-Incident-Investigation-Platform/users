from datetime import UTC, datetime, timedelta
from uuid import uuid7

import aio_pika
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import cfg
from src.core.db.models import User
from src.main import container
from tests.integration.conftest import AuthEvents, Register, profile_email, wait_for


async def username_of(db: AsyncSession, user_id: object) -> str | None:
    db.expire_all()
    return await db.scalar(select(User.username).where(User.id == user_id))


@pytest.mark.case(id="USERS-EVENT-001")
async def test_registration_creates_profile_once_and_newer_email_wins(
    auth_events: AuthEvents, db: AsyncSession
) -> None:
    user_id = uuid7()
    registered_at = datetime.now(UTC)
    await auth_events.publish(
        "user.registered", user_id, "Yuri.Dev+aiip@example.com", registered_at
    )

    async def created() -> bool:
        return await profile_email(user_id) is not None

    await wait_for(created)
    await auth_events.publish(
        "user.registered", user_id, "yuri.dev+aiip@example.com", registered_at
    )
    await auth_events.publish(
        "user.email_changed", user_id, "new@example.com", registered_at + timedelta(minutes=2)
    )

    async def changed() -> bool:
        return await profile_email(user_id) == "new@example.com"

    await wait_for(changed)
    await auth_events.publish(
        "user.email_changed", user_id, "old@example.com", registered_at + timedelta(minutes=1)
    )
    marker = uuid7()
    await auth_events.publish("user.registered", marker, "marker@example.com")

    async def marker_created() -> bool:
        return await profile_email(marker) is not None

    await wait_for(marker_created)

    assert await username_of(db, user_id) == "yuri-dev"
    assert await profile_email(user_id) == "new@example.com"
    assert len((await db.scalars(select(User.id))).all()) == 2


@pytest.mark.case(id="USERS-EVENT-002")
async def test_taken_username_gets_digits(register: Register, db: AsyncSession) -> None:
    first = await register("yuri@example.com")
    second = await register("yuri@other.example")

    first_name = await username_of(db, first.user_id)
    second_name = await username_of(db, second.user_id)
    assert first_name == "yuri"
    assert second_name is not None and second_name != "yuri"
    assert second_name.startswith("yuri") and second_name[4:].isdigit()


@pytest.mark.case(id="USERS-EVENT-003")
async def test_malformed_event_goes_to_dead_letter(auth_events: AuthEvents) -> None:
    await auth_events.publish("user.registered", uuid7(), "x", body=b"{not json")

    connection = await aio_pika.connect(cfg.rabbitmq.url)
    channel = await connection.channel()
    dead = await channel.declare_queue(f"{cfg.auth_events.queue}.dead", passive=True)

    async def dead_lettered() -> bool:
        message = await dead.get(no_ack=True, fail=False)
        return message is not None and message.body == b"{not json"

    await wait_for(dead_lettered)
    await connection.close()
    assert await (await container.get(Redis)).exists("users:usernames:bloom") in (0, 1)
