from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	DATABASE_URL: str
	DEBUG: bool = False
	DATABASE_VERBOSE: bool

	SESSION_EXPIRE_SECONDS: int

	SECRET_KEY: str
	ALGORITHM: str

	B2B_SERVICE_KEY: str = ""
	B2B_BASE_URL: str = "http://b2b:8000"

	model_config = SettingsConfigDict(
		env_file=".env",
		env_file_encoding="utf-8",
		extra="allow",
		case_sensitive=False,  # Позволяет использовать database_url или DATABASE_URL
	)


settings = Settings()
