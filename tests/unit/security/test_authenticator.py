from uuid import uuid7

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.config import cfg
from src.core.auth.exc import AuthUnavailableError
from src.core.cache.client import CacheClient
from src.core.cache.exc import CacheUnavailableError
from src.core.cache.service import CacheService
from src.core.security.authenticator import SessionAuthenticator
from src.core.security.exc import NotAuthenticatedError
from src.core.security.live_sessions import LiveSessions
from src.core.security.signing_keys import SigningKeys
from tests.support.tokens import KEY_ID, SIGNING_KEY, issue_access_token


class FakeAuth:
    """Точка контакта с сервисом auth: отдаёт ключи JWKS и считает обращения."""

    def __init__(self, keys: dict[str, RSAPublicKey] | None = None) -> None:
        self.keys = keys if keys is not None else {KEY_ID: SIGNING_KEY.public_key()}
        self.calls = 0
        self.unavailable = False

    async def fetch_signing_keys(self) -> dict[str, RSAPublicKey]:
        self.calls += 1
        if self.unavailable:
            raise AuthUnavailableError
        return self.keys


class FakeCache(CacheService):
    def __init__(self, live: set[str] | None = None, down: bool = False) -> None:
        self._live = live or set()
        self._down = down

    async def exists(self, key: str) -> bool:
        if self._down:
            raise CacheUnavailableError
        return key in self._live


def make_authenticator(
    auth: FakeAuth, cache: CacheService
) -> tuple[SessionAuthenticator, SigningKeys]:
    keys = SigningKeys(auth)  # type: ignore[arg-type]
    return SessionAuthenticator(keys, LiveSessions(cache)), keys


@pytest.mark.case(id="SEC-TOKEN-001")
async def test_valid_token_with_live_session_is_accepted() -> None:
    user_id, session_id = uuid7(), uuid7()
    cache = FakeCache({f"{cfg.auth.session_key_prefix}{session_id}"})
    authenticator, _ = make_authenticator(FakeAuth(), cache)

    user = await authenticator.authenticate(None, issue_access_token(user_id, session_id))

    assert (user.user_id, user.session_id) == (user_id, session_id)


@pytest.mark.case(id="SEC-TOKEN-002")
@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "other"},
        {"iss": "other"},
        {"exp": 0},
        {"key": rsa.generate_private_key(public_exponent=65537, key_size=2048)},
        {"kid": "unknown"},
    ],
    ids=["audience", "issuer", "expired", "foreign-key", "unknown-kid"],
)
async def test_foreign_or_expired_token_is_rejected(overrides: dict[str, object]) -> None:
    session_id = uuid7()
    cache = FakeCache({f"{cfg.auth.session_key_prefix}{session_id}"})
    authenticator, _ = make_authenticator(FakeAuth(), cache)

    with pytest.raises(NotAuthenticatedError):
        await authenticator.authenticate(None, issue_access_token(uuid7(), session_id, **overrides))


@pytest.mark.case(id="SEC-TOKEN-003")
async def test_revoked_session_is_rejected() -> None:
    authenticator, _ = make_authenticator(FakeAuth(), FakeCache())

    with pytest.raises(NotAuthenticatedError):
        await authenticator.authenticate(None, issue_access_token(uuid7(), uuid7()))


@pytest.mark.case(id="SEC-TOKEN-004")
async def test_unreachable_cache_rejects_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Redis(host="127.0.0.1", port=1)

    async def unreachable(*keys: str) -> int:
        raise RedisConnectionError("cache is down")

    monkeypatch.setattr(connection, "exists", unreachable)
    authenticator, _ = make_authenticator(FakeAuth(), CacheService(CacheClient(connection)))

    with pytest.raises(CacheUnavailableError):
        await authenticator.authenticate(None, issue_access_token(uuid7(), uuid7()))


@pytest.mark.case(id="SEC-JWKS-001")
async def test_unknown_kid_refreshes_jwks_at_most_once_per_interval() -> None:
    auth = FakeAuth(keys={})
    authenticator, keys = make_authenticator(auth, FakeCache())

    for _ in range(5):
        with pytest.raises(NotAuthenticatedError):
            await authenticator.authenticate(None, issue_access_token(uuid7(), uuid7()))
    assert auth.calls == 1

    auth.keys = {KEY_ID: SIGNING_KEY.public_key()}
    keys._refreshed_at = None  # интервал прошёл
    assert await keys.get(KEY_ID) is not None
    assert auth.calls == 2


@pytest.mark.case(id="SEC-JWKS-002")
async def test_unreachable_auth_is_service_unavailable_not_401() -> None:
    auth = FakeAuth()
    auth.unavailable = True
    authenticator, _ = make_authenticator(auth, FakeCache())

    with pytest.raises(AuthUnavailableError):
        await authenticator.authenticate(None, issue_access_token(uuid7(), uuid7()))
