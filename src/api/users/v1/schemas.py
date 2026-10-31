from datetime import datetime, time
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

# шаблон проверяется до перевода в нижний регистр, поэтому допускает заглавные
type Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{1,30}[A-Za-z0-9]$",
    ),
]

type DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class WorkingHoursSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: time
    ends_at: time
    days: list[Annotated[int, Field(ge=1, le=7)]] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.starts_at == self.ends_at:
            raise ValueError("начало и конец рабочего времени совпадают")
        if len(set(self.days)) != len(self.days):
            raise ValueError("дни недели повторяются")
        self.days = sorted(self.days)
        return self


class ProfileUpdateRequest(BaseModel):
    """Частичное изменение: не переданное поле не меняется.

    null очищает имя и рабочее время; юзернейм и часовой пояс null не принимают.
    """

    model_config = ConfigDict(extra="forbid")

    username: Username | None = None
    display_name: DisplayName | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    working_hours: WorkingHoursSchema | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, name: str | None) -> str | None:
        if name is None:
            return None
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("неизвестный часовой пояс") from exc
        return name

    @model_validator(mode="after")
    def _forbid_null(self) -> Self:
        nulls = [f for f in ("username", "timezone") if f in self.model_fields_set]
        if nulls := [f for f in nulls if getattr(self, f) is None]:
            raise ValueError(f"поля не могут быть null: {', '.join(nulls)}")
        return self


class UserResponse(BaseModel):
    id: UUID
    username: str
    display_name: str | None
    email: str
    timezone: str
    working_hours: WorkingHoursSchema | None
    avatar_id: UUID | None = Field(default=None, exclude=True)
    onboarded_at: datetime | None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avatar_url(self) -> str | None:
        """Адрес аватара с версией: новая загрузка — новый адрес, кэш браузера не мешает."""
        if self.avatar_id is None:
            return None
        return f"/api/v1/users/{self.id}/avatar?v={self.avatar_id}"


class UsersPageResponse(BaseModel):
    items: list[UserResponse]
    next_cursor: str | None


class UsersLookupResponse(BaseModel):
    items: list[UserResponse]


class UsernameAvailabilityResponse(BaseModel):
    username: str
    available: bool
