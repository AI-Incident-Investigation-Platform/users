import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KEY_ID = "test-key"


def issue_access_token(user_id: UUID, session_id: UUID, **overrides: Any) -> str:
    """Access-токен, как его выпускает auth; `overrides` подменяет claims и `kid`."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": "auth",
        "aud": "aiip",
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    kid = overrides.pop("kid", KEY_ID)
    key = overrides.pop("key", SIGNING_KEY)
    payload.update(overrides)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def jwks_document() -> bytes:
    jwk = RSAAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True)
    return json.dumps({"keys": [{**jwk, "kid": KEY_ID, "use": "sig", "alg": "RS256"}]}).encode()


# почта аккаунтов для /api/v1/auth/me тестового auth: id пользователя → почта
ACCOUNTS: dict[str, str] = {}


class _JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/v1/auth/me":
            self._me()
            return
        body = jwks_document()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _me(self) -> None:
        token = self.headers.get("Authorization", "").removeprefix("Bearer ")
        user_id = jwt.decode(token, options={"verify_signature": False})["sub"]
        if user_id not in ACCOUNTS:
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps({"id": user_id, "email": ACCOUNTS[user_id], "created_at": "x"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@contextmanager
def jwks_server() -> Iterator[str]:
    """auth на localhost: JWKS тестового ключа и `/auth/me` из ACCOUNTS; отдаёт адрес JWKS."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _JwksHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/.well-known/jwks.json"
    finally:
        server.shutdown()
        server.server_close()
