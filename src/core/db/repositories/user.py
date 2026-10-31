from collections.abc import AsyncIterator, Collection, Sequence
from uuid import UUID

from sqlalchemy import func, or_, select

from src.core.db.models.user import User
from src.core.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_for_update(self, user_id: UUID) -> User | None:
        return await self._session.scalar(select(User).where(User.id == user_id).with_for_update())

    async def list_by_ids(self, user_ids: Collection[UUID]) -> Sequence[User]:
        query = select(User).where(User.id.in_(user_ids)).order_by(User.id)
        return (await self._session.scalars(query)).all()

    async def username_exists(self, username: str, except_user_id: UUID | None = None) -> bool:
        query = select(User.id).where(User.username == username)
        if except_user_id is not None:
            query = query.where(User.id != except_user_id)
        return await self._session.scalar(query.limit(1)) is not None

    async def search(self, text: str, after: UUID | None, limit: int) -> Sequence[User]:
        """Юзернейм или почта начинаются с `text`, либо имя его содержит; порядок — id."""
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = (
            select(User)
            .where(
                or_(
                    User.username.like(f"{escaped}%"),
                    User.email.like(f"{escaped}%"),
                    func.lower(User.display_name).like(f"%{escaped}%"),
                )
            )
            .order_by(User.id)
            .limit(limit)
        )
        if after is not None:
            query = query.where(User.id > after)
        return (await self._session.scalars(query)).all()

    async def stream_usernames(self, batch_size: int) -> AsyncIterator[Sequence[str]]:
        result = await self._session.stream_scalars(
            select(User.username).execution_options(yield_per=batch_size)
        )
        async for batch in result.partitions():
            yield batch
