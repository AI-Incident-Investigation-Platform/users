import logging
from collections.abc import Collection
from datetime import UTC, datetime
from uuid import UUID, uuid7

from src.api.exc.users import AvatarNotFoundError, UsernameTakenError, UserNotFoundError
from src.api.users.dto import ProfileChanges
from src.api.users.parser import AvatarImageParser
from src.core.auth.service import AuthService
from src.core.db.dto.user import UserDTO
from src.core.db.exc import IntegrityViolationError
from src.core.db.models.user import User
from src.core.db.pagination import Page
from src.core.db.uow import UnitOfWork
from src.core.errors import ErrorReport, IntegrationError, InternalError
from src.core.profiles.enums import ProfileSync
from src.core.profiles.service import Profiles
from src.core.s3.dto import StoredObject
from src.core.s3.service import S3Service
from src.core.security.dto import CurrentUser
from src.core.usernames.service import Usernames

log = logging.getLogger(__name__)


class UserService:
    """Профиль, аватар и поиск людей.

    Профиль обычно создаёт событие регистрации из auth. Если человек пришёл
    раньше события, свой профиль создаётся сразу по почте из `auth/me` — тем же
    путём, что событие, поэтому `GET /me` после регистрации не отвечает 404.
    Первое сохранение профиля человеком завершает онбординг (`onboarded_at`).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        usernames: Usernames,
        profiles: Profiles,
        auth: AuthService,
        s3: S3Service,
    ) -> None:
        self._uow = uow
        self._usernames = usernames
        self._profiles = profiles
        self._auth = auth
        self._s3 = s3

    async def get_me(self, current_user: CurrentUser) -> UserDTO:
        return UserDTO.from_orm(await self._own_profile(current_user))

    async def get_user(self, user_id: UUID) -> UserDTO:
        user = await self._uow.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError({"user_id": str(user_id)})
        return UserDTO.from_orm(user)

    async def update_profile(self, current_user: CurrentUser, changes: ProfileChanges) -> UserDTO:
        user = await self._own_profile(current_user)
        renamed = changes.username is not None and changes.username != user.username
        if renamed and await self._usernames.is_taken(changes.username or "", user.id):
            raise UsernameTakenError({"user_id": str(user.id)})
        if changes.username is not None:
            user.username = changes.username
        if changes.timezone is not None:
            user.timezone = changes.timezone
        if "display_name" in changes.provided:
            user.display_name = changes.display_name
        if "working_hours" in changes.provided:
            hours = changes.working_hours
            user.work_starts_at = hours.starts_at if hours else None
            user.work_ends_at = hours.ends_at if hours else None
            user.work_days = list(hours.days) if hours else None
        onboarded = user.onboarded_at is None
        if onboarded:
            user.onboarded_at = datetime.now(UTC)
        try:
            await self._uow.flush()
        except IntegrityViolationError as exc:
            if exc.constraint != "uq_users_username":
                raise
            raise UsernameTakenError({"user_id": str(user.id)}) from exc
        await self._uow.commit()
        if renamed:
            await self._usernames.remember(user.username)
        log.info(
            "Профиль сохранён",
            extra={
                "event": "users.profile_updated",
                "user_id": str(user.id),
                "renamed": renamed,
                "onboarded": onboarded,
            },
        )
        return UserDTO.from_orm(user)

    async def set_avatar(
        self, current_user: CurrentUser, data: bytes, content_type: str | None
    ) -> UserDTO:
        """Кладёт новый аватар под новым ключом, потом переключает профиль и удаляет старый.

        Новый ключ на каждую загрузку: адрес аватара меняется, и кэш браузера не
        показывает старую картинку.
        """
        image_format = AvatarImageParser.parse(data, content_type)
        user = await self._own_profile(current_user)
        await self._uow.rollback()
        avatar_id = uuid7()
        await self._s3.put(self._avatar_key(current_user.user_id, avatar_id), data, image_format)
        user = await self._own_profile(current_user)
        previous = user.avatar_id
        user.avatar_id = avatar_id
        user.avatar_content_type = image_format.value
        await self._uow.commit()
        log.info(
            "Аватар загружен",
            extra={"event": "users.avatar_set", "user_id": str(user.id), "size": len(data)},
        )
        await self._delete_object(user.id, previous)
        return UserDTO.from_orm(user)

    async def delete_avatar(self, current_user: CurrentUser) -> None:
        user = await self._own_profile(current_user)
        previous = user.avatar_id
        if previous is None:
            return
        user.avatar_id = None
        user.avatar_content_type = None
        await self._uow.commit()
        log.info("Аватар удалён", extra={"event": "users.avatar_deleted", "user_id": str(user.id)})
        await self._delete_object(user.id, previous)

    async def get_avatar(self, user_id: UUID) -> StoredObject:
        user = await self._uow.users.get_by_id(user_id)
        if user is None or user.avatar_id is None:
            raise AvatarNotFoundError({"user_id": str(user_id)})
        key = self._avatar_key(user_id, user.avatar_id)
        await self._uow.rollback()
        stored = await self._s3.get(key)
        if stored is None:
            raise AvatarNotFoundError({"user_id": str(user_id), "reason": "object_missing"})
        return stored

    async def is_username_available(self, current_user: CurrentUser, username: str) -> bool:
        """Свободен ли юзернейм; своё текущее имя считается свободным."""
        return not await self._usernames.is_taken(username, current_user.user_id)

    async def search(self, text: str, cursor: str | None, limit: int) -> Page[UserDTO]:
        rows = await self._uow.users.search(text.lower(), Page.decode_cursor(cursor), limit + 1)
        return Page.from_rows(rows, limit, UserDTO.from_orm)

    async def lookup(self, user_ids: Collection[UUID]) -> tuple[UserDTO, ...]:
        """Профили по списку id; неизвестные id пропускаются."""
        return tuple(UserDTO.from_orm(user) for user in await self._uow.users.list_by_ids(user_ids))

    async def _own_profile(self, current_user: CurrentUser) -> User:
        """Свой профиль под блокировкой; ещё нет — создаётся по почте из auth."""
        user = await self._uow.users.get_for_update(current_user.user_id)
        if user is not None:
            return user
        await self._uow.rollback()
        account = await self._auth.get_account(current_user.access_token)
        if account.user_id != current_user.user_id:
            raise InternalError(
                {"user_id": str(current_user.user_id), "reason": "auth_me_mismatch"}
            )
        synced = await self._profiles.sync(account.user_id, account.email, datetime.now(UTC))
        user = await self._uow.users.get_for_update(current_user.user_id)
        if user is None:
            raise InternalError({"user_id": str(current_user.user_id), "reason": "profile_missing"})
        if synced == ProfileSync.CREATED:
            log.info(
                "Профиль создан по запросу раньше события регистрации",
                extra={"event": "users.profile_created_on_demand", "user_id": str(user.id)},
            )
        return user

    async def _delete_object(self, user_id: UUID, avatar_id: UUID | None) -> None:
        """Удаляет прежний объект аватара; сбой оставляет мусор в бакете, но не ломает запрос."""
        if avatar_id is None:
            return
        try:
            await self._s3.delete(self._avatar_key(user_id, avatar_id))
        except IntegrationError as exc:
            log.warning(
                "Прежний аватар не удалён из хранилища",
                extra={
                    "event": "users.avatar_cleanup_failed",
                    "user_id": str(user_id),
                    "error": ErrorReport.from_exception(exc).to_log(),
                },
            )

    @staticmethod
    def _avatar_key(user_id: UUID, avatar_id: UUID) -> str:
        return f"avatars/{user_id}/{avatar_id}"
