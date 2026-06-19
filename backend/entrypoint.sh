#!/bin/sh
# Apply any pending DB migrations, then start the API. This keeps the deployed
# schema in lock-step with the code on every release (local `migrate` compose
# service does the same for dev). alembic/env.py resolves the DB URL from
# DATABASE_URL or, in production, from Key Vault via app.config.
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
