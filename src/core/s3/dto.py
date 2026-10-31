from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    data: bytes
    content_type: str
