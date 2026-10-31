import asyncio
import time

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from src.config import cfg
from src.core.auth.service import AuthService


class SigningKeys:
    """Ключи подписи из JWKS auth в памяти процесса.

    Неизвестный `kid` (auth сменил ключ) перечитывает JWKS, но не чаще
    `jwks_refresh_interval_seconds`: поток токенов с выдуманным `kid` не
    превращается в поток запросов к auth.
    """

    def __init__(self, auth: AuthService) -> None:
        self._auth = auth
        self._keys: dict[str, RSAPublicKey] = {}
        self._refreshed_at: float | None = None
        self._refreshing = asyncio.Lock()

    async def get(self, kid: str) -> RSAPublicKey | None:
        if (key := self._keys.get(kid)) is not None:
            return key
        async with self._refreshing:
            if kid not in self._keys and self._refresh_allowed():
                self._refreshed_at = time.monotonic()
                self._keys = await self._auth.fetch_signing_keys()
        return self._keys.get(kid)

    def _refresh_allowed(self) -> bool:
        return (
            self._refreshed_at is None
            or time.monotonic() - self._refreshed_at >= cfg.auth.jwks_refresh_interval_seconds
        )
