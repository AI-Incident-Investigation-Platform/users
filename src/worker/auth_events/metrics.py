from prometheus_client import Counter

AUTH_EVENTS = Counter(
    "users_auth_events_total",
    "События auth о пользователях по исходу обработки",
    ["type", "outcome"],
)
