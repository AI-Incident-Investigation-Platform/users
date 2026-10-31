import base64
import binascii
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, Self
from uuid import UUID

from src.core.db.exc import InvalidCursorError


class _Identified(Protocol):
    @property
    def id(self) -> UUID: ...


@dataclass(frozen=True)
class Page[T]:
    """Страница по ключу: порядок — id (UUIDv7 растёт со временем), курсор — последний id."""

    items: tuple[T, ...]
    next_cursor: str | None

    @classmethod
    def from_rows[R: _Identified](
        cls, rows: Sequence[R], limit: int, convert: Callable[[R], T]
    ) -> Self:
        """Собирает страницу из `limit + 1` строк: лишняя строка значит, что есть следующая."""
        items = tuple(convert(row) for row in rows[:limit])
        has_more = len(rows) > limit
        next_cursor = Page.encode_cursor(rows[limit - 1].id) if has_more else None
        return cls(items=items, next_cursor=next_cursor)

    @staticmethod
    def encode_cursor(last_id: UUID) -> str:
        return base64.urlsafe_b64encode(last_id.bytes).decode().rstrip("=")

    @staticmethod
    def decode_cursor(cursor: str | None) -> UUID | None:
        if cursor is None:
            return None
        try:
            return UUID(bytes=base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        except (binascii.Error, ValueError) as exc:
            raise InvalidCursorError({"cursor_length": len(cursor)}) from exc
