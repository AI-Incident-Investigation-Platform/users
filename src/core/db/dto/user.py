from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Self
from uuid import UUID


@dataclass(frozen=True)
class WorkingHours:
    """Рабочее время в часовом поясе пользователя; `ends_at` раньше `starts_at` — ночная смена."""

    starts_at: time
    ends_at: time
    days: tuple[int, ...]


@dataclass(frozen=True)
class UserDTO:
    id: UUID
    email: str
    username: str
    display_name: str | None
    timezone: str
    working_hours: WorkingHours | None
    avatar_id: UUID | None
    onboarded_at: datetime | None
    created_at: datetime

    @classmethod
    def from_orm(cls, obj: Any) -> Self:
        working_hours = (
            WorkingHours(
                starts_at=obj.work_starts_at, ends_at=obj.work_ends_at, days=tuple(obj.work_days)
            )
            if obj.work_starts_at is not None
            else None
        )
        return cls(
            id=obj.id,
            email=obj.email,
            username=obj.username,
            display_name=obj.display_name,
            timezone=obj.timezone,
            working_hours=working_hours,
            avatar_id=obj.avatar_id,
            onboarded_at=obj.onboarded_at,
            created_at=obj.created_at,
        )
