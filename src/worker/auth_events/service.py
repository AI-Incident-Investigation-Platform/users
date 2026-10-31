from src.core.profiles.enums import ProfileSync
from src.core.profiles.service import Profiles
from src.worker.auth_events.dto import UserEvent
from src.worker.auth_events.enums import EventOutcome


class AuthEventsService:
    """Профиль из событий auth: регистрация создаёт его, смена почты обновляет копию почты.

    Оба события значат одно и обрабатываются одинаково, поэтому повтор, дубль и обгон
    событий ничего не портят.
    """

    def __init__(self, profiles: Profiles) -> None:
        self._profiles = profiles

    async def apply(self, event: UserEvent) -> EventOutcome:
        synced = await self._profiles.sync(event.user_id, event.email, event.occurred_at)
        return EventOutcome.STALE if synced == ProfileSync.STALE else EventOutcome.APPLIED
