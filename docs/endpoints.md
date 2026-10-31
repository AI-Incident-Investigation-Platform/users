# Эндпоинты users

Снаружи — через Traefik: `http://localhost/api/v1/users...`. Внутри
кластера — `http://users:8004/api/v1/users...`. Служебные роуты (`/health`,
`/ready`, `/metrics`) живут вне `/api` и через gateway не публикуются.
Контракт — `contracts/openapi/main-public.openapi.yaml` и
`contracts/AUTH_BOUNDARY.md` в репозитории `docs`.

Gateway ограничивает сервис: 50 запросов/с, burst 100. Сверх предела
одновременных запросов пода (`service.max_concurrent_requests`, 64) сервис
отвечает `503` с `Retry-After`.

## Авторизация

Каждый роут `/api` требует access-токен `auth`: кука `access_token` из
браузера или `Authorization: Bearer` от другого сервиса (так `projects`
читает профили от имени пользователя). Изменяющий запрос с куки
принимается только с `Origin` из `auth.allowed_origins`. Любой вошедший
видит любой профиль: скрывать, кто зарегистрирован, продукт не требует.

## Публичные

| Метод и путь | Кто зовёт | Вход | Ответ |
|---|---|---|---|
| `GET /api/v1/users/me` | браузер | — | `200` `User`; профиля ещё нет — создаётся по почте из `auth` |
| `PATCH /api/v1/users/me` | браузер | `{username?, display_name?, timezone?, working_hours?}` | `200` `User`; первое сохранение ставит `onboarded_at` |
| `PUT /api/v1/users/me/avatar` | браузер | тело — картинка, `Content-Type` — её тип | `200` `User` с новым `avatar_url` |
| `DELETE /api/v1/users/me/avatar` | браузер | — | `204`; повтор — тоже `204` |
| `GET /api/v1/users/{user_id}/avatar` | браузер | `v` — версия из `avatar_url` | `200` картинка, `Cache-Control: private, max-age=2592000, immutable` |
| `GET /api/v1/users/username-availability` | браузер | `username` | `200` `{username, available}`; своё имя — свободно |
| `GET /api/v1/users` | браузер | `q` (1–100), `cursor`, `limit` (1–50, 20) | `200` `{items: [User], next_cursor}` |
| `GET /api/v1/users/lookup` | браузер, `projects` | `ids` (повторяется, 1–100) | `200` `{items: [User]}`; неизвестные id пропущены |
| `GET /api/v1/users/{user_id}` | браузер | — | `200` `User` |

- `User` — `{id, username, display_name, email, timezone, working_hours,
  avatar_url, onboarded_at, created_at}`. `avatar_url` — путь картинки с
  версией (`/api/v1/users/{id}/avatar?v=…`) или `null`: тогда фронтенд
  рисует инициалы.
- Аватар — PNG, JPEG или WebP до `avatars.max_bytes` (1 МиБ); формат
  проверяется по содержимому и должен совпадать с `Content-Type`. Обрезает
  и сжимает картинку фронтенд. Gateway обрывает тело больше 2 МиБ.
- `username` — 3–32 символа: латинские буквы, цифры, `-`, не по краям.
  Приводится к нижнему регистру, уникален.
- `timezone` — имя IANA (`Europe/Moscow`), до первого сохранения — `UTC`.
- `working_hours` — `{starts_at, ends_at, days}` в часовом поясе
  пользователя: время `HH:MM` на входе и `HH:MM:SS` в ответе, дни ISO
  (1 — понедельник). `ends_at` раньше `starts_at` — ночная смена, равные —
  ошибка. `null` — не задано.
- `PATCH /me` меняет только присланные поля. `null` очищает
  `display_name` и `working_hours`; для `username` и `timezone` `null` —
  `422`.
- Поиск `q`: начало юзернейма или почты, либо часть имени, без учёта
  регистра; `%` и `_` ищутся как символы. Порядок — время регистрации.
- Свой профиль есть всегда: если запрос пришёл раньше события
  `user.registered`, профиль создаётся сразу по почте из `GET
  /api/v1/auth/me` (с токеном пользователя), и позднее событие его не
  дублирует.

## События

| Очередь | Откуда | Что делает |
|---|---|---|
| `users.auth-events` ← `auth.events`, ключ `user.*` | `auth` | `user.registered` и `user.email_changed` `{event_id, type, occurred_at, user_id, email}`: создают профиль, если его нет, и записывают почту, если событие новее записанного |
| `users.auth-events.retry` | сам сервис | событие после временного отказа (БД, кэш) ждёт 5 с и возвращается в основную очередь; до 60 попыток |
| `users.auth-events.dead` | сам сервис | битое событие, непредвиденная ошибка или исчерпанные попытки; хранится 14 дней |

## Служебные

| Метод и путь | Кто зовёт | Ответ |
|---|---|---|
| `GET /health` | kubelet: liveness, startup | `200 {status: "ok"}`, зависимостей не проверяет |
| `GET /ready` | kubelet: readiness | `200`, если доступны Postgres и Dragonfly; иначе `503` |
| `GET /metrics` | Alloy | метрики Prometheus, в том числе `users_auth_events_total{type, outcome}` |

## Ошибки

Тело — конверт `error` из контракта: `{"error": {code, message,
request_id, details?}}`; `request_id` — `trace_id` запроса, он же в
заголовке `X-Request-ID`.

| Код | Статус | Когда |
|---|---|---|
| `security.not_authenticated` | 401 | токена нет, подпись, срок, `iss` или `aud` неверны, пропуска сессии нет |
| `security.origin_forbidden` | 403 | изменяющий запрос с куки без разрешённого `Origin` |
| `user.not_found` | 404 | пользователя нет |
| `user.avatar_not_found` | 404 | у пользователя нет аватара |
| `user.avatar_invalid` | 422 | тело не PNG, JPEG или WebP, либо не совпадает с `Content-Type` |
| `user.avatar_too_large` | 422 | картинка больше предела; `details.max_bytes` |
| `storage.unavailable`, `storage.timeout`, `storage.bad_response` | 503, 504, 502 | SeaweedFS недоступен, не ответил или отказал |
| `user.username_taken` | 409 | юзернейм занят |
| `request.invalid` | 422 | юзернейм, часовой пояс, рабочее время или параметры не прошли проверку; поля — в `details.errors` |
| `request.invalid_cursor` | 422 | курсор страницы испорчен |
| `auth.unavailable`, `auth.bad_response` | 503, 502 | ключ токена неизвестен, а JWKS `auth` не получить; или своего профиля нет, а `auth/me` не получить |
| `db.unavailable`, `cache.unavailable` | 503 | Postgres или Dragonfly недоступны |
| `service.overloaded` | 503 | под перегружен; заголовок `Retry-After` |
| `internal_error` | 500 | всё непредусмотренное; подробности только в логе |
