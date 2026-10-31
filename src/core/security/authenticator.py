from uuid import UUID

import jwt

from src.config import cfg
from src.core.context import bind_log_identity
from src.core.security.dto import CurrentUser
from src.core.security.exc import NotAuthenticatedError
from src.core.security.live_sessions import LiveSessions
from src.core.security.signing_keys import SigningKeys


class SessionAuthenticator:
    """Проверяет access-токен auth локально: подпись по JWKS, claims и живость сессии."""

    def __init__(self, signing_keys: SigningKeys, live_sessions: LiveSessions) -> None:
        self._signing_keys = signing_keys
        self._live_sessions = live_sessions

    async def authenticate(
        self, authorization: str | None, cookie_token: str | None
    ) -> CurrentUser:
        access_token = self._bearer_token(authorization) or cookie_token
        if not access_token:
            raise NotAuthenticatedError
        try:
            kid = jwt.get_unverified_header(access_token).get("kid")
        except jwt.PyJWTError as exc:
            raise NotAuthenticatedError from exc
        if not isinstance(kid, str) or (key := await self._signing_keys.get(kid)) is None:
            raise NotAuthenticatedError({"reason": "unknown_kid"})
        try:
            payload = jwt.decode(
                access_token,
                key,
                algorithms=["RS256"],
                issuer=cfg.auth.issuer,
                audience=cfg.auth.audience,
                options={"require": ["iss", "aud", "sub", "sid", "iat", "exp"]},
            )
            user = CurrentUser(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                access_token=access_token,
            )
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise NotAuthenticatedError from exc
        bind_log_identity(user.user_id, user.session_id)
        if not await self._live_sessions.is_live(user.session_id):
            raise NotAuthenticatedError
        return user

    @staticmethod
    def _bearer_token(authorization: str | None) -> str | None:
        scheme, _, token = (authorization or "").partition(" ")
        return token if scheme.lower() == "bearer" else None
