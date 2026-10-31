from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Account:
    user_id: UUID
    email: str
