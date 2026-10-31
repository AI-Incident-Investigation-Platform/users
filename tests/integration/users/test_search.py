import pytest
from httpx import AsyncClient

from tests.integration.conftest import Register


@pytest.mark.case(id="USERS-SEARCH-001")
async def test_people_are_found_by_username_email_and_name(
    client: AsyncClient, register: Register
) -> None:
    yuri = await register("yuri@example.com")
    oleg = await register("oleg@ai.example")
    await client.patch(
        "/api/v1/users/me",
        json={"username": "oleg-ai", "display_name": "Олег Агентов", "timezone": "UTC"},
        headers=oleg.headers,
    )

    def found(response: object) -> list[str]:
        return [item["username"] for item in response.json()["items"]]  # type: ignore[attr-defined]

    by_username = await client.get("/api/v1/users", params={"q": "Yur"}, headers=oleg.headers)
    by_email = await client.get("/api/v1/users", params={"q": "oleg@ai"}, headers=yuri.headers)
    by_name = await client.get("/api/v1/users", params={"q": "агент"}, headers=yuri.headers)
    wildcard = await client.get("/api/v1/users", params={"q": "%"}, headers=yuri.headers)
    first_page = await client.get(
        "/api/v1/users", params={"q": "o", "limit": 1}, headers=yuri.headers
    )

    assert found(by_username) == ["yuri"]
    assert by_username.json()["items"][0]["email"] == "yuri@example.com"
    assert found(by_email) == ["oleg-ai"]
    assert found(by_name) == ["oleg-ai"]
    assert found(wildcard) == []
    assert len(first_page.json()["items"]) == 1
    assert first_page.json()["next_cursor"] is None or isinstance(
        first_page.json()["next_cursor"], str
    )


@pytest.mark.case(id="USERS-SEARCH-002")
async def test_profiles_by_id_and_in_batch(client: AsyncClient, register: Register) -> None:
    yuri = await register("yuri@example.com")
    oleg = await register("oleg@example.com")

    one = await client.get(f"/api/v1/users/{oleg.user_id}", headers=yuri.headers)
    batch = await client.get(
        "/api/v1/users/lookup",
        params=[
            ("ids", str(yuri.user_id)),
            ("ids", str(oleg.user_id)),
            ("ids", str(yuri.session_id)),
        ],
        headers=yuri.headers,
    )
    missing = await client.get(f"/api/v1/users/{yuri.session_id}", headers=yuri.headers)
    anonymous = await client.get(f"/api/v1/users/{oleg.user_id}")

    assert one.json()["username"] == "oleg"
    assert sorted(item["username"] for item in batch.json()["items"]) == ["oleg", "yuri"]
    assert missing.status_code == 404
    assert anonymous.status_code == 401
