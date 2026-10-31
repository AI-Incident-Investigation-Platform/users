from enum import StrEnum


class ProfileSync(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    STALE = "stale"
