from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.worker.auth_events.enums import UserEventType


@dataclass(frozen=True)
class UserEvent:
    """Событие несёт полное состояние почты, а не разницу: повтор и порядок ему не страшны."""

    event_id: str
    type: UserEventType
    occurred_at: datetime
    user_id: UUID
    email: str
