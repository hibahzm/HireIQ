# Deploying HireIQ to Azure — Portal (GUI) + GitHub Actions CI/CD

This guide provisions all infrastructure **once, through the Azure Portal (point-and-click)**,
then wires up **GitHub Actions** so that every push to `main` automatically builds the three
service images and rolls them out to Azure — no manual redeploys.

> **Code is identical between local and prod** — behaviour is switched by environment
> variables only (see [§9 Local vs production](#9-local-vs-production-parity)).
> Secrets live in **Azure Key Vault**; the apps read them at startup via their
> **managed identity** (nothing secret is stored in the repo or in env vars).

---

## 1. Architecture

Three images are built from this repo and deployed as three **Azure Container Apps**:

| App | Built from | Port | Ingress | Reaches |
|---|---|---|---|---|
| `hireiq-api` | `backend/Dockerfile` | 8000 | **External** (public URL) | Postgres, Redis, Blob, Key Vault, `agents` |
| `hireiq-agents` | `agents/Dockerfile` | 8001 | **Internal only** | OpenAI, Azure Speech, Key Vault |
| `hireiq-frontend` | `frontend/Dockerfile` (nginx) | 80 | **External** (public URL) | the browser → `hireiq-api` |

Backing services you create in the Portal:

| Service | Purpose | Setting it feeds |
|---|---|---|
| **Azure Database for PostgreSQL – Flexible Server** | Primary DB, multi-tenant RLS | `DATABASE_URL` |
| **Azure Cache for Redis** | Sessions, email dedup, rate limits | `REDIS_URL` |
| **Storage account (Blob)** | CV files & interview audio | `AZURE_STORAGE_CONNECTION_STRING` |
| **Key Vault** | Holds all secrets; apps read via managed identity | `AZURE_KEYVAULT_URL` |
| **Container Apps Environment** | Hosts the 3 apps | — |
| **Azure AI Speech** (F0 free) | Voice interview STT/TTS | `AZURE_SPEECH_KEY/REGION` |
| **Azure AI Document Intelligence** (F0 free) | OCR for image/scanned CVs | `AZURE_FORM_RECOGNIZER_*` |
| **Resend** (3rd-party, free tier) | Candidate emails | `EMAIL_API_KEY`, `EMAIL_FROM` |
| **OpenAI** | LLM for all agents | `OPENAI_API_KEY` |
| **Docker Hub** | Image registry GitHub Actions pushes to | — |

---

## 2. Prerequisites

- An **Azure subscription** (portal.azure.com).
- This repo on **GitHub** (you'll add Actions secrets).
- A **Docker Hub** account (free) — the registry CI pushes to.
- An **OpenAI API key**, a **Resend** account, and (optional) a **domain** you control.

---

# Part A — Provision infrastructure in the Azure Portal

Everything below is done in the GUI at **https://portal.azure.com**. Use the **top search bar**
to jump to each service. Put everything in **one region** (e.g. *East US*) and **one resource
group** so the apps can talk to each other and you can delete it all at once.

## A1. Resource group
1. Search **“Resource groups”** → **+ Create**.
2. Name `hireiq-prod`, Region *East US* → **Review + create** → **Create**.

## A2. PostgreSQL (Flexible Server) + pgvector
1. Search **“Azure Database for PostgreSQL flexible servers”** → **+ Create** → *Flexible server*.
2. Resource group `hireiq-prod`; Server name e.g. `hireiq-pg`; Region *East US*; **PostgreSQL version 16**.
3. Workload type **Development** (Burstable B1ms is fine to start).
4. Authentication **PostgreSQL authentication only**; set admin username `hireiq_admin` and a strong password — **save both**.
5. **Networking** tab → Connectivity **Public access** → tick **“Allow public access from any Azure service within Azure”** (or configure a VNet later). Add your own IP if you want to connect with a DB client.
6. **Review + create** → **Create**.
7. After it deploys: open the server → **Server parameters** → search **`azure.extensions`** → enable **VECTOR** → **Save**.
8. Build the connection string (you'll paste it into Key Vault in A5). Format HireIQ expects:
   ```
   postgresql+asyncpg://hireiq_admin:<PASSWORD>@hireiq-pg.postgres.database.azure.com:5432/postgres?ssl=require
   ```
   (Use the **Server name** from the Overview page; DB `postgres` exists by default, or create a `hireiq` database under **Databases**.)

## A3. Azure Cache for Redis
1. Search **“Azure Cache for Redis”** → **+ Create**.
2. Resource group `hireiq-prod`; DNS name e.g. `hireiq-redis`; Region *East US*; Cache type **Basic C0**.
3. **Create**. After deploy: open it → **Access keys** → copy the **Primary** key, and note the **Host name**.
4. Build the URL (TLS port 6380):
   ```
   rediss://:<PRIMARY_KEY>@hireiq-redis.redis.cache.windows.net:6380/0
   ```

## A4. Storage account (Blob) for CVs
1. Search **“Storage accounts”** → **+ Create**. Resource group `hireiq-prod`; name e.g. `hireiqstore123` (lowercase, globally unique); Region *East US*; Redundancy **LRS** → **Create**.
2. Open it → **Containers** → **+ Container** → name **`hireiq`** → **Create**.
3. **Access keys** → **Show** → copy **Connection string** (key1).

## A5. Key Vault (holds every secret)
1. Search **“Key vaults”** → **+ Create**. Resource group `hireiq-prod`; name e.g. `hireiq-kv-123` (globally unique); Region *East US*.
2. **Access configuration** tab → choose **Azure role-based access control (RBAC)** → **Review + create** → **Create**.
3. Give *yourself* permission to add secrets: open the vault → **Access control (IAM)** → **+ Add role assignment** → role **Key Vault Secrets Officer** → assign to your user → **Review + assign**.
4. Open **Objects → Secrets** → **+ Generate/Import**, and add each of these (name must match exactly — the app reads these dash-cased names):

   | Secret name | Value |
   |---|---|
   | `openai-api-key` | your OpenAI key |
   | `jwt-secret` | a long random string |
   | `agents-internal-secret` | a long random string |
   | `database-url` | the asyncpg URL from A2 |
   | `redis-url` | the rediss:// URL from A3 |
   | `email-api-key` | Resend API key (A7) |
   | `azure-storage-connection-string` | the connection string from A4 |
   | `azure-speech-key` / `azure-speech-region` | from A6 *(optional)* |
   | `azure-form-recognizer-endpoint` / `azure-form-recognizer-key` | from A6 *(optional)* |
   | `langfuse-public-key` / `langfuse-secret-key` / `langfuse-host` | *(optional — LLM tracing)* |
5. Copy the vault’s **Vault URI** from its Overview (e.g. `https://hireiq-kv-123.vault.azure.net/`) — that’s `AZURE_KEYVAULT_URL`.

## A6. (Optional) Azure AI Speech + Document Intelligence
- Search **“Azure AI services”** (or “Speech”/“Document intelligence”) → **+ Create** → pick the resource, Resource group `hireiq-prod`, **Free F0** pricing tier.
- After deploy → **Keys and Endpoint** → copy Key + Region/Endpoint → add to Key Vault (A5).
- Skip this if you don’t need voice interviews or image/scanned-CV OCR (HireIQ degrades gracefully).

## A7. Resend (candidate email)
1. Sign up at https://resend.com → **Domains → Add Domain**, add the shown **SPF/DKIM/DMARC** DNS records at your registrar, wait for *Verified*.
2. **API Keys → Create** → copy the key into Key Vault as `email-api-key` (A5).
3. Choose a `From` address on the verified domain (you’ll set `EMAIL_FROM` in A11).

## A8. Container Apps Environment
1. Search **“Container Apps”** → **+ Create**.
2. On the **Basics** tab, next to *Container Apps Environment* click **Create new** → name `hireiq-env`, Region *East US* → **Create**.
3. You’ll finish creating the first app (agents) in A9 — or cancel and create each app fresh; either works.

## A9. Create the three Container Apps
For the **first deploy** point each app at a public placeholder image; GitHub Actions will replace it with the real image on your first push. Create them in this order.

**`hireiq-agents` (internal):**
1. Container Apps → **+ Create**. Resource group `hireiq-prod`; Container app name `hireiq-agents`; Environment `hireiq-env`.
2. **Container** tab: uncheck *Use quickstart image*; Image source **Docker Hub**, image `<your-dockerhub-namespace>/hireiq-agents:latest` (it won’t exist yet — that’s fine, it’ll pull after the first CI run). Set **Target port 8001** later under Ingress.
3. **Ingress** tab: **Enabled**, **Ingress traffic: Limited to Container Apps Environment** (internal), Target port **8001**.
4. **Create**.

**`hireiq-api` (external):**
1. **+ Create** → name `hireiq-api`, Environment `hireiq-env`, image `<namespace>/hireiq-api:latest`.
2. **Ingress**: Enabled, **Accepting traffic from anywhere** (external), Target port **8000**.
3. **Create**.

**`hireiq-frontend` (external):**
1. **+ Create** → name `hireiq-frontend`, Environment `hireiq-env`, image `<namespace>/hireiq-frontend:latest`.
2. **Ingress**: Enabled, **Accepting traffic from anywhere** (external), Target port **80**.
3. **Create**.

After creation, open each external app’s **Overview** and copy its **Application Url** — you’ll need the api URL for the frontend build args and CORS.

## A10. Give `api` and `agents` access to Key Vault (managed identity)
For **each** of `hireiq-api` and `hireiq-agents`:
1. Open the app → **Settings → Identity** → **System assigned** → Status **On** → **Save** (copy the Object/Principal ID).
2. Open your **Key Vault → Access control (IAM)** → **+ Add role assignment** → role **Key Vault Secrets User** → **Assign access to: Managed identity** → select the app → **Review + assign**.

This is what lets `config.py` pull every secret from Key Vault at startup (via `DefaultAzureCredential`).

## A11. Set non-secret environment variables on each app
Open each app → **Settings → Containers → Edit and deploy → (select container) → Environment variables**. Add:

**`hireiq-api`:**
| Name | Value |
|---|---|
| `ENV` | `production` |
| `AZURE_KEYVAULT_URL` | your Vault URI (A5) |
| `AGENTS_BASE_URL` | `http://hireiq-agents` |
| `STORAGE_BACKEND` | `azure` |
| `AZURE_STORAGE_CONTAINER` | `hireiq` |
| `EMAIL_BACKEND` | `resend` |
| `EMAIL_FROM` | `HireIQ <noreply@yourdomain>` |
| `INTERVIEW_LINK_EXPIRY_HOURS` | `48` |
| `FRONTEND_ORIGIN` | the frontend Application Url (A9) |

**`hireiq-agents`:**
| Name | Value |
|---|---|
| `ENV` | `production` |
| `AZURE_KEYVAULT_URL` | your Vault URI |
| `AZURE_SPEECH_REGION` | e.g. `eastus` |

Click **Save** (creates a new revision).

## A12. (Optional) Custom domains
On the external apps → **Settings → Custom domains → + Add** → follow the DNS + managed-certificate wizard. After binding, update `FRONTEND_ORIGIN` (api) and the frontend build args (Part B) to the custom hostnames.

---

# Part B — Continuous deploy with GitHub Actions

The workflow already exists at **`.github/workflows/deploy.yml`**: on every push to `main` it
builds the three images, pushes them to Docker Hub, and runs a rolling `az containerapp update`
so Azure picks up the new images automatically. You just need to give it credentials.

## B1. Create a service principal for GitHub (Portal)
GitHub needs an identity allowed to update your Container Apps.
1. Search **“Microsoft Entra ID”** → **App registrations** → **+ New registration** → name `hireiq-github-deploy` → **Register**.
2. Copy the **Application (client) ID** and **Directory (tenant) ID** from its Overview.
3. **Certificates & secrets → + New client secret** → copy the **secret Value** immediately.
4. Find your **Subscription ID**: search **“Subscriptions”** → copy the ID.

## B2. Let it deploy to your resource group
1. Open **Resource group `hireiq-prod` → Access control (IAM) → + Add role assignment**.
2. Role **Contributor** → **Assign access to: User, group, or service principal** → select `hireiq-github-deploy` → **Review + assign**.

## B3. Add the GitHub repository secrets
In GitHub: **repo → Settings → Secrets and variables → Actions → New repository secret**. Add:

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | JSON (below) |
| `AZURE_RESOURCE_GROUP` | `hireiq-prod` |
| `ACA_API_APP` | `hireiq-api` |
| `ACA_AGENTS_APP` | `hireiq-agents` |
| `ACA_FRONTEND_APP` | `hireiq-frontend` |
| `DOCKERHUB_USERNAME` | your Docker Hub username |
| `DOCKERHUB_TOKEN` | a Docker Hub **access token** (Account → Security) |
| `DOCKERHUB_NAMESPACE` | your Docker Hub namespace (usually the username) |
| `FRONTEND_VITE_API_URL` | the api Application Url, e.g. `https://hireiq-api.<region>.azurecontainerapps.io` |
| `FRONTEND_VITE_WS_URL` | same host with `wss://`, e.g. `wss://hireiq-api.<region>.azurecontainerapps.io` |
| `OPENAI_API_KEY` | your OpenAI key (used by the RAGAS CI gate) |

`AZURE_CREDENTIALS` JSON (fill in the four IDs from B1):
```json
{
  "clientId": "<application-client-id>",
  "clientSecret": "<client-secret-value>",
  "subscriptionId": "<subscription-id>",
  "tenantId": "<directory-tenant-id>"
}
```

## B4. How the pipeline works (`.github/workflows/deploy.yml`)
On push to `main` (or **Actions → Deploy → Run workflow**):
1. **Build & push** — builds `hireiq-api`, `hireiq-agents`, `hireiq-frontend`, tags them `:${{ github.sha }}` and `:latest`, pushes to Docker Hub. The frontend image bakes `VITE_API_URL`/`VITE_WS_URL` from the secrets above so the browser calls your API directly.
2. **Rolling update** — `az containerapp update` swaps each app to the new `:${{ github.sha }}` image (agents first, then api, then frontend).

From then on, **every merge to `main` redeploys automatically**. `ci.yml` runs lint/tests/type-check (and the RAGAS gate on `main`) on every push/PR.

## B5. First deploy
Push to `main` (or trigger the workflow manually). Watch **GitHub → Actions**. When the *Deploy* run is green, your apps are live on the URLs from A9.

---

## C. Run database migrations (one-off, via Portal)
After the first successful deploy, create the schema:
1. Open **`hireiq-api` → Monitoring → Console** (or **Revisions → active revision → Console**).
2. Choose `/bin/sh` to connect to the running container, then run:
   ```
   alembic upgrade head
   ```
(The api image ships Alembic and reads `database-url` from Key Vault via its managed identity.)
Re-run this whenever a release adds a new migration.

---

## 9. Local vs production parity
Everything is env-driven; **no code differs**.

| Concern | Local (`ENV=development`) | Production (`ENV=production`) | Switch |
|---|---|---|---|
| Secrets | dev Vault / `.env` | Azure Key Vault (managed identity) | `ENV` |
| Email | console log | Resend | `EMAIL_BACKEND` |
| File storage | local disk | Azure Blob | `STORAGE_BACKEND` |
| Database / Redis | Docker | Flexible Server / Azure Cache | `DATABASE_URL` / `REDIS_URL` |
| Agents URL | `http://localhost:8001` | `http://hireiq-agents` | `AGENTS_BASE_URL` |
| Frontend → API | Vite/nginx `/api` proxy | baked `VITE_API_URL` (build arg) | build arg |
| CORS origin | `http://localhost:3000` | frontend Application Url | `FRONTEND_ORIGIN` |

Run locally exactly as before: `cd infra && cp .env.example .env && docker compose up`.

---

## 10. Smoke test
1. Visit the **frontend** URL → register a company, create + activate a job.
2. Apply as a candidate with a CV:
   - Qualified → invitation email with a link valid **48 h**.
   - Not qualified → warm rejection email.
3. Complete an interview → after evaluation: `hire` → “team will be in touch” email; otherwise → feedback report (valid 30 days).
4. Check delivery in the **Resend dashboard**, and (if enabled) traces in **Langfuse**.

---

## 11. Secrets & variables reference

**Azure Key Vault** (dash-cased secret name → setting, read automatically in prod): `openai-api-key`, `jwt-secret`, `agents-internal-secret`, `database-url`, `redis-url`, `email-api-key`, `azure-storage-connection-string`, and optional `azure-speech-*`, `azure-form-recognizer-*`, `langfuse-*`.

**Container App env vars** (non-secret, set in Portal A11): `ENV`, `AZURE_KEYVAULT_URL`, `AGENTS_BASE_URL`, `STORAGE_BACKEND`, `AZURE_STORAGE_CONTAINER`, `EMAIL_BACKEND`, `EMAIL_FROM`, `INTERVIEW_LINK_EXPIRY_HOURS`, `FRONTEND_ORIGIN` (api); `ENV`, `AZURE_KEYVAULT_URL`, `AZURE_SPEECH_REGION` (agents).

**GitHub Actions secrets** (Part B3): `AZURE_CREDENTIALS`, `AZURE_RESOURCE_GROUP`, `ACA_API_APP`, `ACA_AGENTS_APP`, `ACA_FRONTEND_APP`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `DOCKERHUB_NAMESPACE`, `FRONTEND_VITE_API_URL`, `FRONTEND_VITE_WS_URL`, `OPENAI_API_KEY`.
