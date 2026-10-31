from dataclasses import dataclass

from src.core.db.dto.user import WorkingHours


@dataclass(frozen=True)
class ProfileChanges:
    """Частичное изменение профиля: None — поле не меняется.

    Имя и рабочее время можно очистить: присланные поля перечислены в `provided`,
    и присланный None их стирает.
    """

    provided: frozenset[str]
    username: str | None = None
    display_name: str | None = None
    timezone: str | None = None
    working_hours: WorkingHours | None = None
