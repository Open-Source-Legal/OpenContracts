# Bolivian Laws RAG Service

A multi-agent Retrieval-Augmented Generation (RAG) service over Bolivian
legal sources. Designed around two ideas:

1. **Cost-aware corpora**: one Corpus per legal area (constitucional,
   penal, civil, ...). Embeddings only run for the area you actually
   ingest, and similarity search never crosses areas.
2. **Multi-agent orchestration**: each area has a specialist agent
   (persona + corpus). A top-level orchestrator routes user questions to
   the relevant specialist(s) and synthesises one consolidated answer
   with citations.

## Architecture

```
       PDFs (flat dir)
            │
            ▼
  ingest_bolivian_laws  ─────►  ensure_area_corpus(area)
   (mgmt command)                 │
            │                     ▼
            │              Corpus<area>  (preferred_embedder, persona, instructions)
            │                     │
            ▼                     ▼
   ingest_pdf  ─►  Corpus.import_content  ─►  pgvector embeddings
                                              │
                                              ▼
GraphQL: askBolivianLaw  ─►  orchestrator  ─►  consult_<area> tool  ─►  specialist agent
                                  │                                        │
                                  └────────── synthesises ◄────────────────┘
```

## Legal areas

| `area` (key)      | Corpus slug              | Specialist persona                          |
|-------------------|--------------------------|---------------------------------------------|
| `constitucional`  | `bolivia-constitucional` | CPE 2009, jurisprudencia TCP                |
| `penal`           | `bolivia-penal`          | Código Penal, CPP, sala penal TSJ           |
| `civil`           | `bolivia-civil`          | Código Civil, contratos, sucesiones         |
| `administrativo`  | `bolivia-administrativo` | LPA, Ley SAFCO, contrataciones estatales    |
| `laboral`         | `bolivia-laboral`        | LGT, sala social TSJ                        |
| `tributario`      | `bolivia-tributario`     | Código Tributario, SIN, AIT                 |
| `familia`         | `bolivia-familia`        | Código de las Familias                      |
| `comercial`       | `bolivia-comercial`      | Código de Comercio                          |
| `agrario`         | `bolivia-agrario`        | Ley INRA, Tribunal Agroambiental            |
| `ambiental`       | `bolivia-ambiental`      | Ley 1333                                    |
| `otros`           | `bolivia-otros`          | residual                                    |

## Ingesting PDFs

PDFs live in a flat directory. The management command does
SHA-256-based dedupe (a given PDF is ingested at most once across all
areas).

```bash
# Explicit area (recommended for known batches):
docker compose -f local.yml run --rm django \
  python manage.py ingest_bolivian_laws \
    --path /data/leyes_constitucional/ \
    --area constitucional

# Mixed batch — let an LLM classify each PDF:
docker compose -f local.yml run --rm django \
  python manage.py ingest_bolivian_laws \
    --path /data/leyes_mix/ \
    --auto-classify

# Source attribution + async via Celery:
docker compose -f local.yml run --rm django \
  python manage.py ingest_bolivian_laws \
    --path /data/sentencias_tsj/ \
    --area civil --source tsj --async

# Dry-run: just list what would happen
docker compose -f local.yml run --rm django \
  python manage.py ingest_bolivian_laws \
    --path /data/leyes_mix/ --area civil --dry-run
```

### Filename convention (orientative)

`[area]_[year]_[number]_[title].pdf` — every segment is optional and
inferred best-effort by `infer_metadata_from_filename`. For example:

- `constitucional_2009_001_cpe.pdf` → area=constitucional, year=2009
- `ley_general_trabajo.pdf` → no area inference; falls back to `--area`
  or `--auto-classify`.

## Querying via GraphQL

The mutation `askBolivianLaw` is the single entry point. It returns a
synthesised answer plus tagged sources.

```graphql
mutation {
  askBolivianLaw(
    question: "Si soy detenido sin orden judicial, ¿qué garantías constitucionales y penales tengo?"
  ) {
    ok
    answer
    consultedAreas
    sources {
      area
      documentId
      snippet
      similarityScore
    }
  }
}
```

If the caller already knows which areas matter, they can skip
orchestration (cheaper + deterministic):

```graphql
mutation {
  askBolivianLaw(
    question: "¿Qué exige la Ley 1178?"
    areas: ["administrativo"]
  ) {
    answer
    consultedAreas
    sources { area snippet }
  }
}
```

`curl` example:

```bash
curl -s -X POST http://localhost:8000/graphql/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"query":"mutation { askBolivianLaw(question: \"¿Qué dice el art. 14 CPE?\") { answer consultedAreas sources { area snippet } } }"}' \
  | python3 -m json.tool
```

## Configuration

Environment variables (all optional, sensible defaults baked in):

| Var                                 | Default                   | Purpose                                |
|-------------------------------------|---------------------------|----------------------------------------|
| `BOLIVIAN_LAWS_DEFAULT_EMBEDDER`    | platform `DEFAULT_EMBEDDER` | embedder seeded for new area corpora |
| `BOLIVIAN_LAWS_CLASSIFIER_MODEL`    | `gpt-4o-mini`             | model used by `--auto-classify`        |
| `BOLIVIAN_LAWS_ORCHESTRATOR_MODEL`  | `gpt-4o-mini`             | orchestrator LLM                       |
| `BOLIVIAN_LAWS_SPECIALIST_MODEL`    | `""` (corpus default)     | override for specialist agents         |

LLM provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) are
read by the underlying `pydantic_ai` Agent. They can also be stored in
`PipelineSettings.encrypted_secrets` (see the LLM framework docs).

## Extending: adding a new area

1. Add a value to `LegalArea` and an entry to `AREA_PROFILES` in
   `opencontractserver/bolivian_laws/constants.py`.
2. Generate a migration that updates the `area` field choices.
3. Done. The orchestrator auto-discovers all `LegalArea` values when
   building its tools, and the management command exposes the new key
   via `--area`.

## Phase 3 roadmap (not yet implemented)

Automatic scrapers for:

- **Gaceta Oficial de Bolivia** (`gacetaoficialdebolivia.gob.bo`)
- **Tribunal Supremo de Justicia** (`tsj.bo`)
- **Tribunal Constitucional Plurinacional** (`tcpbolivia.bo`)

These will sit in `opencontractserver/bolivian_laws/scrapers/`, share a
`BaseLegalScraper` interface, and run via `CELERY_BEAT_SCHEDULE` daily.
For now ingestion is manual / batch via the management command.

## Risks

- **Cost**: orchestrator may invoke 1-N specialists per question.
  Mitigations: cheap specialist model; pass `areas` to bypass routing.
- **Latency**: parallel specialist calls (`ask_specialists` uses
  `asyncio.gather`) keep wall time bounded by the slowest specialist.
- **`preferred_embedder` is immutable** once a corpus has documents.
  Plan the embedder choice before the first ingest per area.
- **Auto-classification cost**: avoid `--auto-classify` for very large
  batches; prefer pre-sorted batches with `--area`.
