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
| `frontend` | `yarn build` once → **WhiteNoise serves `dist/`** from Daphne + a SPA catch-all (`config/spa.py`, wired in `config/urls.py` when `OC_DESKTOP_SPA_ROOT` is set). No Node at install time. |
| `docling-parser` | **`WarpIngestParser`** (`opencontractserver/pipeline/parsers/warp_ingest_parser.py`) — in-process, rule-based, no torch/GPU. |
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
heading hierarchy as `OC_PARENT_CHILD` relationships — so `WarpIngestParser` is a
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

## Running Phase 0

```bash
# 1. Build the SPA once (served by Daphne):
cd frontend && yarn build && cd ..

# 2. Install desktop extras (adds warp-ingest, pgserver, sqlalchemy):
pip install -r requirements/desktop.txt

# 3. Launch — starts Postgres, migrates, seeds a local user, runs Daphne +
#    Celery worker/beat, opens the browser. No Docker, no Redis.
python oc-desktop.py
```

Everything is stored under a per-user app-data directory
(`opencontractserver/desktop/paths.py`): `pgdata/`, `media/`, `staticfiles/`,
`celery-broker/`, `nltk_data/`, the persisted `secret_key`, and the generated
login `credentials.txt`. Point at an existing database instead of the embedded
one by exporting `DATABASE_URL` before launch.

To enable embeddings + chat, set `OPENAI_API_KEY` (and optionally
`OPENAI_API_BASE_URL` for a local OpenAI-compatible server) before first run so
`desktop_bootstrap` seeds it into `PipelineSettings`.

## Phased delivery

- **Phase 0 (this):** `config/settings/desktop.py` + `oc-desktop.py` launcher +
  `WarpIngestParser` + first-run bootstrap. Runs the whole stack as processes.
- **Phase 1:** package `python-build-standalone` + a relocatable venv + `pgserver`
  + staged `dist/` per-OS; harden embedded-Postgres supervision (stale-lock
  recovery, major-version datadir guard); loop-safe notification transport;
  collapse worker/beat in-process (thread worker + APScheduler); pystray tray.
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
