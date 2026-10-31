from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from src.worker.auth_events.enums import UserEventType


class UserEventMessage(BaseModel):
    event_id: Annotated[str, Field(min_length=1, max_length=64)]
    type: UserEventType
    occurred_at: AwareDatetime
    user_id: UUID
    email: Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")]
