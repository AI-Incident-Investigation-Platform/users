from uuid import UUID

from src.config import cfg
from src.core.cache.service import CacheService


class LiveSessions:
    """Пропуска живых сессий, которые ведёт auth: нет ключа — сессия отозвана или истекла."""

    def __init__(self, cache: CacheService) -> None:
        self._cache = cache

    async def is_live(self, session_id: UUID) -> bool:
        return await self._cache.exists(f"{cfg.auth.session_key_prefix}{session_id}")
