from src.core.errors import IntegrationBadResponseError, IntegrationUnavailableError


class AuthUnavailableError(IntegrationUnavailableError):
    code = "auth.unavailable"
    message = "Сервис входа недоступен"


class AuthBadResponseError(IntegrationBadResponseError):
    code = "auth.bad_response"
    message = "Сервис входа вернул некорректный ответ"
