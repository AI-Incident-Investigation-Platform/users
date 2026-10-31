from collections.abc import Awaitable
from typing import Any

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    ReadTimeoutError,
)

from src.config import cfg
from src.core.s3.exc import S3BadResponseError, S3TimeoutError, S3UnavailableError


class S3Client:
    """Транспорт к S3-совместимому хранилищу (SeaweedFS) в бакете сервиса.

    Ошибки botocore переводятся в ошибки пакета; «объекта нет» — `None` у `get_object`.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        await self._call(
            self._client.put_object(
                Bucket=cfg.s3.bucket, Key=key, Body=data, ContentType=content_type
            ),
            key,
        )

    async def get_object(self, key: str) -> tuple[bytes, str] | None:
        try:
            response = await self._call(self._client.get_object(Bucket=cfg.s3.bucket, Key=key), key)
            async with response["Body"] as body:
                data = await body.read()
        except S3BadResponseError as exc:
            if exc.context.get("error_code") == "NoSuchKey":
                return None
            raise
        except (BotoCoreError, OSError) as exc:
            raise S3UnavailableError({"key": key}) from exc
        return data, str(response.get("ContentType", "application/octet-stream"))

    async def delete_object(self, key: str) -> None:
        await self._call(self._client.delete_object(Bucket=cfg.s3.bucket, Key=key), key)

    @staticmethod
    async def _call(request: Awaitable[Any], key: str) -> Any:
        try:
            return await request
        except (ConnectTimeoutError, ReadTimeoutError) as exc:
            raise S3TimeoutError({"key": key}) from exc
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            raise S3BadResponseError({"key": key, "error_code": error_code}) from exc
        except (BotoCoreError, OSError) as exc:
            raise S3UnavailableError({"key": key}) from exc
