from dishka import Provider, Scope, provide

from src.api.users.service import UserService
from src.core.profiles.service import Profiles
from src.core.usernames.service import Usernames
from src.worker.auth_events.service import AuthEventsService


class UsersProvider(Provider):
    usernames = provide(Usernames, scope=Scope.REQUEST)
    profiles = provide(Profiles, scope=Scope.REQUEST)
    user_service = provide(UserService, scope=Scope.REQUEST)
    auth_events_service = provide(AuthEventsService, scope=Scope.REQUEST)
