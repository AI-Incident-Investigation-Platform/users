import logging
import re
import secrets
from uuid import UUID

from src.config import cfg
from src.core.cache.exc import CacheUnavailableError
from src.core.cache.service import CacheService
from src.core.db.uow import UnitOfWork
from src.core.errors import ErrorReport, InternalError

log = logging.getLogger(__name__)


class Usernames:
    """Занятость юзернеймов: фильтр Блума в кэше перед уникальным индексом БД.

    Фильтр отвечает «точно свободно» без похода в БД; «возможно занято» уточняет
    БД. Источник правды — уникальный индекс: фильтр только экономит запросы.
    Нет фильтра — его пересобирает из БД один под под замком, а пока ответ даёт
    БД. Кэш недоступен — тоже БД: проверка имени не ломается вместе с кэшем.
    Освобождённое при переименовании имя остаётся в фильтре и уточняется БД.
    """

    def __init__(self, uow: UnitOfWork, cache: CacheService) -> None:
        self._uow = uow
        self._cache = cache

    async def is_taken(self, username: str, except_user_id: UUID | None = None) -> bool:
        if await self._filter_says_free(username):
            return False
        return await self._uow.users.username_exists(username, except_user_id)

    async def generate(self, email: str) -> str:
        """Свободный юзернейм из начала почты, при занятом — с цифрами в конце."""
        base = self._base_from_email(email)
        candidates = [base] + [
            f"{base}{secrets.randbelow(10**digits):0{digits}d}" for digits in self._digit_counts()
        ]
        for candidate in candidates:
            if not await self.is_taken(candidate):
                return candidate
        raise InternalError({"reason": "username_space_exhausted"})

    async def remember(self, username: str) -> None:
        """Добавляет занятое имя в фильтр после commit; сбой кэша имя не теряет — правда в БД."""
        try:
            await self._cache.bloom_add_if_exists(self._key(), username)
        except CacheUnavailableError as exc:
            log.warning(
                "Юзернейм не добавлен в фильтр Блума",
                extra={
                    "event": "usernames.filter_add_failed",
                    "error": ErrorReport.from_exception(exc).to_log(),
                },
            )

    async def _filter_says_free(self, username: str) -> bool:
        try:
            contains = await self._cache.bloom_check(self._key(), username)
            if contains is None:
                await self._rebuild()
                return False
        except CacheUnavailableError as exc:
            log.warning(
                "Фильтр Блума недоступен, занятость имени проверяет БД",
                extra={
                    "event": "usernames.filter_unavailable",
                    "error": ErrorReport.from_exception(exc).to_log(),
                },
            )
            return False
        return not contains

    async def _rebuild(self) -> None:
        lock = f"{self._key()}:lock"
        if not await self._cache.try_lock(lock, cfg.usernames.rebuild_lock_seconds):
            return
        try:
            await self._cache.bloom_replace(
                self._key(),
                self._uow.users.stream_usernames(batch_size=1000),
                capacity=cfg.usernames.bloom_capacity,
                error_rate=cfg.usernames.bloom_error_rate,
            )
        finally:
            await self._cache.delete([lock])
        log.info("Фильтр Блума юзернеймов пересобран", extra={"event": "usernames.filter_rebuilt"})

    @staticmethod
    def _digit_counts() -> list[int]:
        # треть попыток с двумя цифрами, треть с четырьмя, остальные с шестью:
        # «yuri42» приятнее «yuri482139», а длинный хвост почти всегда свободен
        attempts = cfg.usernames.generate_attempts
        return [2 + 2 * (index * 3 // attempts) for index in range(attempts)]

    @staticmethod
    def _base_from_email(email: str) -> str:
        local = email.partition("@")[0].partition("+")[0].lower()
        base = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", local)).strip("-")[:24].strip("-")
        return base if len(base) >= 3 else f"user{base}"[:24]

    @staticmethod
    def _key() -> str:
        return f"{cfg.cache.key_prefix}usernames:bloom"
