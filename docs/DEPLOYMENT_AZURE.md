# Deploying HireIQ to Azure

A step-by-step, copy-pasteable guide to take HireIQ from local Docker Compose to a
production deployment on **Azure Container Apps (ACA)**, with every secret stored in
**Azure Key Vault** and read at runtime via the container's **managed identity** (no
secrets in env files or images).

> **Nothing about the application code changes between local and prod.** The behaviour
> is switched entirely by environment variables (see [§11 Local vs. production parity](#11-local-vs-production-parity)).
> Locally: `ENV=development`, email logs to the console, files on disk, secrets from dev Vault.
> Prod: `ENV=production`, email via Resend, files in Blob Storage, secrets from Key Vault.

---

## 1. Architecture: what runs where

Three container images, built from this repo:

| Image | Source | Port | Ingress | Talks to |
|---|---|---|---|---|
| `hireiq-api` | `backend/Dockerfile` | 8000 | **external** (public FQDN) | Postgres, Redis, Blob, Key Vault, `agents` |
| `hireiq-agents` | `agents/Dockerfile` | 8001 | **internal only** | OpenAI, Azure Speech, Key Vault |
| `hireiq-frontend` | `frontend/Dockerfile` (nginx) | 80 | **external** (public FQDN) | the browser → `hireiq-api` |

Backing Azure services you will provision:

| Azure service | Why HireIQ needs it | Maps to setting(s) |
|---|---|---|
| **PostgreSQL Flexible Server** (+ `pgvector`) | Primary DB, multi-tenant RLS, CV/job vector search | `DATABASE_URL` |
| **Azure Cache for Redis** | Interview session state, email dedup, rate limits | `REDIS_URL` |
| **Storage Account** (Blob) | CV files & audio blobs | `AZURE_STORAGE_CONNECTION_STRING`, `STORAGE_BACKEND=azure` |
| **Key Vault** | Holds every secret; apps read via managed identity | `AZURE_KEYVAULT_URL` |
| **Container Apps Environment** | Runs the 3 images | — |
| **Container Registry** (ACR) *or* Docker Hub | Stores the built images | — |
| **Azure AI Speech** (F0 free) | Voice interview STT/TTS | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` |
| **Azure AI Document Intelligence** (F0 free) | OCR for image/scanned CVs | `AZURE_FORM_RECOGNIZER_*` |
| **Resend** (3rd-party, free tier) | Sends candidate emails | `EMAIL_BACKEND=resend`, `EMAIL_API_KEY`, `EMAIL_FROM` |
| **OpenAI** | LLM for all agents | `OPENAI_API_KEY` |

> **About email / Resend.** Resend (https://resend.com) is a transactional-email API.
> Its free tier is **3,000 emails/month (100/day)** — ample for HireIQ. It is not an
> Azure product but works from anywhere. Dev logs emails to the console
> (`EMAIL_BACKEND=console`); prod sends them (`EMAIL_BACKEND=resend`).

---

## 2. Prerequisites (install once)

```bash
# Azure CLI + the Container Apps extension
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Docker (to build images) and a registry account (Docker Hub or ACR)
docker login        # Docker Hub, OR `az acr login --name <registry>` for ACR
```

You also need: an **OpenAI API key**, a **domain name** you control (for Resend +
optionally custom app URLs).

---

## 3. Set shell variables (reuse them throughout)

```bash
# --- pick these ---
export LOCATION="eastus"
export RG="hireiq-prod"
export PREFIX="hireiq"                       # used to name resources
export DOCKERHUB_NAMESPACE="yourdockerhubuser"   # or your ACR login server
export IMAGE_TAG="v1.0.0"

# --- generated names ---
export KV_NAME="${PREFIX}-kv-$RANDOM"        # Key Vault names are globally unique
export PG_NAME="${PREFIX}-pg-$RANDOM"
export REDIS_NAME="${PREFIX}-redis-$RANDOM"
export STORAGE_NAME="${PREFIX}store$RANDOM"  # 3-24 lowercase alphanumeric, globally unique
export ACA_ENV="${PREFIX}-env"

az group create --name "$RG" --location "$LOCATION"
```

---

## 4. PostgreSQL Flexible Server (+ pgvector)

```bash
# Choose a strong admin password
export PG_ADMIN="hireiq_admin"
export PG_PASSWORD="$(openssl rand -base64 20)"

az postgres flexible-server create \
  --resource-group "$RG" --name "$PG_NAME" --location "$LOCATION" \
  --admin-user "$PG_ADMIN" --admin-password "$PG_PASSWORD" \
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 \
  --version 16 --database-name hireiq --public-access 0.0.0.0

# Enable the pgvector extension (required for CV/job similarity search)
az postgres flexible-server parameter set \
  --resource-group "$RG" --server-name "$PG_NAME" \
  --name azure.extensions --value VECTOR

# Build the asyncpg URL HireIQ expects (note: +asyncpg, sslmode=require)
export PG_HOST="$(az postgres flexible-server show -g "$RG" -n "$PG_NAME" --query fullyQualifiedDomainName -o tsv)"
export DATABASE_URL="postgresql+asyncpg://${PG_ADMIN}:${PG_PASSWORD}@${PG_HOST}:5432/hireiq?ssl=require"
```

> `--public-access 0.0.0.0` opens the server to Azure services for first setup. For a
> hardened deployment, place Postgres on a VNet and give the Container Apps environment
> a delegated subnet instead.

---

## 5. Azure Cache for Redis

```bash
az redis create \
  --resource-group "$RG" --name "$REDIS_NAME" --location "$LOCATION" \
  --sku Basic --vm-size c0

export REDIS_KEY="$(az redis list-keys -g "$RG" -n "$REDIS_NAME" --query primaryKey -o tsv)"
export REDIS_HOST="${REDIS_NAME}.redis.cache.windows.net"
# Azure Redis requires TLS on 6380 → use the rediss:// scheme
export REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:6380/0"
```

---

## 6. Storage Account (CV & audio blobs)

```bash
az storage account create \
  --resource-group "$RG" --name "$STORAGE_NAME" --location "$LOCATION" \
  --sku Standard_LRS --kind StorageV2

export AZURE_STORAGE_CONNECTION_STRING="$(az storage account show-connection-string \
  -g "$RG" -n "$STORAGE_NAME" --query connectionString -o tsv)"

# Create the container HireIQ uploads into (default name: hireiq)
az storage container create --name hireiq \
  --connection-string "$AZURE_STORAGE_CONNECTION_STRING"
```

---

## 7. (Optional) Azure AI Speech + Document Intelligence

Skip if you don't need voice interviews or image/scanned-CV OCR — HireIQ degrades
gracefully (text interview fallback; PDF/DOCX-only CVs).

```bash
# Speech (free F0): voice interview STT/TTS
az cognitiveservices account create \
  --resource-group "$RG" --name "${PREFIX}-speech" --location "$LOCATION" \
  --kind SpeechServices --sku F0 --yes
export AZURE_SPEECH_KEY="$(az cognitiveservices account keys list -g "$RG" -n "${PREFIX}-speech" --query key1 -o tsv)"
export AZURE_SPEECH_REGION="$LOCATION"

# Document Intelligence (free F0): OCR for JPG/PNG/scanned CVs
az cognitiveservices account create \
  --resource-group "$RG" --name "${PREFIX}-docintel" --location "$LOCATION" \
  --kind FormRecognizer --sku F0 --yes
export AZURE_FORM_RECOGNIZER_ENDPOINT="$(az cognitiveservices account show -g "$RG" -n "${PREFIX}-docintel" --query properties.endpoint -o tsv)"
export AZURE_FORM_RECOGNIZER_KEY="$(az cognitiveservices account keys list -g "$RG" -n "${PREFIX}-docintel" --query key1 -o tsv)"
```

---

## 8. Resend (candidate email)

1. Sign up at https://resend.com (free).
2. **Add a domain** you own (e.g. `hireiq.io`) under *Domains → Add Domain*, then add
   the shown **SPF, DKIM, and DMARC** DNS records at your registrar. Wait for "Verified".
   - No domain yet? You can test with Resend's `onboarding@resend.dev` sender, but it
     only delivers to your own account email. Use a verified domain for real candidates.
3. Create an **API key** (*API Keys → Create*). Copy it once.
4. Pick your `From` address on the verified domain.

```bash
export EMAIL_API_KEY="re_xxxxxxxxxxxxxxxxx"
export EMAIL_FROM="HireIQ <noreply@hireiq.io>"   # must be on your verified domain
export OPENAI_API_KEY="sk-..."                    # your OpenAI key
export JWT_SECRET="$(openssl rand -hex 32)"
export AGENTS_INTERNAL_SECRET="$(openssl rand -hex 32)"
```

---

## 9. Key Vault: store every secret

The app code (`backend/app/config.py → _load_from_azure_keyvault`) reads these **exact
secret names**. They are dash-cased.

```bash
az keyvault create --resource-group "$RG" --name "$KV_NAME" --location "$LOCATION"
export AZURE_KEYVAULT_URL="https://${KV_NAME}.vault.azure.net/"

kv() { az keyvault secret set --vault-name "$KV_NAME" --name "$1" --value "$2" >/dev/null && echo "  set $1"; }

kv openai-api-key                     "$OPENAI_API_KEY"
kv jwt-secret                         "$JWT_SECRET"
kv agents-internal-secret             "$AGENTS_INTERNAL_SECRET"
kv database-url                       "$DATABASE_URL"
kv redis-url                          "$REDIS_URL"
kv email-api-key                      "$EMAIL_API_KEY"
kv azure-storage-connection-string    "$AZURE_STORAGE_CONNECTION_STRING"
# Only if you provisioned them in §7:
kv azure-speech-key                   "${AZURE_SPEECH_KEY:-}"
kv azure-speech-region                "${AZURE_SPEECH_REGION:-$LOCATION}"
kv azure-form-recognizer-endpoint     "${AZURE_FORM_RECOGNIZER_ENDPOINT:-}"
kv azure-form-recognizer-key          "${AZURE_FORM_RECOGNIZER_KEY:-}"
```

> **Why this works:** with `ENV=production`, `config.py` ignores env/`.env` for secrets
> and pulls each of the names above from Key Vault using `DefaultAzureCredential`, which
> resolves to the container app's managed identity (granted access in §10).

---

## 10. Build, push, and deploy the three apps

### 10a. Build & push images

```bash
# Build for the cloud platform (linux/amd64) and push to your registry
docker build --platform linux/amd64 -t "$DOCKERHUB_NAMESPACE/hireiq-api:$IMAGE_TAG"    backend
docker build --platform linux/amd64 -t "$DOCKERHUB_NAMESPACE/hireiq-agents:$IMAGE_TAG" agents

# Frontend: the browser calls the API directly, so the API URL is baked in at build time.
# We don't know the API FQDN until its app exists — so we deploy api first (10c),
# capture its FQDN, then build the frontend (10e).

docker push "$DOCKERHUB_NAMESPACE/hireiq-api:$IMAGE_TAG"
docker push "$DOCKERHUB_NAMESPACE/hireiq-agents:$IMAGE_TAG"
```

### 10b. Create the Container Apps environment

```bash
az containerapp env create \
  --resource-group "$RG" --name "$ACA_ENV" --location "$LOCATION"
```

### 10c. Deploy `api` (external ingress) + `agents` (internal)

```bash
# agents — internal only (no public ingress)
az containerapp create \
  --resource-group "$RG" --name "${PREFIX}-agents" --environment "$ACA_ENV" \
  --image "$DOCKERHUB_NAMESPACE/hireiq-agents:$IMAGE_TAG" \
  --target-port 8001 --ingress internal \
  --system-assigned \
  --env-vars ENV=production AZURE_KEYVAULT_URL="$AZURE_KEYVAULT_URL" AZURE_SPEECH_REGION="$LOCATION"

# api — external, reaches agents over the internal name
az containerapp create \
  --resource-group "$RG" --name "${PREFIX}-api" --environment "$ACA_ENV" \
  --image "$DOCKERHUB_NAMESPACE/hireiq-api:$IMAGE_TAG" \
  --target-port 8000 --ingress external \
  --system-assigned \
  --env-vars ENV=production AZURE_KEYVAULT_URL="$AZURE_KEYVAULT_URL" \
             AGENTS_BASE_URL="http://${PREFIX}-agents" \
             STORAGE_BACKEND=azure AZURE_STORAGE_CONTAINER=hireiq \
             EMAIL_BACKEND=resend EMAIL_FROM="$EMAIL_FROM" \
             INTERVIEW_LINK_EXPIRY_HOURS=48 \
             FRONTEND_ORIGIN="https://placeholder"   # fixed in §10f
```

### 10d. Grant both apps read access to Key Vault

```bash
for app in "${PREFIX}-api" "${PREFIX}-agents"; do
  PID="$(az containerapp show -g "$RG" -n "$app" --query identity.principalId -o tsv)"
  az keyvault set-policy --name "$KV_NAME" --object-id "$PID" --secret-permissions get list
done
# Restart so they pick up secrets on next boot
az containerapp revision restart -g "$RG" -n "${PREFIX}-api"    --revision "$(az containerapp show -g "$RG" -n "${PREFIX}-api"    --query properties.latestRevisionName -o tsv)"
az containerapp revision restart -g "$RG" -n "${PREFIX}-agents" --revision "$(az containerapp show -g "$RG" -n "${PREFIX}-agents" --query properties.latestRevisionName -o tsv)"

export API_FQDN="$(az containerapp show -g "$RG" -n "${PREFIX}-api" --query properties.configuration.ingress.fqdn -o tsv)"
echo "API is at: https://$API_FQDN"
```

### 10e. Build & deploy the frontend (now that the API FQDN is known)

The browser calls the API directly, so Vite must bake the API URL in at build time.
**Add build args to `frontend/Dockerfile`** (one-time):

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL
ARG VITE_WS_URL
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_WS_URL=$VITE_WS_URL
RUN npm run build
# ... (nginx stage unchanged)
```

Then build, push, deploy:

```bash
docker build --platform linux/amd64 \
  --build-arg VITE_API_URL="https://$API_FQDN" \
  --build-arg VITE_WS_URL="wss://$API_FQDN" \
  -t "$DOCKERHUB_NAMESPACE/hireiq-frontend:$IMAGE_TAG" frontend
docker push "$DOCKERHUB_NAMESPACE/hireiq-frontend:$IMAGE_TAG"

az containerapp create \
  --resource-group "$RG" --name "${PREFIX}-frontend" --environment "$ACA_ENV" \
  --image "$DOCKERHUB_NAMESPACE/hireiq-frontend:$IMAGE_TAG" \
  --target-port 80 --ingress external

export FRONTEND_FQDN="$(az containerapp show -g "$RG" -n "${PREFIX}-frontend" --query properties.configuration.ingress.fqdn -o tsv)"
echo "Frontend is at: https://$FRONTEND_FQDN"
```

> **Alternative (keep the nginx proxy, API stays private):** instead of baking
> `VITE_API_URL`, set the **api** ingress to `internal`, and change the two
> `proxy_pass http://api:8000/` lines in `frontend/nginx.conf` to
> `proxy_pass http://${PREFIX}-api/` (ACA internal DNS, port 80). Then the frontend
> serves the API under its own origin at `/api` and `/ws` — no CORS needed. Pick one
> model; the direct-FQDN approach above is simpler to reason about.

### 10f. Point CORS at the real frontend origin

```bash
az containerapp update -g "$RG" -n "${PREFIX}-api" \
  --set-env-vars FRONTEND_ORIGIN="https://$FRONTEND_FQDN"
```

---

## 11. Run database migrations

The `api` image ships Alembic. Run the migrations once as a short-lived Container Apps
**job** (same image, same Key Vault identity), or exec into the running app:

```bash
# One-off exec (quickest):
az containerapp exec -g "$RG" -n "${PREFIX}-api" --command "alembic upgrade head"
```

> If `exec` is unavailable in your environment, create a Container Apps **Job** from the
> same `hireiq-api` image with command `["alembic","upgrade","head"]`, the same
> `ENV=production` + `AZURE_KEYVAULT_URL` env and a system-assigned identity granted
> Key Vault `get` access, then `az containerapp job start`.

---

## 12. Custom domains (optional but recommended)

Map friendly hostnames (e.g. `app.hireiq.io`, `api.hireiq.io`) to the two external apps:

```bash
az containerapp hostname add     -g "$RG" -n "${PREFIX}-frontend" --hostname app.hireiq.io
az containerapp hostname bind    -g "$RG" -n "${PREFIX}-frontend" --hostname app.hireiq.io --environment "$ACA_ENV"
# repeat for api.hireiq.io on ${PREFIX}-api
```

After binding, **rebuild the frontend** with `VITE_API_URL=https://api.hireiq.io` and
**update** `FRONTEND_ORIGIN=https://app.hireiq.io` on the api (CORS).

---

## 13. Smoke test the deployment

1. `curl https://$API_FQDN/health` → `{"status":"ok"}`.
2. Open `https://$FRONTEND_FQDN`, register a company, create + activate a job.
3. Apply as a candidate with a CV:
   - **Qualified** → candidate receives the **interview invitation** email with a link
     valid **48 hours** (`INTERVIEW_LINK_EXPIRY_HOURS`).
   - **Not qualified** → candidate receives the **warm rejection** email.
4. Complete an interview → after evaluation:
   - **`hire`** recommendation → candidate gets *"our team will be in touch"* email.
   - otherwise → candidate gets the **feedback report** email (valid 30 days).
5. Check delivery in the Resend dashboard → *Emails*.

---

## 14. Local vs. production parity

Everything is env-driven; **no code differs** between the two.

| Concern | Local (`ENV=development`) | Production (`ENV=production`) | Switch |
|---|---|---|---|
| Secrets source | dev HashiCorp Vault / `.env` | Azure Key Vault (managed identity) | `ENV` |
| Email | logged to console | sent via Resend | `EMAIL_BACKEND` |
| File storage | local disk `./storage` | Azure Blob | `STORAGE_BACKEND` |
| Database | Docker Postgres | Postgres Flexible Server | `DATABASE_URL` |
| Redis | Docker Redis | Azure Cache for Redis | `REDIS_URL` |
| Agents URL | `http://localhost:8001` | `http://hireiq-agents` (internal) | `AGENTS_BASE_URL` |
| Interview link TTL | 48 h | 48 h | `INTERVIEW_LINK_EXPIRY_HOURS` |
| CORS origin | `http://localhost:3000` | frontend FQDN | `FRONTEND_ORIGIN` |

To run locally exactly as before: `cd infra && cp .env.example .env && docker compose up`.

---

## 15. Environment variable reference

**Stored in Key Vault** (dash-cased name → setting), read automatically in prod:

| Key Vault secret | Setting | Where to get it |
|---|---|---|
| `openai-api-key` | `OPENAI_API_KEY` | platform.openai.com → API keys |
| `jwt-secret` | `JWT_SECRET` | `openssl rand -hex 32` |
| `agents-internal-secret` | `AGENTS_INTERNAL_SECRET` | `openssl rand -hex 32` |
| `database-url` | `DATABASE_URL` | §4 (built from Postgres admin + host) |
| `redis-url` | `REDIS_URL` | §5 (built from Redis key + host) |
| `email-api-key` | `EMAIL_API_KEY` | Resend → API Keys (§8) |
| `azure-storage-connection-string` | `AZURE_STORAGE_CONNECTION_STRING` | §6 |
| `azure-speech-key` / `azure-speech-region` | `AZURE_SPEECH_*` | §7 (optional) |
| `azure-form-recognizer-endpoint` / `-key` | `AZURE_FORM_RECOGNIZER_*` | §7 (optional) |

**Set directly on the container app** (non-secret config):

| Env var | api | agents | Value |
|---|---|---|---|
| `ENV` | ✓ | ✓ | `production` |
| `AZURE_KEYVAULT_URL` | ✓ | ✓ | `https://<kv>.vault.azure.net/` |
| `AGENTS_BASE_URL` | ✓ | | `http://hireiq-agents` |
| `STORAGE_BACKEND` | ✓ | | `azure` |
| `AZURE_STORAGE_CONTAINER` | ✓ | | `hireiq` |
| `EMAIL_BACKEND` | ✓ | | `resend` |
| `EMAIL_FROM` | ✓ | | `HireIQ <noreply@yourdomain>` |
| `INTERVIEW_LINK_EXPIRY_HOURS` | ✓ | | `48` (default) |
| `FRONTEND_ORIGIN` | ✓ | | frontend public URL (CORS) |
| `AZURE_SPEECH_REGION` | | ✓ | `eastus` |
| `VITE_API_URL` / `VITE_WS_URL` | frontend **build args** | | api FQDN (§10e) |
