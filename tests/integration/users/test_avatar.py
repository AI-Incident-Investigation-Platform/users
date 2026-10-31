import pytest
from httpx import AsyncClient, Response

from src.config import cfg
from src.core.s3.service import S3Service
from src.main import container
from tests.integration.conftest import Register

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def upload(
    client: AsyncClient, headers: dict[str, str], data: bytes, content_type: str
) -> Response:
    return await client.put(
        "/api/v1/users/me/avatar",
        content=data,
        headers={**headers, "Content-Type": content_type},
    )


@pytest.mark.case(id="USERS-AVATAR-001")
async def test_avatar_is_uploaded_served_replaced_and_deleted(
    client: AsyncClient, register: Register
) -> None:
    yuri = await register("yuri@example.com")
    oleg = await register("oleg@example.com")
    s3 = await container.get(S3Service)

    first = await upload(client, yuri.headers, PNG, "image/png")
    first_url = first.json()["avatar_url"]
    served = await client.get(first_url, headers=oleg.headers)
    second = await upload(client, yuri.headers, JPEG, "image/jpeg")
    second_url = second.json()["avatar_url"]
    old_key = f"avatars/{yuri.user_id}/{first_url.rsplit('=', 1)[1]}"
    old_object = await s3.get(old_key)
    in_list = await client.get(
        "/api/v1/users/lookup", params={"ids": str(yuri.user_id)}, headers=oleg.headers
    )
    deleted = await client.delete("/api/v1/users/me/avatar", headers=yuri.headers)
    after = await client.get("/api/v1/users/me", headers=yuri.headers)
    gone = await client.get(f"/api/v1/users/{yuri.user_id}/avatar", headers=oleg.headers)

    assert first.status_code == 200
    assert first_url.startswith(f"/api/v1/users/{yuri.user_id}/avatar?v=")
    assert served.status_code == 200
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert "immutable" in served.headers["cache-control"]
    assert served.headers["x-content-type-options"] == "nosniff"
    assert second_url != first_url
    assert old_object is None
    assert in_list.json()["items"][0]["avatar_url"] == second_url
    assert deleted.status_code == 204
    assert after.json()["avatar_url"] is None
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "user.avatar_not_found"


@pytest.mark.case(id="USERS-AVATAR-002")
async def test_avatar_must_be_a_small_image_of_declared_type(
    client: AsyncClient, register: Register, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await register("yuri@example.com")
    monkeypatch.setattr(cfg.avatars, "max_bytes", 100)

    mismatch = await upload(client, user.headers, PNG, "image/jpeg")
    not_image = await upload(client, user.headers, b"<svg onload=alert(1)>", "image/png")
    too_large = await upload(client, user.headers, PNG + b"\x00" * 100, "image/png")
    me = await client.get("/api/v1/users/me", headers=user.headers)

    assert mismatch.status_code == not_image.status_code == 422
    assert (
        mismatch.json()["error"]["code"]
        == not_image.json()["error"]["code"]
        == ("user.avatar_invalid")
    )
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "user.avatar_too_large"
    assert too_large.json()["error"]["details"] == {"max_bytes": 100}
    assert me.json()["avatar_url"] is None
