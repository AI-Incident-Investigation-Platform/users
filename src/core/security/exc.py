from src.core.errors import ForbiddenError, UnauthenticatedError


class NotAuthenticatedError(UnauthenticatedError):
    code = "security.not_authenticated"
    message = "Требуется вход в систему"


class OriginForbiddenError(ForbiddenError):
    code = "security.origin_forbidden"
    message = "Запрос с этого адреса не принимается"
