from fastapi import Response

from src.config import cfg


def cache_avatar(response: Response) -> None:
    """Аватар по адресу с версией не меняется: браузер держит его в кэше долго."""
    response.headers["Cache-Control"] = (
        f"private, max-age={cfg.avatars.cache_max_age_seconds}, immutable"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
