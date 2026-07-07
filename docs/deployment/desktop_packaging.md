# Single-User Desktop Packaging

Goal: run OpenContracts as an easy, seamless **single-user desktop app** on
Linux/macOS/Windows with as few runtime dependencies as possible — every
`local.yml` compose service becomes a plain process or is eliminated. In
particular, **Redis is dropped** and PostgreSQL becomes a bundled child process.

This document is the architecture + phased plan. Phase 0 (settings profile +
launcher + the Warp-Ingest parser) lands first to de-risk the topology before
any native shell or installer work.

## Compose service → desktop replacement

| `local.yml` service | Desktop replacement |
|---|---|
| `postgres` (pgvector) | **Embedded PostgreSQL 16 + pgvector** child process (`pgserver`), per-user data dir. `DATABASES` is URL-driven (`config/settings/base.py` → `env.db("DATABASE_URL")`), so **no query/ORM/migration changes**. |
| `redis` | **Deleted.** Cache → `LocMemCache`; Celery broker → kombu *filesystem* transport; Celery result backend → the bundled Postgres via SQLAlchemy; Channels → in-process. |
| `celeryworker` | Worker **subprocess** over the filesystem broker (Phase 0) → in-process thread worker (later). |
| `celerybeat` | `celery beat` **subprocess** (Phase 0) → in-process APScheduler (later). The periodic sweeps (`reconcile_stuck_documents`, `recover_stalled_uploads`, …) matter *more* on a force-quit-prone desktop. |
| `flower` | Deleted. |
| `frontend` | `yarn build` once → Daphne serves the built `dist/` via the `spa_fallback` catch-all (`config/spa.py`, wired in `config/urls.py` when `OC_DESKTOP_SPA_ROOT` is set) — it serves both the hashed assets and `index.html` for client routes. WhiteNoise still covers only Django's own `STATIC_ROOT` (admin/DRF). No Node at install time. |
| `docling-parser` | **`WarpIngestLocalParser`** (`opencontractserver/pipeline/parsers/warp_ingest_local_parser.py`) — in-process, rule-based, no torch/GPU. |
| `docxodus-parser`, `vector-embedder`, `multimodal-embedder`, `privacy_filter` | Not used. Embeddings come from an OpenAI-compatible endpoint (`OpenAIEmbedder`, cloud key or a local server via `OPENAI_API_BASE_URL`). |

## Tiers

- **Tier 0 — offline, no key:** upload → parse (Warp-Ingest / TXT / MD) →
  annotate → read → Postgres keyword (tsvector) search. No semantic search, no
  chat.
- **Tier 1 — lite (default):** Tier 0 **+** embeddings & chat via an
  OpenAI-compatible endpoint (user key, or a local server). Zero microservices,
  zero torch. **Recommended default.**
- **Tier 2 — full (opt-in download):** local torch + sentence-transformers +
  docling-as-library for offline semantic search / ML layout. Installer ~2–4 GB,
  so it is a download-on-demand pack, never baked in.

## The Warp-Ingest parser

[`Warp-Ingest`](https://github.com/Open-Source-Legal/Warp-Ingest) is a
pure-Python, rule-based PDF layout engine (built on `pdfplumber`; optional
CPU-only OCR via `rapidocr-onnxruntime`). Its
`pdf_ingestor.parse_to_opencontracts(path)` returns an `OpenContractDocExport`
directly — PAWLS word tokens, one structural annotation per block, and the
heading hierarchy as `OC_PARENT_CHILD` relationships — so `WarpIngestLocalParser` is a
thin wrapper around `BaseParser`. Verified against real PDFs: born-digital docs
yield hundreds of structural annotations + relationships with no microservice.

It is registered for every deployment (auto-discovered) but only *selected* when
`PREFERRED_PARSERS` / `PipelineSettings` point at it — the compose default stays
Docling. `warp_ingest` is imported **lazily** so pipeline discovery works when
the package is absent.

> **nltk data.** Warp-Ingest imports the `stopwords`/`punkt` corpora at load
> time. The `desktop_bootstrap` command downloads them into the app-data dir on
> first run; bundle them for a fully-offline installer.

## Real-time eventing (known Phase-0 limitation)

Dropping Redis means the Channels layer becomes in-process
(`InMemoryChannelLayer`). The high-traffic **agent chat** path is unaffected — it
streams tokens inline in the consumer with no channel layer. But the two
notification emitters (`opencontractserver/notifications/signals.py` and
`opencontractserver/tasks/agent_tasks.py`) fire `group_send` from a **different
event loop** than Daphne's, and `InMemoryChannelLayer`'s buffers are loop-bound —
so badge/reply/mention/analysis-status toasts are **not delivered** yet under the
desktop profile. The fix (a loop-safe transport, preferably Postgres
`LISTEN/NOTIFY` since Postgres is already bundled) is the immediate follow-up;
until then the desktop settings note it inline.

## Running it — one command

```bash
python3 oc-desktop.py       # Windows: py oc-desktop.py
```

Requirements: **Python 3.10–3.12** (`pgserver` publishes no 3.13 wheels yet)
and an internet connection for the first run. The first run, in order
(`opencontractserver/desktop/bootstrap.py` → `launcher.py`):

1. creates a private virtualenv under the per-user app-data dir and installs
   `requirements/desktop.txt` into it (system Python untouched; re-installs
   automatically when the requirement files change);
2. acquires the built SPA (`opencontractserver/desktop/spa_dist.py`): repo
   `frontend/dist` if present → previously downloaded copy → the
   `opencontracts-frontend-dist.zip` asset from the GitHub release
   (version-matched tag, then latest) → `yarn install && yarn build` if a Node
   toolchain is present;
3. starts the embedded PostgreSQL, migrates, and prompts you to **choose a
   password** for the local `desktop` superuser (set `OC_DESKTOP_PASSWORD` to
   skip the prompt in scripted/headless runs);
4. seeds pipeline settings + nltk corpora, starts Daphne and the Celery
   worker/beat, and opens the browser at `http://127.0.0.1:8406/` (falls back
   to an ephemeral port if 8406 is taken).

Log in as **`desktop`** with the password you chose. **Stop the app with
Ctrl+C** in the launch terminal — every child (including Postgres) shuts down
cleanly. Later launches skip setup and start in well under a minute.

Everything is stored under a per-user app-data directory
(`opencontractserver/desktop/paths.py`): `venv/`, `pgdata/`, `media/`,
`staticfiles/`, `celery-broker/`, `nltk_data/`, `spa/`, and the first-run
`.bootstrapped` marker — delete the directory to reset the app completely.
Point at an existing database instead of the embedded one by exporting
`DATABASE_URL` before launch. (An external database must already have the
`vector` extension available — the embedded `pgserver` path runs `CREATE
EXTENSION IF NOT EXISTS vector` for you; the external path does not.)

> **pg_trgm.** The embedded `pgserver` binaries bundle only `plpgsql` and
> `vector` — no contrib extensions. Migration
> `annotations/0074_annotation_raw_text_trigram_index` therefore probes
> `pg_available_extensions` and skips the trigram index when `pg_trgm` is
> absent: annotation substring search still works on desktop, just unindexed
> (fine at single-user scale; every compose/production deployment still gets
> the index).

**Secret handling:** the launcher resolves a stable `DJANGO_SECRET_KEY` from the
**OS keyring** (macOS Keychain / Windows Credential Locker / Linux Secret
Service) and shares it across child processes. A stable key is important: it
survives restarts *and* keeps `PipelineSettings`' encrypted secrets (e.g. your
`OPENAI_API_KEY`) decryptable — a key that rotated each launch would make them
permanently unrecoverable. If no keyring backend is available, the launcher
falls back to an ephemeral key (with a warning) and sessions + stored secrets
reset on restart; export a stable `DJANGO_SECRET_KEY` yourself in that case. The
local login password comes from `OC_DESKTOP_PASSWORD` when set, otherwise from
the interactive first-run prompt (min 8 characters, confirmed twice); with
neither (headless, no env var) the user is created with no usable password and
the next interactive launch — or `manage.py changepassword` — sets one. Because
this account is a superuser, choose a strong password (only the length floor is
validated on the desktop profile). No secret is written to a plaintext file.

To enable embeddings + chat, set `OPENAI_API_KEY` (and optionally
`OPENAI_API_BASE_URL` for a local OpenAI-compatible server) before first run so
`desktop_bootstrap` seeds it into `PipelineSettings`.

## Phased delivery

- **Phase 0 (this):** `config/settings/desktop.py` + `oc-desktop.py` launcher +
  `WarpIngestLocalParser` + first-run bootstrap. Runs the whole stack as processes.
- **Phase 1:** package `python-build-standalone` + a relocatable venv + `pgserver`
  + staged `dist/` per-OS; harden embedded-Postgres supervision (stale-lock
  recovery, major-version datadir guard); loop-safe notification transport;
  collapse worker/beat in-process (thread worker + APScheduler); pystray tray.
  Windows shutdown note: `Popen.terminate()` on Windows is a hard
  `TerminateProcess` (no graceful signal), so a Celery worker's in-flight task is
  interrupted rather than drained — the `reconcile_stuck_documents` beat sweep
  recovers any stranded document, but graceful Windows teardown is a Phase-1 item.
- **Phase 2:** native shell (Tauri v2 sidecar) + dmg/msi/AppImage installers.
- **Phase 3:** code-signing, macOS notarization, auto-update (Tauri updater).
- **Phase 4 (optional):** full offline ML pack (torch + sentence-transformers +
  docling-as-library), downloaded on demand.

### Why these choices

- **Embedded Postgres, not SQLite/sqlite-vec.** The vector/search coupling
  (pgvector `VectorField` × 7 dims, HNSW indexes, tsvector FTS with a plpgsql
  trigger + GIN, `pg_trgm` trigram, `ArrayField`) is concentrated but deep; an
  embedded server preserves 100% of it with a one-line `DATABASE_URL` change,
  whereas sqlite-vec is an L–XL rewrite that also regresses ANN to brute force.
- **`python-build-standalone` + venv, not PyInstaller.** Freezing
  Django/Celery/Daphne/psycopg fights app autodiscovery, dynamic imports and
  native libs; a relocatable CPython runs `manage.py` exactly as in dev and
  yields real child PIDs for clean shutdown.
- **Tauri, not Electron.** ~3 MB shell vs ~96 MB, native code-signing hooks and a
  turnkey cross-platform updater; the install weight is dominated by the
  Python + Postgres payload regardless.
