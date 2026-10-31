import httpx

from src.config import cfg
from src.core.auth.exc import AuthBadResponseError, AuthUnavailableError


class AuthClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get_jwks(self) -> bytes:
        try:
            response = await self._http.get(cfg.auth.jwks_url)
        except httpx.HTTPError as exc:
            raise AuthUnavailableError({"url": cfg.auth.jwks_url}) from exc
        if response.status_code != httpx.codes.OK:
            raise AuthBadResponseError({"status": response.status_code})
        return response.content

    async def get_me(self, access_token: str) -> bytes:
        """Аккаунт пользователя от его имени: токен уходит в Authorization."""
        url = f"{cfg.auth.url}/api/v1/auth/me"
        try:
            response = await self._http.get(
                url, headers={"Authorization": f"Bearer {access_token}"}
            )
        except httpx.HTTPError as exc:
            raise AuthUnavailableError({"url": url}) from exc
        if response.is_server_error:
            raise AuthUnavailableError({"status": response.status_code})
        if response.status_code != httpx.codes.OK:
            raise AuthBadResponseError({"status": response.status_code})
        return response.content
