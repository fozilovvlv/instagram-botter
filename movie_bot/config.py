import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    database_url: str
    movie_channel_id: int
    port: int = 8080
    sleep_warning: str | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        missing = [
            name
            for name in ("BOT_TOKEN", "ADMIN_IDS", "MOVIE_CHANNEL_ID")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        admin_ids = cls.parse_admin_ids(os.environ["ADMIN_IDS"])
        database_url = os.getenv("DATABASE_URL", "sqlite:///data/movies.db")
        provider = os.getenv("HOSTING_PROVIDER", "").lower()
        production = provider or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER")
        if production and database_url.startswith("sqlite"):
            raise RuntimeError(
                "Production requires a persistent PostgreSQL DATABASE_URL; "
                "SQLite storage is ephemeral on free hosting."
            )

        warning = None
        if provider == "render" or os.getenv("RENDER"):
            warning = (
                "Deployment warning: Render free web services sleep after 15 minutes "
                "without inbound traffic, and free Render Postgres expires after 30 days. "
                "Migrate to a non-sleeping provider before relying on this bot 24/7."
            )

        return cls(
            bot_token=os.environ["BOT_TOKEN"],
            admin_ids=admin_ids,
            database_url=cls.normalize_database_url(database_url),
            movie_channel_id=int(os.environ["MOVIE_CHANNEL_ID"]),
            port=int(os.getenv("PORT", "8080")),
            sleep_warning=warning,
        )

    @staticmethod
    def parse_admin_ids(value: str) -> frozenset[int]:
        try:
            ids = frozenset(int(item.strip()) for item in value.split(",") if item.strip())
        except ValueError as exc:
            raise RuntimeError("ADMIN_IDS must be comma-separated Telegram user IDs") from exc
        if not ids:
            raise RuntimeError("ADMIN_IDS must contain at least one Telegram user ID")
        return ids

    @staticmethod
    def normalize_database_url(value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value
