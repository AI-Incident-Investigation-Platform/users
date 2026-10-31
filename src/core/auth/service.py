import json
from uuid import UUID

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidKeyError

from src.core.auth.client import AuthClient
from src.core.auth.dto import Account
from src.core.auth.exc import AuthBadResponseError


class AuthService:
    def __init__(self, client: AuthClient) -> None:
        self._client = client

    async def fetch_signing_keys(self) -> dict[str, RSAPublicKey]:
        """Публичные ключи подписи access-токенов из JWKS сервиса auth по `kid`."""
        try:
            document = json.loads(await self._client.get_jwks())
            keys: dict[str, RSAPublicKey] = {}
            for jwk in document["keys"]:
                if jwk.get("alg") != "RS256" or jwk.get("use", "sig") != "sig":
                    continue
                key = RSAAlgorithm.from_jwk(jwk)
                if isinstance(key, RSAPublicKey):
                    keys[str(jwk["kid"])] = key
        except (ValueError, KeyError, TypeError, InvalidKeyError) as exc:
            raise AuthBadResponseError({"reason": "malformed_jwks"}) from exc
        return keys

    async def get_account(self, access_token: str) -> Account:
        """Id и почта пользователя из auth."""
        try:
            data = json.loads(await self._client.get_me(access_token))
            return Account(user_id=UUID(data["id"]), email=str(data["email"]).lower())
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthBadResponseError({"reason": "malformed_me"}) from exc
