# Deploying OpenContracts on EasyPanel (from GitHub)

Native EasyPanel flow: pull the repo from GitHub, paste a block of
environment variables into the app, click **Deploy**. No SSH, no
scripts on the server, no `.env` files to upload.

The stack uses `easypanel.yml` (dedicated Compose file) instead of
`production.yml`. It's parameterised entirely through env vars and
delegates TLS / domain routing to EasyPanel's built-in reverse proxy.

## What you need

- A domain pointing at your EasyPanel server (A record).
- Your fork of this repo on GitHub.
- An OpenAI API key.

## Step 1 — generate secrets to paste

On your laptop (or any machine with Python 3):

```bash
./scripts/easypanel/print-env.sh \
    --domain oc.example.com \
    --email you@example.com \
    --openai-key sk-... \
    --admin-password 'StrongPass!'
```

This prints ~12 `KEY=value` lines: the four values you supplied plus
cryptographically-random `DJANGO_SECRET_KEY`, `DJANGO_ADMIN_URL_SLUG`,
`POSTGRES_PASSWORD`, `CELERY_FLOWER_USER`, `CELERY_FLOWER_PASSWORD`,
`VECTOR_EMBEDDER_API_KEY`.

Copy the whole block.

> Don't have Python 3 handy? Open the script and run the `python3 -c`
> lines in any Python REPL, or generate random strings with
> `openssl rand -hex 24` / `openssl rand -base64 64`.

## Step 2 — create the EasyPanel app

1. **Create Service → App** in your EasyPanel project.
2. **Source**: Git.
    - Repository: your fork's URL.
    - Branch: the one you want to deploy (e.g.
      `claude/rag-bolivian-laws-service-OYXry`).
3. **Build Method**: **Docker Compose**.
4. **Compose File**: `easypanel.yml`.
5. **Environment**: paste the block from step 1 straight into the
   EasyPanel env editor.
6. **Save**. Do **not** deploy yet — we need to wire domains first.

## Step 3 — wire the domain in EasyPanel

The Compose file intentionally has **no Traefik service**; EasyPanel's
proxy does TLS and routing. In the app's *Domains* tab:

| Target service | Port | Path rules |
|---|---|---|
| `frontend` | 80 | default (everything that isn't a Django path) |
| `django` | 5000 | `/graphql`, `/api`, `/admin`, `/ws`, `/mcp`, `/sse`, `/.well-known`, `/robots.txt`, `/llms.txt`, `/llms-full.txt`, `/sitemap.xml` |

Assign the same hostname (e.g. `oc.example.com`) to both entries.
EasyPanel will issue a Let's Encrypt cert automatically.

*(Skipping Flower for now — the bundled Traefik is gone, so if you
want the Celery monitor UI, expose `celeryworker` separately or port-
forward `docker exec ... flower` when you need it.)*

## Step 4 — deploy

Click **Deploy** in EasyPanel. First build takes a few minutes
(pulls Docling + embedder images, builds the Django + frontend
images).

Once all services are healthy, run migrations exactly once — either
from the EasyPanel terminal:

```bash
docker compose -f easypanel.yml --profile migrate up migrate
```

…or from any service's shell:

```bash
docker compose -f easypanel.yml exec django python manage.py migrate
docker compose -f easypanel.yml exec django python manage.py migrate_pipeline_settings
```

## Step 5 — verify

- Browse to `https://<your-domain>` — the React app loads.
- `https://<your-domain>/admin/<slug>/` — Django admin. The slug is
  whatever `DJANGO_ADMIN_URL_SLUG` value you pasted.
- Smoke-test the Bolivian-laws scrape:
  ```bash
  docker compose -f easypanel.yml exec django \
      python manage.py scrape_bolivian_laws --all --since-days 7 --max-entries 3 --sync
  ```
  Should print a summary like `{'source': 'gaceta', 'discovered': 3,
  'ingested': 3, ...}`.

The Beat scheduler (`celerybeat` service) then runs
`bolivian-laws-scrape-all` automatically once a day. SHA-256 dedupe
makes re-runs cheap.

## Environment variables reference

Required:

| Var | Description |
|---|---|
| `DOMAIN` | Public hostname (e.g. `oc.example.com`) |
| `ADMIN_EMAIL` | Contact email — used for the superuser and can be reused for Let's Encrypt |
| `ADMIN_PASSWORD` | Initial Django superuser password |
| `OPENAI_API_KEY` | Used for embeddings + agent answers |
| `DJANGO_SECRET_KEY` | Cryptographic secret key; random 64+ chars |
| `DJANGO_ADMIN_URL_SLUG` | Obfuscates the admin path; random 30 chars |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `CELERY_FLOWER_USER` / `CELERY_FLOWER_PASSWORD` | Flower basic-auth creds |
| `VECTOR_EMBEDDER_API_KEY` | Shared secret between Django and the embedder sidecar |

Optional (safe defaults apply):

| Var | Default |
|---|---|
| `OPENAI_MODEL` | `gpt-4o` |
| `ANTHROPIC_API_KEY` | (empty) |
| `STORAGE_BACKEND` | `LOCAL` (set `AWS` or `GCP` to use object storage) |
| `USE_AUTH0` | `false` |
| `ADMIN_USERNAME` | `admin` |
| `BOLIVIAN_LAWS_SCRAPER_USER_AGENT` | `OpenContractsBolivianLawsBot/1.0` |
| `BOLIVIAN_LAWS_SCRAPE_LOOKBACK_DAYS` | `30` |
| `BOLIVIAN_LAWS_REQUEST_DELAY_SECONDS` | `1.0` |

Missing a required var? Compose will refuse to start and tell you
which one — that's the `${VAR:?error}` syntax in `easypanel.yml`.

## Day-2

- **Redeploy** pulls the latest commit and rebuilds.
- **New migrations**: run the `--profile migrate` command after each
  deploy that includes them.
- **On-demand scrape**:
  ```bash
  docker compose -f easypanel.yml exec django \
      python manage.py scrape_bolivian_laws --all --since-days 7 --sync
  ```
- **Logs**: EasyPanel tails each service. `celerybeat` should log
  `Scheduler: Sending due task bolivian-laws-scrape-all` once a day.

## Troubleshooting

| Symptom | Fix |
|---|---|
| App fails to start with `ERROR: DJANGO_SECRET_KEY is required` | One of the required env vars is empty — re-run `print-env.sh` and paste the full block. |
| `psycopg2.OperationalError` on first boot | Postgres needs ~30 s — re-run the migrate step. |
| `443` returns the EasyPanel landing page | Domain not bound to the `frontend`/`django` services. Check the Domains tab (step 3). |
| `/graphql` returns the React index | Path rule for `/graphql` → `django:5000` missing. Add it in the Domains tab. |
| Scrape summary `discovered=0` | Target site changed structure — override `BOLIVIAN_LAWS_<SOURCE>_LISTING_PATHS` env var and redeploy. |
| `500` on `POST /graphql/` | `OPENAI_API_KEY` not set on the worker. EasyPanel env vars apply to all services in the Compose app — confirm they're at the app level, not one service. |

## Security checklist

- [ ] `DJANGO_DEBUG=False` (default in `easypanel.yml`).
- [ ] `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, Flower password are the
      randomly-generated values (not placeholders).
- [ ] `DJANGO_ADMIN_URL_SLUG` is random (script default).
- [ ] EasyPanel cert visible in browser.
- [ ] `BOLIVIAN_LAWS_SCRAPER_USER_AGENT` identifies you with a contact
      email — respect each target site's `robots.txt`.

## Alternative: bundled Traefik (old flow)

If you'd rather manage TLS yourself with the project's bundled Traefik
config (instead of EasyPanel's proxy), use the original
`production.yml`. See [production.yml](../../production.yml) and run
`./scripts/easypanel/deploy.sh` — that flow still works but is heavier.

## Related

- [Bolivian Laws RAG service](../features/bolivian_laws_rag.md) — what
  the scrapers do and how to query the corpus via GraphQL.
- [GPU setup](./docker-gpu-setup.md) — co-locate a local LLM.
