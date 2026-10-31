import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.models import User
from src.main import container
from tests.integration.conftest import (
    AuthEvents,
    Register,
    SignIn,
    profile_email,
    wait_for,
)
from tests.support.tokens import ACCOUNTS

PROFILE = {
    "username": "Yuri",
    "display_name": "Юрий",
    "timezone": "Europe/Moscow",
    "working_hours": {"starts_at": "10:00", "ends_at": "19:00", "days": [5, 1, 2, 3, 4]},
}


@pytest.mark.case(id="USERS-PROFILE-001")
async def test_first_save_completes_onboarding_and_patch_is_partial(
    client: AsyncClient, register: Register
) -> None:
    user = await register("someone@example.com")

    before = await client.get("/api/v1/users/me", headers=user.headers)
    saved = await client.patch("/api/v1/users/me", json=PROFILE, headers=user.headers)
    renamed = await client.patch(
        "/api/v1/users/me", json={"username": "yuri-dev"}, headers=user.headers
    )
    cleared = await client.patch(
        "/api/v1/users/me",
        json={"display_name": None, "working_hours": None},
        headers=user.headers,
    )
    null_username = await client.patch(
        "/api/v1/users/me", json={"username": None}, headers=user.headers
    )

    assert before.json()["username"] == "someone"
    assert before.json()["onboarded_at"] is None
    assert before.json()["timezone"] == "UTC"
    body = saved.json()
    assert saved.status_code == 200
    assert body["username"] == "yuri"
    assert body["display_name"] == "Юрий"
    assert body["email"] == "someone@example.com"
    assert body["working_hours"] == {
        "starts_at": "10:00:00",
        "ends_at": "19:00:00",
        "days": [1, 2, 3, 4, 5],
    }
    assert body["onboarded_at"] is not None
    assert body["avatar_url"] is None
    assert renamed.json()["username"] == "yuri-dev"
    assert renamed.json()["display_name"] == "Юрий"
    assert renamed.json()["timezone"] == "Europe/Moscow"
    assert renamed.json()["working_hours"] == body["working_hours"]
    assert cleared.json()["working_hours"] is None
    assert cleared.json()["display_name"] is None
    assert cleared.json()["username"] == "yuri-dev"
    assert cleared.json()["onboarded_at"] == body["onboarded_at"]
    assert null_username.status_code == 422


@pytest.mark.case(id="USERS-PROFILE-003")
async def test_own_profile_exists_before_registration_event(
    client: AsyncClient, sign_in: SignIn, auth_events: AuthEvents, db: AsyncSession
) -> None:
    early = await sign_in()
    ACCOUNTS[str(early.user_id)] = "early@example.com"

    me = await client.get("/api/v1/users/me", headers=early.headers)
    await auth_events.publish("user.registered", early.user_id, "early@example.com")
    marker = await sign_in()
    await auth_events.publish("user.registered", marker.user_id, "marker@example.com")

    async def marker_created() -> bool:
        return await profile_email(marker.user_id) is not None

    await wait_for(marker_created)
    again = await client.get("/api/v1/users/me", headers=early.headers)

    assert me.status_code == 200
    assert me.json()["username"] == "early"
    assert me.json()["email"] == "early@example.com"
    assert again.json() == me.json()
    assert await db.scalar(select(func.count()).select_from(User)) == 2


@pytest.mark.case(id="USERS-PROFILE-002")
async def test_profile_is_validated(client: AsyncClient, register: Register) -> None:
    user = await register("someone@example.com")
    url = "/api/v1/users/me"

    bad = [
        {**PROFILE, "username": "-yuri"},
        {**PROFILE, "username": "yu"},
        {**PROFILE, "timezone": "Mars/Olympus"},
        {**PROFILE, "working_hours": {"starts_at": "10:00", "ends_at": "10:00", "days": [1]}},
        {**PROFILE, "working_hours": {"starts_at": "10:00", "ends_at": "19:00", "days": [8]}},
        {**PROFILE, "working_hours": {"starts_at": "10:00", "ends_at": "19:00", "days": [1, 1]}},
    ]
    responses = [await client.patch(url, json=body, headers=user.headers) for body in bad]
    night = await client.patch(
        url,
        json={**PROFILE, "working_hours": {"starts_at": "22:00", "ends_at": "06:00", "days": [6]}},
        headers=user.headers,
    )

    assert [response.status_code for response in responses] == [422] * len(bad)
    assert {response.json()["error"]["code"] for response in responses} == {"request.invalid"}
    assert night.status_code == 200


@pytest.mark.case(id="USERS-NAME-001")
async def test_username_is_unique_and_availability_is_exact(
    client: AsyncClient, register: Register
) -> None:
    yuri = await register("yuri@example.com")
    oleg = await register("oleg@example.com")
    cache = await container.get(Redis)
    url = "/api/v1/users/username-availability"

    taken = await client.get(url, params={"username": "Yuri"}, headers=oleg.headers)
    own = await client.get(url, params={"username": "yuri"}, headers=yuri.headers)
    free = await client.get(url, params={"username": "daniil"}, headers=oleg.headers)
    conflict = await client.patch(
        "/api/v1/users/me", json={**PROFILE, "username": "yuri"}, headers=oleg.headers
    )
    renamed = await client.patch(
        "/api/v1/users/me", json={**PROFILE, "username": "rasul"}, headers=oleg.headers
    )
    await cache.delete("users:usernames:bloom")
    after_loss = await client.get(url, params={"username": "rasul"}, headers=yuri.headers)
    rebuilt = await cache.execute_command("BF.EXISTS", "users:usernames:bloom", "rasul")

    assert taken.json() == {"username": "yuri", "available": False}
    assert own.json()["available"] is True
    assert free.json()["available"] is True
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "user.username_taken"
    assert renamed.status_code == 200
    assert after_loss.json()["available"] is False
    assert rebuilt == 1
