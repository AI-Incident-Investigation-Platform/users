from datetime import datetime, time
from uuid import UUID

from sqlalchemy import CheckConstraint, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db.models.base import Base


class User(Base):
    """Профиль пользователя.

    id и почта приходят из auth событиями, остальное ведёт сам человек. Почта
    здесь — копия для поиска: владелец почты и входа — auth.
    """

    __table_args__ = (
        CheckConstraint(r"username ~ '^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$'", name="username_format"),
        CheckConstraint(
            "(work_starts_at IS NULL) = (work_ends_at IS NULL)"
            " AND (work_starts_at IS NULL) = (work_days IS NULL)",
            name="working_hours_complete",
        ),
        CheckConstraint(
            "(avatar_id IS NULL) = (avatar_content_type IS NULL)", name="avatar_complete"
        ),
        # поиск по началу почты и юзернейма: LIKE 'q%' идёт по индексу при любой collation
        Index("ix_users_email_pattern", "email", postgresql_ops={"email": "varchar_pattern_ops"}),
        Index(
            "ix_users_username_pattern",
            "username",
            postgresql_ops={"username": "varchar_pattern_ops"},
        ),
    )

    # id пользователя из auth, поэтому без default
    id: Mapped[UUID] = mapped_column(primary_key=True)
    # без уникальности: копии почт обновляются событиями не одновременно
    email: Mapped[str] = mapped_column(String(254))
    # время события auth, которое последним записало почту: старое событие её не откатит
    email_synced_at: Mapped[datetime]
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC")
    work_starts_at: Mapped[time | None]
    work_ends_at: Mapped[time | None]
    # дни недели ISO: 1 — понедельник, 7 — воскресенье
    work_days: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    # версия аватара: объект `avatars/<user_id>/<avatar_id>` в бакете сервиса
    avatar_id: Mapped[UUID | None]
    avatar_content_type: Mapped[str | None] = mapped_column(String(32))
    onboarded_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
