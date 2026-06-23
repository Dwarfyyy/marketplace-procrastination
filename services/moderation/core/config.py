from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	DATABASE_URL: str = "sqlite+aiosqlite:///./moderation.db"
	B2B_URL: str = "http://b2b:8000"
	MOD_TO_B2B_KEY: str = ""
	B2B_SERVICE_KEY: str = ""
	OUTBOX_WORKER_ENABLED: bool = True
	OUTBOX_POLL_INTERVAL_SECONDS: float = 1.0

	model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
