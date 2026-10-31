import logging
from datetime import datetime
from uuid import UUID

from src.config import cfg
from src.core.db.exc import IntegrityViolationError
from src.core.db.models.user import User
from src.core.db.uow import UnitOfWork
from src.core.errors import InternalError
from src.core.profiles.enums import ProfileSync
from src.core.usernames.service import Usernames

log = logging.getLogger(__name__)


class Profiles:
    """Профиль по сведениям auth: «у пользователя такая почта на такой момент».

    Профиля нет — он создаётся с юзернеймом из почты; есть — почта меняется, только
    если сведения новее записанных. Так событие, его повтор, обгон и чтение
    `auth/me` при отсутствии профиля сходятся к одному состоянию.
    """

    def __init__(self, uow: UnitOfWork, usernames: Usernames) -> None:
        self._uow = uow
        self._usernames = usernames

    async def sync(self, user_id: UUID, email: str, as_of: datetime) -> ProfileSync:
        for _ in range(cfg.auth_events.conflict_retries):
            user = await self._uow.users.get_for_update(user_id)
            if user is not None:
                return await self._sync_email(user, email, as_of)
            try:
                user = await self._create(user_id, email, as_of)
            except IntegrityViolationError as exc:
                await self._uow.rollback()
                if exc.constraint not in {"pk_users", "uq_users_username"}:
                    raise
                continue
            await self._usernames.remember(user.username)
            log.info(
                "Профиль пользователя создан",
                extra={"event": "users.profile_created", "user_id": str(user.id)},
            )
            return ProfileSync.CREATED
        raise InternalError({"user_id": str(user_id), "reason": "conflict_retries"})

    async def _create(self, user_id: UUID, email: str, as_of: datetime) -> User:
        user = User(
            id=user_id,
            email=email,
            email_synced_at=as_of,
            username=await self._usernames.generate(email),
        )
        self._uow.users.add(user)
        await self._uow.flush()
        await self._uow.commit()
        return user

    async def _sync_email(self, user: User, email: str, as_of: datetime) -> ProfileSync:
        if as_of <= user.email_synced_at:
            await self._uow.rollback()
            return ProfileSync.STALE
        user.email = email
        user.email_synced_at = as_of
        await self._uow.commit()
        log.info(
            "Почта в профиле обновлена",
            extra={"event": "users.email_synced", "user_id": str(user.id)},
        )
        return ProfileSync.UPDATED
