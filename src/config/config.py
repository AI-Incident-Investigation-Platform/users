from pathlib import Path
from urllib.parse import quote

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

BASE_DIR = Path(__file__).parent.parent.parent
TOML_SETTINGS_PATH = BASE_DIR / "config.toml"

PATHS_SOURCES: list[tuple[Path, type[PydanticBaseSettingsSource]]] = [
    (TOML_SETTINGS_PATH, TomlConfigSettingsSource),
]


class Service(BaseModel):
    name: str = "users"
    # тег образа, его подставляет сборка; на хосте — dev
    version: str = "dev"
    port: int = 8004
    bind_host: str = "127.0.0.1"
    # предел замерен на auth (закон Литтла); для users не перемерялся
    max_concurrent_requests: int = Field(default=64, ge=1)
    overload_retry_after_seconds: int = Field(default=2, ge=1)


class Database(BaseModel):
    postgres_username: str = ""
    postgres_db: str = ""
    postgres_port: int = 5432
    postgres_host: str = ""
    postgres_password: str = ""
    # постоянный пул без overflow: соединения сверх пула открывались и закрывались на каждом пике
    pool_size: int = Field(default=10, ge=1)
    pool_max_overflow: int = Field(default=0, ge=0)
    pool_timeout_seconds: float = Field(default=2, gt=0)
    pool_recycle_seconds: int = Field(default=1800, ge=1)
    statement_timeout_ms: int = Field(default=5000, ge=1)
    lock_timeout_ms: int = Field(default=2000, ge=1)

    @property
    def async_database_url(self) -> str:
        user = quote(self.postgres_username, safe="")
        password = quote(self.postgres_password, safe="")
        return f"postgresql+asyncpg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


class Cache(BaseModel):
    host: str = ""
    port: int = 6379
    password: str = ""
    db: int = 0
    key_prefix: str = "users:"
    timeout_seconds: float = 2

    @property
    def url(self) -> str:
        credentials = f"default:{quote(self.password, safe='')}@" if self.password else ""
        return f"redis://{credentials}{self.host}:{self.port}/{self.db}"


class Tracing(BaseModel):
    enabled: bool = True
    otlp_endpoint: str = ""


class Auth(BaseModel):
    jwks_url: str = ""
    # API auth внутри кластера: почта пользователя, когда профиль ещё не создан событием
    url: str = "http://auth.apps:8001"
    issuer: str = "auth"
    audience: str = "aiip"
    jwks_timeout_seconds: float = Field(default=2, gt=0)
    # неизвестный kid перечитывает JWKS не чаще раза в этот интервал: чужой токен не заваливает auth
    jwks_refresh_interval_seconds: int = Field(default=30, ge=1)
    # пропуск живой сессии ведёт auth в своём префиксе кэша
    session_key_prefix: str = "auth:session:"
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost", "https://localhost"]
    )


class S3(BaseModel):
    endpoint_url: str = ""
    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""
    region: str = "us-east-1"
    connect_timeout_seconds: float = Field(default=2, gt=0)
    read_timeout_seconds: float = Field(default=5, gt=0)


class Avatars(BaseModel):
    # фронтенд обрезает и сжимает картинку до загрузки; больше — уже не аватар
    max_bytes: int = Field(default=1_048_576, ge=1)
    # адрес аватара меняется с каждой загрузкой, поэтому браузер кэширует его надолго
    cache_max_age_seconds: int = Field(default=86_400 * 30, ge=0)


class Rabbitmq(BaseModel):
    url: str = ""
    connect_timeout_seconds: float = Field(default=5, gt=0)
    reconnect_delay_seconds: float = Field(default=5, gt=0)
    publish_timeout_seconds: float = Field(default=2, gt=0)


class AuthEvents(BaseModel):
    """Очередь событий auth о пользователях: регистрация и смена почты."""

    exchange: str = "auth.events"
    queue: str = "users.auth-events"
    prefetch: int = Field(default=10, ge=1)
    retry_delay_seconds: int = Field(default=5, ge=1)
    # без события у пользователя нет профиля: недоступную БД ждём минуты, а не секунды
    max_attempts: int = Field(default=60, ge=1)
    dead_letter_ttl_days: int = Field(default=14, ge=1)
    # параллельное событие того же пользователя или занятое между проверкой и записью имя
    conflict_retries: int = Field(default=3, ge=1)


class Usernames(BaseModel):
    # фильтр Блума растёт сам; ёмкость — сколько имён он держит с заданной долей ложных «занято»
    bloom_capacity: int = Field(default=100_000, ge=1)
    bloom_error_rate: float = Field(default=0.001, gt=0, lt=1)
    rebuild_lock_seconds: int = Field(default=30, ge=1)
    generate_attempts: int = Field(default=10, ge=1)


class Search(BaseModel):
    default_limit: int = Field(default=20, ge=1)
    max_limit: int = Field(default=50, ge=1)
    lookup_max_ids: int = Field(default=100, ge=1)


class Logging(BaseModel):
    level: str = "INFO"
    slow_request_ms: int = 1000


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        toml_file=TOML_SETTINGS_PATH,
        env_nested_delimiter="__",
    )

    service: Service = Service()
    database: Database = Database()
    cache: Cache = Cache()
    tracing: Tracing = Tracing()
    auth: Auth = Auth()
    s3: S3 = S3()
    avatars: Avatars = Avatars()
    rabbitmq: Rabbitmq = Rabbitmq()
    auth_events: AuthEvents = AuthEvents()
    usernames: Usernames = Usernames()
    search: Search = Search()
    logging: Logging = Logging()

    def missing_required(self) -> list[str]:
        required = {
            "database.postgres_host": self.database.postgres_host,
            "database.postgres_db": self.database.postgres_db,
            "database.postgres_username": self.database.postgres_username,
            "cache.host": self.cache.host,
            "auth.jwks_url": self.auth.jwks_url,
            "rabbitmq.url": self.rabbitmq.url,
            "s3.endpoint_url": self.s3.endpoint_url,
            "s3.access_key": self.s3.access_key,
            "s3.secret_key": self.s3.secret_key,
            "s3.bucket": self.s3.bucket,
        }
        if self.tracing.enabled:
            required["tracing.otlp_endpoint"] = self.tracing.otlp_endpoint
        return [name for name, value in required.items() if not value]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        active_sources = [method(settings_cls) for path, method in PATHS_SOURCES if path.exists()]
        return EnvSettingsSource(settings_cls), *active_sources


cfg = Config()
