from src.core.errors import (
    IntegrationBadResponseError,
    IntegrationTimeoutError,
    IntegrationUnavailableError,
)


class S3UnavailableError(IntegrationUnavailableError):
    code = "storage.unavailable"
    message = "Хранилище файлов недоступно"


class S3TimeoutError(IntegrationTimeoutError):
    code = "storage.timeout"
    message = "Хранилище файлов не ответило вовремя"


class S3BadResponseError(IntegrationBadResponseError):
    code = "storage.bad_response"
    message = "Хранилище файлов отказало в операции"
