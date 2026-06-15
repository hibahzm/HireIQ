#!/bin/sh
# One-shot Vault seeding for local dev.
#
# Reads secrets from the environment (injected from infra/.env via the
# `vault-init` compose service) and writes them into the dev Vault's KV v2 store
# at `secret/hireiq/dev` — the exact path/keys that backend & agents `config.py`
# read via `client.secrets.kv.v2.read_secret_version(path="hireiq/dev")`.
#
# Runs to completion and exits; api/agents wait for it via
# `depends_on: { condition: service_completed_successfully }`.
set -e

export VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-hireiq-dev-token}"

echo "init-vault: waiting for Vault at ${VAULT_ADDR} ..."
i=0
until vault status >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -gt 60 ] && { echo "init-vault: Vault not ready after 60s"; exit 1; }
  sleep 1
done

echo "init-vault: writing secrets to secret/hireiq/dev"
vault kv put secret/hireiq/dev \
  openai_api_key="${OPENAI_API_KEY:-}" \
  jwt_secret="${JWT_SECRET:-dev-secret-change-me}" \
  agents_internal_secret="${AGENTS_INTERNAL_SECRET:-dev-internal-secret}" \
  email_api_key="${EMAIL_API_KEY:-}" \
  azure_speech_key="${AZURE_SPEECH_KEY:-}" \
  azure_speech_region="${AZURE_SPEECH_REGION:-}" \
  azure_form_recognizer_endpoint="${AZURE_FORM_RECOGNIZER_ENDPOINT:-}" \
  azure_form_recognizer_key="${AZURE_FORM_RECOGNIZER_KEY:-}" \
  langfuse_public_key="${LANGFUSE_PUBLIC_KEY:-}" \
  langfuse_secret_key="${LANGFUSE_SECRET_KEY:-}" \
  langfuse_host="${LANGFUSE_HOST:-https://cloud.langfuse.com}"

echo "init-vault: done."
