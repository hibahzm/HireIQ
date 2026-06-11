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

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Internal auth — api service must present this header
    AGENTS_INTERNAL_SECRET: str = "dev-internal-secret"

    # Azure AI Speech (TTS fallback)
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = "eastus"

    # HashiCorp Vault (dev)
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"
    VAULT_SECRETS_PATH: str = "hireiq/dev"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def load_secrets(self) -> None:
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
                "AGENTS_INTERNAL_SECRET": "agents_internal_secret",
                "AZURE_SPEECH_KEY": "azure_speech_key",
                "AZURE_SPEECH_REGION": "azure_speech_region",
            }
            for attr, key in mapping.items():
                value = _read_vault_secret(
                    self.VAULT_ADDR, self.VAULT_TOKEN, self.VAULT_SECRETS_PATH, key
                )
                object.__setattr__(self, attr, value)
        except Exception:
            pass

    def _load_from_azure_keyvault(self) -> None:
        try:
            mapping = {
                "OPENAI_API_KEY": "openai-api-key",
                "AGENTS_INTERNAL_SECRET": "agents-internal-secret",
                "AZURE_SPEECH_KEY": "azure-speech-key",
                "AZURE_SPEECH_REGION": "azure-speech-region",
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
