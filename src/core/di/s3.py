from collections.abc import AsyncIterator

from aiobotocore.session import get_session
from botocore.config import Config
from dishka import Provider, Scope, provide

from src.config import cfg
from src.core.s3.client import S3Client
from src.core.s3.service import S3Service


class S3Provider(Provider):
    s3_service = provide(S3Service, scope=Scope.APP)

    @provide(scope=Scope.APP)
    async def get_client(self) -> AsyncIterator[S3Client]:
        async with get_session().create_client(
            "s3",
            endpoint_url=cfg.s3.endpoint_url,
            aws_access_key_id=cfg.s3.access_key,
            aws_secret_access_key=cfg.s3.secret_key,
            region_name=cfg.s3.region,
            config=Config(
                s3={"addressing_style": "path"},
                connect_timeout=cfg.s3.connect_timeout_seconds,
                read_timeout=cfg.s3.read_timeout_seconds,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        ) as client:
            yield S3Client(client)
