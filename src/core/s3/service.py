from src.core.s3.client import S3Client
from src.core.s3.dto import StoredObject


class S3Service:
    def __init__(self, client: S3Client) -> None:
        self._client = client

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await self._client.put_object(key, data, content_type)

    async def get(self, key: str) -> StoredObject | None:
        """Объект по ключу; нет такого — None."""
        stored = await self._client.get_object(key)
        if stored is None:
            return None
        data, content_type = stored
        return StoredObject(data=data, content_type=content_type)

    async def delete(self, key: str) -> None:
        """Удаляет объект; удаление отсутствующего — не ошибка."""
        await self._client.delete_object(key)
