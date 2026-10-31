from src.core.errors import ConflictError, NotFoundError, RuleViolationError


class UserNotFoundError(NotFoundError):
    """Пользователя нет; сразу после регистрации профиль появляется с задержкой события."""

    code = "user.not_found"
    message = "Пользователь не найден"


class UsernameTakenError(ConflictError):
    code = "user.username_taken"
    message = "Этот юзернейм уже занят"


class AvatarNotFoundError(NotFoundError):
    code = "user.avatar_not_found"
    message = "Аватара нет"


class AvatarInvalidError(RuleViolationError):
    code = "user.avatar_invalid"
    message = "Аватар должен быть картинкой PNG, JPEG или WebP с верным Content-Type"


class AvatarTooLargeError(RuleViolationError):
    code = "user.avatar_too_large"
    message = "Аватар слишком большой"
