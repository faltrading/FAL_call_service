from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SUPABASE_DB_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_PROJECT_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    API_GATEWAY_URL: str = "http://localhost:8001"
    ADMIN_USERNAME: str = "faltrading"
    ADMIN_EMAIL: str = "faltrade@protonmail.com"
    CALL_SERVICE_PORT: int = 8004
    JITSI_URL: str = ""
    JITSI_APP_ID: str = ""
    JITSI_APP_SECRET: str = ""

    @property
    def async_database_url(self) -> str:
        url = self.SUPABASE_DB_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def supabase_realtime_url(self) -> str:
        return self.SUPABASE_PROJECT_URL.replace("https://", "wss://") + "/realtime/v1"

    @property
    def jitsi_domain(self) -> str:
        url = self.JITSI_URL
        url = url.replace("https://", "").replace("http://", "")
        return url.rstrip("/")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
