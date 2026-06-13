from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


def _read_vault_secret(vault_addr: str, token: str, path: str, key: str) -> str:
    import hvac

    client = hvac.Client(url=vault_addr, token=token)
    secret = client.secrets.kv.v2.read_secret_version(path=path)
    return secret["data"]["data"][key]


def _read_azure_secret(secret_name: str) -> str:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    vault_url = os.environ["AZURE_KEYVAULT_URL"]
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)
    return client.get_secret(secret_name).value


class Settings(BaseSettings):
    ENV: Literal["development", "production", "test"] = "development"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://hireiq:hireiq@localhost:5432/hireiq"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Agents internal communication
    AGENTS_BASE_URL: str = "http://localhost:8001"
    AGENTS_INTERNAL_SECRET: str = "dev-internal-secret"

    # Azure Blob Storage
    STORAGE_BACKEND: Literal["local", "azure"] = "local"
    STORAGE_LOCAL_PATH: str = "./storage"
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "hireiq"

    # Azure Form Recognizer / Document Intelligence
    AZURE_FORM_RECOGNIZER_ENDPOINT: str = ""
    AZURE_FORM_RECOGNIZER_KEY: str = ""

    # Azure Speech (streaming STT/TTS — free F0 tier)
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""

    # Email
    EMAIL_BACKEND: Literal["console", "resend"] = "console"
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@hireiq.io"

    # Interview invitation link lifetime (hours)
    INTERVIEW_LINK_EXPIRY_HOURS: int = 48

    # HashiCorp Vault (dev)
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"
    VAULT_SECRETS_PATH: str = "hireiq/dev"

    # Frontend origin for CORS
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def load_secrets(self) -> None:
        """Pull secrets from Vault (dev) or Azure Key Vault (prod) at startup."""
        if self.ENV == "test":
            return
        if self.ENV == "development":
            self._load_from_vault()
        else:
            self._load_from_azure_keyvault()

    def _load_from_vault(self) -> None:
        try:
            import hvac  # noqa: F401
        except ImportError:
            return
        try:
            mapping = {
                "OPENAI_API_KEY": "openai_api_key",
                "JWT_SECRET": "jwt_secret",
                "AGENTS_INTERNAL_SECRET": "agents_internal_secret",
                "AZURE_SPEECH_KEY": "azure_speech_key",
                "AZURE_SPEECH_REGION": "azure_speech_region",
                "AZURE_FORM_RECOGNIZER_ENDPOINT": "azure_form_recognizer_endpoint",
                "AZURE_FORM_RECOGNIZER_KEY": "azure_form_recognizer_key",
            }
            for attr, key in mapping.items():
                value = _read_vault_secret(
                    self.VAULT_ADDR, self.VAULT_TOKEN, self.VAULT_SECRETS_PATH, key
                )
                object.__setattr__(self, attr, value)
        except Exception:
            pass  # Fall back to env values in dev

    def _load_from_azure_keyvault(self) -> None:
        try:
            mapping = {
                "OPENAI_API_KEY": "openai-api-key",
                "JWT_SECRET": "jwt-secret",
                "AGENTS_INTERNAL_SECRET": "agents-internal-secret",
                "DATABASE_URL": "database-url",
                "REDIS_URL": "redis-url",
                "EMAIL_API_KEY": "email-api-key",
                "AZURE_STORAGE_CONNECTION_STRING": "azure-storage-connection-string",
                "AZURE_SPEECH_KEY": "azure-speech-key",
                "AZURE_SPEECH_REGION": "azure-speech-region",
                "AZURE_FORM_RECOGNIZER_ENDPOINT": "azure-form-recognizer-endpoint",
                "AZURE_FORM_RECOGNIZER_KEY": "azure-form-recognizer-key",
            }
            for attr, secret_name in mapping.items():
                value = _read_azure_secret(secret_name)
                object.__setattr__(self, attr, value)
        except Exception as exc:
            raise RuntimeError(f"Failed to load secrets from Azure Key Vault: {exc}") from exc


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.load_secrets()
    return settings
