# Bolivian Laws RAG Service

A turn-key RAG (Retrieval-Augmented Generation) service for Bolivian
legal sources. It scrapes the three main official publishers, ingests
their PDFs into per-area corpora, and exposes a ready-to-query agent
stack on top of the standard OpenContracts GraphQL API.

## Architecture at a glance

```
  ┌────────────────┐   ┌───────────────┐   ┌──────────────────┐
  │ Gaceta Oficial │   │     TSJ       │   │       TCP        │
  └───────┬────────┘   └───────┬───────┘   └────────┬─────────┘
          │                    │                    │
          ▼                    ▼                    ▼
   GacetaOficialScraper   TsjScraper         TcpScraper
          │                    │                    │
          └──────┬─────────────┴────────┬───────────┘
                 ▼                      ▼
      scrape_and_ingest_source (Celery, one per source)
                          │
                          ▼  (SHA-256 dedupe)
                   ingest_pdf()
                          │
                          ▼
              Corpus.import_content() → parser pipeline (Docling/Text)
                          │
                          ▼
             Per-area Corpus (+ pgvector embeddings)
                          │
                          ▼
                Specialist + Orchestrator agents
                          │
                          ▼
               GraphQL chat mutations (existing)
```

## Data model

Everything lives under `opencontractserver/bolivian_laws/`.

| Model | Purpose |
|---|---|
| `LegalAreaCorpus` | 1-to-1 idempotent mapping `area → Corpus`. Created on first ingest for each area. |
| `BolivianLegalDocument` | Tracking record per ingested PDF. `pdf_sha256` is globally unique for dedupe. Keeps `area`, `source` (gaceta / tsj / tcp / manual), `external_id`, `published_at`, status, and a FK to the resulting `Document`. |

### Legal areas

Defined in `constants.LegalArea`. Each area gets its own corpus and its
own specialist agent persona:

`constitucional · penal · civil · administrativo · laboral · tributario ·
familia · comercial · agrario · ambiental · otros`

### Sources

Defined in `constants.LegalSource`:

- `gaceta` — Gaceta Oficial de Bolivia (legislation)
- `tsj` — Tribunal Supremo de Justicia (ordinary jurisprudence)
- `tcp` — Tribunal Constitucional Plurinacional (constitutional jurisprudence)
- `manual` — Files uploaded via the management command

## Scrapers

Each source has a scraper class under
`opencontractserver/bolivian_laws/scrapers/`:

| File | Class | Source |
|---|---|---|
| `gaceta.py` | `GacetaOficialScraper` | `gacetaoficialdebolivia.gob.bo` |
| `tsj.py` | `TribunalSupremoJusticiaScraper` | `tsj.bo` |
| `tcp.py` | `TribunalConstitucionalScraper` | `tcpbolivia.bo` |

All three inherit from `BaseScraper`, which provides:

- Injectable `httpx.Client` (tests use `httpx.MockTransport` with HTML
  fixtures; no real HTTP).
- Polite User-Agent and configurable per-request sleep
  (`BOLIVIAN_LAWS_REQUEST_DELAY_SECONDS`).
- Defensive iteration: a failure on one listing page logs and moves on
  instead of aborting the batch.

Every scraper yields `ScrapedEntry` objects with best-effort metadata
(external ID, publication date, suggested legal area). The ingestion
task uses the suggested area and falls back to `OTROS` when no clear
match is found. Callers who want smarter classification can re-run
ingestion through the management command with `--auto-classify`.

## Celery wiring

Two tasks live in `tasks.py`:

- `scrape_and_ingest_source(source_key, *, since_days=None, max_entries=None, user_id=None)`
  runs a single scraper, deduplicates by SHA-256, and calls
  `ingest_pdf` for every new PDF. Returns a summary dict.
- `scrape_and_ingest_all(*, since_days=None, max_entries_per_source=None)`
  fans out one task per source.

The Beat schedule is wired up in `config/settings/base.py`:

```python
CELERY_BEAT_SCHEDULE = {
    ...
    "bolivian-laws-scrape-all": {
        "task": "bolivian_laws.scrape_and_ingest_all",
        "schedule": 86400.0,  # daily
    },
}
```

## Configuration

All knobs are environment-driven. Override only what you need.

| Variable | Default | Meaning |
|---|---|---|
| `BOLIVIAN_LAWS_GACETA_BASE_URL` | `https://gacetaoficialdebolivia.gob.bo/` | Base URL of the Gaceta site |
| `BOLIVIAN_LAWS_GACETA_LISTING_PATHS` | `/` | Comma-separated listing paths |
| `BOLIVIAN_LAWS_TSJ_BASE_URL` | `https://tsj.bo/` | Base URL of the TSJ site |
| `BOLIVIAN_LAWS_TSJ_LISTING_PATHS` | `/jurisprudencia/` | TSJ listing paths |
| `BOLIVIAN_LAWS_TCP_BASE_URL` | `https://tcpbolivia.bo/` | Base URL of the TCP site |
| `BOLIVIAN_LAWS_TCP_LISTING_PATHS` | `/jurisprudencia/` | TCP listing paths |
| `BOLIVIAN_LAWS_SCRAPER_USER_AGENT` | `OpenContractsBolivianLawsBot/1.0 ...` | Outgoing User-Agent |
| `BOLIVIAN_LAWS_SCRAPE_LOOKBACK_DAYS` | `30` | Ignore entries older than N days (when a date is parseable) |
| `BOLIVIAN_LAWS_REQUEST_DELAY_SECONDS` | `1.0` | Sleep between HTTP calls |
| `BOLIVIAN_LAWS_SPECIALIST_MODEL` | *(none)* | Override the model for specialist agents |
| `BOLIVIAN_LAWS_ORCHESTRATOR_MODEL` | `gpt-4o-mini` | Model for the orchestrator |
| `BOLIVIAN_LAWS_CLASSIFIER_MODEL` | `gpt-4o-mini` | Model for the LLM-based area classifier |

The LLM agents use whatever embedder/LLM credentials are already
configured for OpenContracts (`OPENAI_API_KEY`, etc.).

## Operator workflows

### Manual bulk ingest from a directory

```
python manage.py ingest_bolivian_laws \
  --path /data/leyes/ --area constitucional
```

- `--auto-classify` to let the LLM classifier pick the area.
- `--async` to enqueue Celery tasks instead of running inline.
- `--dry-run` to preview without writing.

### On-demand scrape (one source or all)

```
python manage.py scrape_bolivian_laws --source gaceta
python manage.py scrape_bolivian_laws --all --since-days 7 --sync
python manage.py scrape_bolivian_laws --source tcp --max-entries 5 --sync
```

Without `--sync`, the command enqueues Celery tasks and returns the
task IDs so you can watch them via Flower.

### Automatic periodic scrape

The Beat schedule runs `scrape_and_ingest_all` once a day. It's
idempotent: already-ingested PDFs are a no-op thanks to SHA-256
dedupe.

## Consuming the RAG programmatically

### Direct Python API

```python
from opencontractserver.bolivian_laws.services.agents import (
    ask_orchestrator, ask_specialists, consult_specialist,
)

# 1) Let the orchestrator decide which specialist(s) to consult:
result = await ask_orchestrator(
    "¿Qué dice la SCP 0250/2012 sobre la consulta previa?"
)
print(result.answer)
for src in result.sources:
    print(f"[{src.area}] doc#{src.document_id} — {src.snippet[:120]}")

# 2) Or target one specialist directly:
answer, sources = await consult_specialist(
    "penal", "Resume los elementos del tipo penal de trata de personas"
)

# 3) Or fan out across several specialists in parallel:
result = await ask_specialists(
    ["constitucional", "penal"],
    "Detención de menores sin orden judicial",
)
```

### GraphQL

The specialist corpora are regular OpenContracts corpora. Once ingested,
query them through the existing chat mutations:

```graphql
mutation {
  startConversation(corpusId: "<id-of-bolivia-constitucional>") {
    ok
    conversation { id }
  }
}

mutation {
  sendMessage(conversationId: "<id>", content: "¿Qué exige la Ley 1178?") {
    ok
    response { content sources { document { id title } } }
  }
}
```

You can look up the corpus IDs via `LegalAreaCorpus`:

```python
from opencontractserver.bolivian_laws.models import LegalAreaCorpus
{a.area: a.corpus_id for a in LegalAreaCorpus.objects.all()}
```

## Testing

```
docker compose -f test.yml run django pytest \
  opencontractserver/bolivian_laws/tests -n 4 --dist loadscope
```

The scraper tests use `httpx.MockTransport` with inline HTML fixtures
and never hit the real government sites.

## Operational notes

- **Robots.txt**: respect each site's crawling rules. The scrapers
  identify themselves with a clear User-Agent and rate-limit between
  requests.
- **First backfill**: set `BOLIVIAN_LAWS_SCRAPE_LOOKBACK_DAYS=0` and
  run `scrape_bolivian_laws --all --sync` once to seed the corpora,
  then let Beat handle daily updates.
- **Embedders are locked** after the first document is added to a
  corpus. Configure `preferred_embedder` before the first run if you
  want a non-default embedder.
- **Large volumes**: the TSJ/TCP archives are large. Use
  `--max-entries` or a short `--since-days` window during development
  to avoid embedding everything at once.
