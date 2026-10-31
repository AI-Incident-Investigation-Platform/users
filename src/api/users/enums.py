from enum import StrEnum


class AvatarFormat(StrEnum):
    """Принимаемые форматы аватара; значение — MIME-тип."""

    PNG = "image/png"
    JPEG = "image/jpeg"
    WEBP = "image/webp"
