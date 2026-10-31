from src.api.exc.users import AvatarInvalidError, AvatarTooLargeError
from src.api.users.enums import AvatarFormat
from src.config import cfg


class AvatarImageParser:
    """Проверяет загруженный аватар: размер и формат по сигнатуре файла, а не по заголовку."""

    @staticmethod
    def parse(data: bytes, declared_type: str | None) -> AvatarFormat:
        if len(data) > cfg.avatars.max_bytes:
            raise AvatarTooLargeError({"size": len(data)}, {"max_bytes": cfg.avatars.max_bytes})
        detected = AvatarImageParser._detect(data)
        if detected is None:
            raise AvatarInvalidError({"size": len(data)})
        declared = (declared_type or "").split(";")[0].strip().lower()
        if declared != detected.value:
            raise AvatarInvalidError({"declared": declared[:64], "detected": detected.value})
        return detected

    @staticmethod
    def _detect(data: bytes) -> AvatarFormat | None:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return AvatarFormat.PNG
        if data.startswith(b"\xff\xd8\xff"):
            return AvatarFormat.JPEG
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return AvatarFormat.WEBP
        return None
