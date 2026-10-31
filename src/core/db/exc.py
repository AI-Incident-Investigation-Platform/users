from src.core.errors import (
    PersistenceConflictError,
    PersistenceUnavailableError,
    RuleViolationError,
)


class DatabaseUnavailableError(PersistenceUnavailableError):
    code = "db.unavailable"
    message = "База данных недоступна"


class IntegrityViolationError(PersistenceConflictError):
    code = "db.integrity_violation"
    message = "Нарушено ограничение целостности данных"

    def __init__(self, constraint: str | None) -> None:
        super().__init__({"constraint": constraint})
        self.constraint = constraint


class InvalidCursorError(RuleViolationError):
    code = "request.invalid_cursor"
    message = "Некорректный курсор страницы"
