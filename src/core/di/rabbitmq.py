from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from src.core.rabbitmq.connection import RabbitmqConnection


class RabbitmqProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_connection(self) -> AsyncIterator[RabbitmqConnection]:
        connection = RabbitmqConnection()
        yield connection
        await connection.close()
