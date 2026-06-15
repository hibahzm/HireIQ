from __future__ import annotations

import contextlib
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

    # Langfuse LLM tracing (optional — tracing is disabled when keys are blank)
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

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
        self._load_optional_vault()

    def _load_optional_vault(self) -> None:
        """Best-effort: load optional secrets without aborting if any are absent."""
        optional = {
            "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
            "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
            "LANGFUSE_HOST": "langfuse_host",
        }
        for attr, key in optional.items():
            try:
                value = _read_vault_secret(
                    self.VAULT_ADDR, self.VAULT_TOKEN, self.VAULT_SECRETS_PATH, key
                )
                object.__setattr__(self, attr, value)
            except Exception:
                pass  # optional — leave default/blank

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
        # Optional secrets — never fail startup if they're not present.
        for attr, secret_name in {
            "LANGFUSE_PUBLIC_KEY": "langfuse-public-key",
            "LANGFUSE_SECRET_KEY": "langfuse-secret-key",
            "LANGFUSE_HOST": "langfuse-host",
        }.items():
            with contextlib.suppress(Exception):  # optional — leave default/blank
                object.__setattr__(self, attr, _read_azure_secret(secret_name))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.load_secrets()
    return settings
