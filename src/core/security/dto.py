from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    session_id: UUID
    # токен уходит дальше в вызовы других сервисов от имени пользователя; в repr и логи — нет
    access_token: str = field(repr=False)
