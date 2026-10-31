from collections.abc import AsyncIterator

import httpx
from dishka import Provider, Scope, provide

from src.config import cfg
from src.core.auth.client import AuthClient
from src.core.auth.service import AuthService


class AuthProvider(Provider):
    auth_client = provide(AuthClient, scope=Scope.APP)
    auth_service = provide(AuthService, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def get_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        # Service балансирует соединения: короткий keep-alive даёт трафик новым подам auth
        async with httpx.AsyncClient(
            timeout=cfg.auth.jwks_timeout_seconds,
            limits=httpx.Limits(keepalive_expiry=30),
        ) as client:
            yield client
