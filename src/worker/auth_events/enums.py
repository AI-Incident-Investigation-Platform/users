from enum import StrEnum


class UserEventType(StrEnum):
    """Событие auth о пользователе; значение — routing key в exchange событий auth."""

    REGISTERED = "user.registered"
    EMAIL_CHANGED = "user.email_changed"


class EventOutcome(StrEnum):
    APPLIED = "applied"
    STALE = "stale"
    RETRIED = "retried"
    DEAD = "dead"
