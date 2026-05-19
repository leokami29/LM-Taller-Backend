import json
from typing import Any, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors_origins(v: Any) -> list[str]:
    """Acepta lista, JSON array en string, o valores separados por comas (desde .env)."""
    if v is None or v == "":
        return ["http://localhost:3000", "http://localhost:8000"]
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x) for x in parsed]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in s.split(",") if part.strip()]
    return ["http://localhost:3000", "http://localhost:8000"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_NAME: str = "SGtaller Web API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql://sgtaller:sgtaller_password@localhost:5432/sgtaller_db"

    USE_TENANT_DATABASE_ROUTING: bool = Field(default=False, validation_alias="USE_TENANT_DATABASE_ROUTING")
    CATALOG_DATABASE_URL: Optional[str] = Field(default=None, validation_alias="CATALOG_DATABASE_URL")
    TENANT_DATABASE_URL_MAP_JSON: str = Field(default="{}", validation_alias="TENANT_DATABASE_URL_MAP_JSON")
    TENANT_ENGINE_CACHE_MAX: int = Field(default=24, validation_alias="TENANT_ENGINE_CACHE_MAX")
    TENANT_RESOLVER_CACHE_TTL_SEC: int = Field(default=60, validation_alias="TENANT_RESOLVER_CACHE_TTL_SEC")

    REDIS_URL: str = "redis://localhost:6379"

    SECRET_KEY: str = "dev-secret-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    LICENSE_SIGNING_PRIVATE_KEY_B64: str = ""
    LICENSE_SIGNING_PUBLIC_KEY_B64: str = ""

    # En .env va como string (coma o JSON); no usar list[str] aquí: pydantic-settings intenta json.loads antes.
    cors_origins_raw: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        validation_alias="CORS_ORIGINS",
    )

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "sgtaller"
    MINIO_USE_SSL: bool = False

    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@sgtaller.com"

    @computed_field
    @property
    def tenant_database_url_map(self) -> dict[str, str]:
        """Mapa opcional company_id (UUID str) → URL de Postgres del tenant (JSON en env)."""
        raw = self.TENANT_DATABASE_URL_MAP_JSON.strip()
        if not raw or raw == "{}":
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            return {}

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return _parse_cors_origins(self.cors_origins_raw)


settings = Settings()
