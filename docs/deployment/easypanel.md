# Deploying OpenContracts to EasyPanel

This guide walks through deploying the full OpenContracts stack (including the
Bolivian-laws RAG service with its scheduled scrapers) to an [EasyPanel](https://easypanel.io/)
server using the existing `production.yml` Docker Compose file.

## Prerequisites

- A VPS with EasyPanel installed (Hetzner, DigitalOcean, etc.). Minimum:
  **4 vCPU / 8 GB RAM / 40 GB disk**. The Docling parser + embedder
  microservices are memory-hungry; 16 GB is comfortable.
- A domain you control (e.g. `oc.example.com`). Point an `A` record at the
  server.
- An OpenAI API key (or equivalent) for embeddings and agent LLMs.
- Your fork of this repository on GitHub/GitLab, on the branch you want to
  deploy (e.g. `claude/rag-bolivian-laws-service-OYXry`).

## Architecture recap

`production.yml` brings up:

| Service | Purpose | Needs persistence? |
|---|---|---|
| `postgres` | PostgreSQL 16 + pgvector | **yes** (DB volume) |
| `redis` | Broker + cache | no (OK to rebuild) |
| `django` | ASGI app (GraphQL + REST + WebSockets) on port 5000 | no |
| `celeryworker` | Background jobs (parsing, embedding, ingestion, scraping) | no |
| `celerybeat` | Periodic task scheduler (runs the daily Bolivian-laws scrape) | no |
| `vector-embedder` | Sentence-transformers microservice | no |
| `docling-parser` | Docling PDF parser microservice | no |
| `docxodus-parser` | DOCX/XLSX/PPTX parser microservice | no |
| `frontend` | React SPA (Vite build behind nginx) | no |
| `traefik` | TLS termination + reverse proxy | **yes** (ACME volume) |
| `migrate` | One-shot migration container (profile: `migrate`) | no |

Volumes to preserve across rebuilds:

- `production_postgres_data`
- `production_postgres_data_backups`
- `production_traefik`

## Option A — single "App" service running Compose (recommended)

EasyPanel has native support for Docker Compose. This is the fastest path.

### 1. Create the app

1. In the EasyPanel dashboard: **Create Service → App**.
2. **Source**: Git. Provide the repository URL and the branch you want
   (`main` or a feature branch).
3. **Build Method**: **Docker Compose**.
4. **Compose File**: `production.yml`.
5. **Compose Project Name**: leave as default (EasyPanel scopes volumes
   under the app).

### 2. Configure environment files

`production.yml` reads env files from `./.envs/.production/`. These are **not**
committed, so create them on the server using EasyPanel's mounted files
feature — or commit them to a **private** fork. Create three files under
`.envs/.production/` at deploy time:

#### `.envs/.production/.django`

```bash
# --- Django core ---
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<run: python -c "import secrets;print(secrets.token_urlsafe(64))">
DJANGO_ADMIN_URL=admin/<random-slug>/
DJANGO_ALLOWED_HOSTS=oc.example.com,django
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=you@example.com
DJANGO_SUPERUSER_PASSWORD=<strong-password>

# --- Storage ---
STORAGE_BACKEND=LOCAL   # or AWS / GCP (see docs/deployment/)

# --- Redis / Celery ---
REDIS_URL=redis://redis:6379/0
CELERY_FLOWER_USER=<random>
CELERY_FLOWER_PASSWORD=<random>

# --- Auth0 (optional) ---
USE_AUTH0=false

# --- LLM ---
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
ANTHROPIC_API_KEY=                 # optional

# --- Pipeline microservices (in-network URLs) ---
EMBEDDINGS_MICROSERVICE_URL=http://vector-embedder:8000
VECTOR_EMBEDDER_API_KEY=<random>
DOCLING_PARSER_SERVICE_URL=http://docling-parser:8000/parse/
DOCXODUS_PARSER_SERVICE_URL=http://docxodus-parser:8080/parse
DOCXODUS_PARSER_TIMEOUT=120

# --- Bolivian Laws RAG (optional overrides) ---
BOLIVIAN_LAWS_GACETA_BASE_URL=https://gacetaoficialdebolivia.gob.bo/
BOLIVIAN_LAWS_GACETA_LISTING_PATHS=/
BOLIVIAN_LAWS_TSJ_BASE_URL=https://tsj.bo/
BOLIVIAN_LAWS_TSJ_LISTING_PATHS=/jurisprudencia/
BOLIVIAN_LAWS_TCP_BASE_URL=https://tcpbolivia.bo/
BOLIVIAN_LAWS_TCP_LISTING_PATHS=/jurisprudencia/
BOLIVIAN_LAWS_SCRAPER_USER_AGENT=YourOrg-OpenContracts/1.0 (contact@yourorg)
BOLIVIAN_LAWS_SCRAPE_LOOKBACK_DAYS=30
BOLIVIAN_LAWS_REQUEST_DELAY_SECONDS=1.0
```

#### `.envs/.production/.postgres`

```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=opencontractserver
POSTGRES_USER=opencontractserver
POSTGRES_PASSWORD=<strong-password>
DATABASE_URL=postgres://opencontractserver:<strong-password>@postgres:5432/opencontractserver
```

#### `.envs/.production/.frontend`

```bash
# Point the SPA at the same public domain (Traefik routes /graphql, /api, /ws)
REACT_APP_API_ROOT_URL=https://oc.example.com
REACT_APP_APPLICATION_DOMAIN=oc.example.com
REACT_APP_USE_AUTH0=false
```

### 3. Traefik / domain wiring

`production.yml` exposes Traefik on ports 80/443/5555. On EasyPanel:

- **Option 3a (recommended)**: disable EasyPanel's built-in Traefik for this
  app (or bind the ports) and point your domain at the VPS directly. The
  bundled Traefik in `production.yml` handles Let's Encrypt via the
  `production_traefik` volume.
- **Option 3b**: keep EasyPanel's proxy and bind the `django` service to an
  internal port. You'll need to customise `compose/production/traefik` or
  disable the bundled Traefik. This is more work — prefer 3a.

Configure the bundled Traefik by editing
`compose/production/traefik/traefik.yml` (domain, email) before the first
deploy. This file is baked into the Traefik image at build time, so re-deploy
after changes.

### 4. First deploy

Push the **Deploy** button in EasyPanel. The stack comes up; Postgres
initialises the `opencontractserver` database on first boot.

### 5. Run migrations

Migrations do **not** run automatically. From the EasyPanel app console
(or SSH into the host and `cd` to the deployment directory):

```bash
docker compose -f production.yml --profile migrate up migrate
```

This runs:

1. `python manage.py migrate` — schema migrations, including
   `bolivian_laws/0001_initial.py`.
2. `python manage.py migrate_pipeline_settings` — wires up parsers/embedders.

### 6. Verify the deploy

- Browse to `https://oc.example.com` — the React SPA should load.
- `https://oc.example.com/graphql/` — GraphiQL (if `ALLOW_GRAPHQL_DEBUG=true`
  is set) or `405 Method Not Allowed` on GET.
- `https://oc.example.com/admin/<your-slug>/` — Django admin.
- Flower (Celery monitor) at `https://oc.example.com:5555` with the Flower
  credentials from `.django`.
- In Flower, confirm that **`bolivian-laws-scrape-all`** appears under
  scheduled tasks.

### 7. Bootstrap the Bolivian-laws corpora

From the `django` container:

```bash
# Create the superuser if you haven't already:
docker compose -f production.yml exec django python manage.py createsuperuser

# Optionally seed one area corpus up-front (not required — it's lazy):
docker compose -f production.yml exec django python manage.py shell -c "\
from opencontractserver.bolivian_laws.services.ingestion import ensure_area_corpus;\
from django.contrib.auth import get_user_model;\
u = get_user_model().objects.filter(is_superuser=True).first();\
ensure_area_corpus('constitucional', user=u);\
"

# Kick a first scrape manually (good smoke test — pass --max-entries to keep it small):
docker compose -f production.yml exec django \
  python manage.py scrape_bolivian_laws --all --since-days 7 --max-entries 5 --sync
```

After that, `celerybeat` runs `scrape_and_ingest_all` daily. Re-runs are
cheap because SHA-256 dedupe skips already-ingested PDFs.

## Option B — one EasyPanel service per image

Useful if you want independent scaling (e.g. more workers for heavy
embedding batches) or EasyPanel-managed backups.

Create one service per row in the architecture table. Key wiring:

| EasyPanel service | Image / build | Depends on | Ports |
|---|---|---|---|
| `oc-postgres` | Build `compose/production/postgres/Dockerfile` | — | 5432 (internal) |
| `oc-redis` | `redis:6` | — | 6379 (internal) |
| `oc-vector-embedder` | `jscrudato/vector-embedder-microservice` | — | 8000 (internal) |
| `oc-docling-parser` | `jscrudato/docsling-local` | — | 8000 (internal) |
| `oc-docxodus-parser` | `ghcr.io/open-source-legal/docxodus-service:1.1.0-docxodus5.4.2` | — | 8080 (internal) |
| `oc-django` | Build `compose/production/django/Dockerfile`, command as in `production.yml` | postgres, redis, vector-embedder, docling-parser, docxodus-parser | 5000 (proxied) |
| `oc-celeryworker` | Same image as `oc-django`, command `/start-celeryworker` | postgres, redis | — |
| `oc-celerybeat` | Same image, command `/start-celerybeat` | postgres, redis | — |
| `oc-frontend` | Build `./frontend/Dockerfile` | oc-django | 80 (proxied) |

Set the same env files on `oc-django`, `oc-celeryworker`, `oc-celerybeat`
(they share the `&django` anchor in `production.yml` for a reason). Expose
only `oc-frontend` and `oc-django` through EasyPanel's reverse proxy — give
both the same hostname, with `oc-django` handling `/graphql`, `/api`, `/ws`,
`/admin` and `oc-frontend` the default.

## Persistence & backups

EasyPanel maps Compose volumes onto the host. Point your backup tool at:

- `production_postgres_data` (PostgreSQL data — use the
  `production_postgres_data_backups` volume plus
  `compose/production/postgres/maintenance/backup`).
- `production_traefik` (ACME certificates — small, but saves re-issuing).

If you're on AWS/GCP object storage (`STORAGE_BACKEND=AWS`/`GCP`), uploaded
documents live outside the container and only the DB matters on-host.

## Upgrades

- Commit to `main` (or your deployment branch), then **Redeploy** in
  EasyPanel.
- After pulling a new commit that adds migrations: re-run
  `docker compose -f production.yml --profile migrate up migrate` **before**
  the new `django` image starts serving traffic. EasyPanel supports a
  "pre-deploy command" field — put the migrate line there.

## Operational tips

- **Scaling workers**: duplicate the `celeryworker` service (or bump the
  concurrency of `/start-celeryworker`). The Bolivian-laws scrape task is
  independent per source — running three workers lets all three scrapers
  run in parallel on the daily Beat trigger.
- **Logs**: EasyPanel tails container logs. `celerybeat` should log
  `Scheduler: Sending due task bolivian-laws-scrape-all` once per day.
- **Metrics**: Flower (port 5555) shows task throughput, retries, and the
  scrape summary dict (`discovered` / `ingested` / `dedupe_hits` / `failed`).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `django` keeps restarting | Missing env vars (e.g. `DJANGO_SECRET_KEY`) | Check `.envs/.production/.django` is mounted and populated |
| `psycopg2.OperationalError: could not connect` | DB init race | `postgres` needs ~30 s on first boot; Compose has `depends_on` but EasyPanel may skip health gates |
| Scrape summary shows `discovered=0` | Site HTML changed, or listing URL blocked | Override `BOLIVIAN_LAWS_<SOURCE>_LISTING_PATHS`; inspect one listing manually via `docker compose exec django python -c "import httpx;print(httpx.get('https://...').text[:500])"` |
| Beat never fires `bolivian-laws-scrape-all` | `celerybeat` service not running | EasyPanel dashboard → ensure the service is up; check `docker compose logs celerybeat` |
| `500` on `POST /graphql/` | Missing `OPENAI_API_KEY` reaching the worker | Verify all three services (`django`, `celeryworker`, `celerybeat`) share the same env file |
| Embedding calls fail | `vector-embedder` sidecar didn't start | `docker compose logs vector-embedder`; the image pulls ~1 GB of model weights on first boot |

## Security checklist

- [ ] `DJANGO_DEBUG=False` (production settings default).
- [ ] `DJANGO_SECRET_KEY` is randomly generated and **not** the sample value.
- [ ] `DJANGO_ADMIN_URL` is obfuscated (the sample uses a random 30-char slug).
- [ ] Flower's basic-auth credentials are strong; the port 5555 is firewalled
  to your IP or disabled if unused.
- [ ] `POSTGRES_PASSWORD` matches between `.postgres` and `DATABASE_URL`.
- [ ] The `BOLIVIAN_LAWS_SCRAPER_USER_AGENT` identifies your deployment with
  a contact email — respect `robots.txt` on each target site.
- [ ] TLS certificate issued by Traefik (check
  `https://oc.example.com` in a browser).

## Related docs

- [Bolivian Laws RAG service](../features/bolivian_laws_rag.md) — feature,
  tasks, and query examples.
- [GPU setup](./docker-gpu-setup.md) — if you want to co-locate a local LLM.
