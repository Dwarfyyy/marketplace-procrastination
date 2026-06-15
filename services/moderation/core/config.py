from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	DATABASE_URL: str
	DEBUG: bool = False
	DATABASE_VERBOSE: bool = False

	# Service-to-service key expected from B2B on POST /api/v1/events/product
	B2B_SERVICE_KEY: str = ""

	# JWT settings for moderator-facing endpoints (shared with other services)
	SECRET_KEY: str = ""
	ALGORITHM: str = "HS256"

	# Outgoing service-to-service call to B2B's POST /api/v1/moderation/events
	B2B_BASE_URL: str = "http://b2b:8000"
	B2B_MODERATION_SERVICE_KEY: str = ""

	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		extra="allow",
		case_sensitive=False,
	)


settings = Settings()
