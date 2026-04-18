# Deploying OpenContracts to EasyPanel

Get the full stack — Django + Celery + pgvector + the Bolivian-laws RAG
service with its daily scrapers — running on an [EasyPanel](https://easypanel.io/)
host with **one command**.

## TL;DR — three steps

You need: a VPS with Docker, a domain pointing at it, and an OpenAI API
key.

```bash
# 1. SSH into the VPS, clone the repo
git clone <your-fork-url> opencontracts
cd opencontracts
git checkout <branch-you-want-to-deploy>

# 2. Run the one-command deploy (you'll be asked 4 questions)
./scripts/easypanel/deploy.sh

# 3. Open https://<your-domain> in a browser
```

That's it. The script:

1. Generates strong random secrets (`DJANGO_SECRET_KEY`, admin URL slug,
   Postgres password, Flower creds, vector-embedder API key) and writes
   `.envs/.production/{.django,.postgres,.frontend}` for you.
2. Patches `compose/production/traefik/traefik.yml` with your domain and
   ACME email so Let's Encrypt issues a real cert.
3. Builds images, runs migrations, brings the stack up, and runs a 3-PDF
   smoke test of the Bolivian-laws scrape so you can see Flower light up.

It prints the credentials it generated at the end — copy them into a
password manager.

### Non-interactive (CI / re-runs)

```bash
./scripts/easypanel/deploy.sh \
    --domain oc.example.com \
    --email you@example.com \
    --openai-key sk-... \
    --admin-password 'StrongPass!'
```

Re-running is safe: env files are kept, Traefik is re-patched
idempotently, Compose just brings any missing services up.

## Plugging it into EasyPanel

The script is plain Docker Compose under the hood, so EasyPanel only
needs to know which Compose file to boot:

1. **Create Service → App** in the EasyPanel dashboard.
2. **Source**: Git, pointing at your fork + branch.
3. **Build Method**: Docker Compose. **File**: `production.yml`.
4. **Pre-deploy hook** (optional but recommended for fresh installs):
   `./scripts/easypanel/deploy.sh --domain $DOMAIN --email $EMAIL --openai-key $OPENAI_KEY --admin-password $ADMIN_PASSWORD --skip-scrape-test`
5. Set `DOMAIN`, `EMAIL`, `OPENAI_KEY`, `ADMIN_PASSWORD` as EasyPanel env
   vars on the App so the hook picks them up.
6. **Deploy**.

If you'd rather wire EasyPanel up by hand (no script), see "Manual
wiring" below.

## What gets deployed

`production.yml` brings up:

| Service | Purpose | Persistent volume? |
|---|---|---|
| `postgres` | PostgreSQL 16 + pgvector | yes |
| `redis` | Broker + cache | no |
| `django` | ASGI app (GraphQL + REST + WebSockets) | no |
| `celeryworker` | Background jobs (parsing, embedding, scraping) | no |
| `celerybeat` | Periodic task scheduler — runs the daily Bolivian-laws scrape | no |
| `vector-embedder` | Sentence-transformers microservice | no |
| `docling-parser` | Docling PDF parser microservice | no |
| `docxodus-parser` | DOCX/XLSX/PPTX parser microservice | no |
| `frontend` | React SPA (Vite build behind nginx) | no |
| `traefik` | TLS termination + reverse proxy | yes (ACME volume) |

Persistent volumes you should back up: `production_postgres_data`,
`production_postgres_data_backups`, `production_traefik`.

## Verifying the deploy

- Browse to `https://<your-domain>` — the React SPA loads.
- `https://<your-domain>/admin/<slug>/` — Django admin (slug printed at
  the end of `deploy.sh`).
- `https://<your-domain>:5555` — Flower (Celery monitor) protected by
  basic auth. Confirm `bolivian-laws-scrape-all` appears under
  *Scheduled tasks*.
- In Django admin → *Bolivian Legal Documents* you should see entries
  with `status=ingested` from the smoke test.

## Day-2 operations

```bash
# Re-deploy after pulling new code:
git pull && docker compose -f production.yml up -d --build

# Run new migrations:
docker compose -f production.yml --profile migrate up migrate

# Run the Bolivian-laws scrape on demand:
docker compose -f production.yml exec django \
    python manage.py scrape_bolivian_laws --all --since-days 7 --sync

# Tail logs:
docker compose -f production.yml logs -f django celeryworker celerybeat
```

The Beat schedule re-runs `scrape_and_ingest_all` once a day. SHA-256
dedupe makes re-runs cheap.

## Manual wiring (without `deploy.sh`)

The deploy script is a thin wrapper. If you prefer to do each step by
hand:

1. `./scripts/easypanel/generate-env.sh --domain ... --email ... --openai-key ...`
   creates the three env files under `.envs/.production/`.
2. `./scripts/easypanel/configure-traefik.sh --domain ... --email ...`
   patches the Traefik config (a `.bak` is left next to the file).
3. `docker compose -f production.yml --profile migrate up migrate`
   runs migrations.
4. `docker compose -f production.yml up -d` brings the stack up.

Each helper accepts `--help` and is safe to re-run.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `django` keeps restarting | Missing env vars | Inspect `docker compose logs django`; re-run `deploy.sh` |
| `psycopg2.OperationalError: could not connect` | DB still warming up on first boot | Give Postgres ~30 s and retry the `--profile migrate` step |
| Scrape summary shows `discovered=0` | Site HTML changed or blocked | Override `BOLIVIAN_LAWS_<SOURCE>_LISTING_PATHS` in `.envs/.production/.django` and restart |
| Beat never fires `bolivian-laws-scrape-all` | `celerybeat` service down | `docker compose logs celerybeat`; redeploy that service |
| `500` on `POST /graphql/` | `OPENAI_API_KEY` empty in worker | All three services share the same env file — re-run `deploy.sh` to refresh |
| Embeddings fail | `vector-embedder` still pulling weights on first boot (~1 GB) | Wait a few minutes, retry |
| Cert never issues | Domain doesn't resolve to the VPS | `dig <domain>` should return your server IP; fix DNS first |

## Security checklist

- [ ] `DJANGO_DEBUG=False` (`.django` template default).
- [ ] `DJANGO_SECRET_KEY` is randomly generated (script-handled).
- [ ] `DJANGO_ADMIN_URL` slug is random (script-handled).
- [ ] Flower port 5555 firewalled to your IP (or behind a VPN) — basic
      auth alone is not enough for production.
- [ ] `BOLIVIAN_LAWS_SCRAPER_USER_AGENT` identifies your deployment with
      a contact email — respect each target site's `robots.txt`.
- [ ] TLS cert visible in browser (Traefik via Let's Encrypt).

## Related docs

- [Bolivian Laws RAG service](../features/bolivian_laws_rag.md) — how
  the scrapers work and how to query the corpus from GraphQL.
- [GPU setup](./docker-gpu-setup.md) — for co-locating a local LLM.
