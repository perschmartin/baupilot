"""BauPilot — Anwendungskonfiguration via Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Zentrale Konfiguration, gelesen aus Umgebungsvariablen."""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "baupilot"
    postgres_password: str = "baupilot_dev"
    postgres_db: str = "baupilot"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_http_port: int = 6333

    # MinIO
    minio_host: str = "localhost"
    minio_api_port: int = 9000
    minio_root_user: str = "baupilot"
    minio_root_password: str = "baupilot_dev"

    # LiteLLM
    litellm_host: str = "localhost"
    litellm_port: int = 4000

    # Ollama
    ollama_host: str = "localhost"
    ollama_port: int = 11434

    # API
    api_secret_key: str = "dev_secret_change_me"
    api_cors_origins: list[str] = [
        "http://localhost:8091",
        "https://fli.baupilot.work",
    ]

    environment: str = "development"

    # Auth (AP 1.1)
    jwt_secret: str = "dev_jwt_secret_change_me"
    totp_key: str = "dev_totp_key_change_me_needs_64_hex_chars_0123456789abcdef"

    # Auth (AP 1.1)
    jwt_secret: str = "dev_jwt_secret_change_me"
    totp_key: str = "dev_totp_key_change_me_needs_64_hex_chars_0123456789abcdef"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
