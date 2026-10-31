# users

Сервис пользователей AIIP: всё о человеке внутри продукта. Профиль —
юзернейм, аватар, имя, часовой пояс, рабочее время; поиск людей по юзернейму, почте
и имени; профили пачкой для списков участников. Входа не ведёт: аккаунт,
почта и сессии — в `auth`. Профиль создаётся по событию `user.registered`
из `auth`, почта в профиле — копия, которую обновляет `user.email_changed`.

Работает в namespace `apps` кластера `aiip`, снаружи — за Traefik на
`/api/v1/users`. Данные — своя БД в Postgres, бакет `users` в SeaweedFS
(аватары), префикс `users:` в Dragonfly (фильтр Блума юзернеймов), события
`auth` — очередь `users.auth-events` в RabbitMQ.

## Документация

- [docs/endpoints.md](docs/endpoints.md) — карта эндпоинтов и событий: что,
  кому, с какими ошибками.
- [docs/design.md](docs/design.md) — профиль из событий, юзернеймы и фильтр
  Блума, поиск, принятые решения.
- [docs/requirements.md](docs/requirements.md) — что требует документация
  продукта и что из этого реализовано.

## Стек

Python 3.14, uv, FastAPI на uvicorn с uvloop и httptools, dishka, SQLAlchemy 2.0 async + asyncpg, Alembic,
pydantic-settings, redis-клиент к Dragonfly, aio-pika к RabbitMQ, aiobotocore к SeaweedFS, httpx к `auth`, PyJWT,
OpenTelemetry, prometheus-client.

## Запуск

Нужны Docker, `k3d`, `kubectl`, поднятая инфра (`make -C ../infra up`) и
выкаченный `auth`: без его JWKS запросы с токеном получают `503`, а без его
событий профили не появляются.

```bash
make config          # первый раз: config.toml из выдачи инфры
make up              # образ → кластер, миграции Job'ом, RollingUpdate с откатом
make ps              # поды, нагрузка, решение автоскейлера
make logs
make down            # убрать Deployment, Service и маршрут; секрет остаётся
```

На хосте без Docker: `make -C ../infra forward` в соседнем терминале и
`make run` в `auth`, затем `make upgrade` и `make run` — сервис на
`localhost:8004`, мимо Traefik.

## Проверка

```bash
make check             # ruff format --check + ruff check + mypy
make test              # unit, без Docker
make test-integration  # Postgres, Dragonfly, RabbitMQ и SeaweedFS в Testcontainers; auth — тестовый сервер на localhost
make test-all
```

Миграции: `make migrate MSG="..."` (нужен `forward`), `make upgrade`,
`make downgrade REV=<rev>`. Полный список целей — `make help`.

## Конфиг и секреты

`config.toml` (не в git) собирается из `config.toml.example` и блока,
который печатает `make -C ../infra service name=users`. Переменные
окружения перекрывают его (вложенность через `__`). В кластере он лежит в
Secret `users` и монтируется файлом.
