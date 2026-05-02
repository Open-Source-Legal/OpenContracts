# Proposal 0001 — Scheduled Scraping & Corpus Groups

**Status:** Draft (planning) — no implementation yet
**Related:** [PR #1305](https://github.com/Open-Source-Legal/OpenContracts/pull/1305) (Bolivian Laws RAG service)
**Date:** 2026-05-02

---

## Summary

PR #1305 ships a complete RAG service for Bolivian legal sources: three publisher scrapers, SHA-256 deduplication, eleven specialist agents per legal area, and an orchestrator that synthesizes cross-area answers. After review against the rest of the codebase, the only capabilities OpenContracts genuinely lacks today are:

1. **Scheduled scraping** that lands content in a Corpus on a recurring basis.
2. **Multi-corpus retrieval** for an agent that consults several corpora at once.

Everything else PR #1305 builds — per-corpus personas, streaming chat, citation rendering, conversation persistence, per-corpus permissioning — already exists in OpenContracts and is in production use today. This proposal extracts the two missing primitives into generic OC-native infrastructure, splits them across two sequential phases, and lays out the migration path that preserves PR #1305's contributions (scrapers, dedup logic, persona text) while making the same shape reusable for every future deployment.

The intent is for this proposal to be reviewed and ratified **before** any implementation work lands, including by [@jseborga](https://github.com/jseborga), the author of PR #1305.

---

## Why not just merge PR #1305 as-is

PR #1305 is high-quality work and the analysis below is not a critique of the contributor's craft — the scrapers are well-defended, tests use `httpx.MockTransport` correctly, and the persona text reflects real domain expertise. The architectural concerns are about reuse and overlap with existing OC primitives, not implementation quality.

**Overlap with existing OpenContracts primitives.** PR #1305's `bolivian_laws/` app re-implements capabilities that already exist:

| PR #1305 capability                               | Existing OC primitive                                                              |
| ------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `LegalAreaCorpus` 1-to-1 area→corpus              | `Corpus` rows with `corpus_agent_instructions` — already supports per-corpus persona |
| `BolivianLegalDocument` SHA-256 dedup record      | Generic — could live on any source, not just Bolivian                              |
| `build_specialist_agent(area)`                    | `oc_agents.for_corpus(corpus_id)` already injects `corpus_agent_instructions`      |
| `AskBolivianLawMutation` GraphQL mutation         | `UnifiedAgentConsumer` over `ws/agent-chat/?corpus_id=X` already streams + cites   |
| `BOLIVIAN_LAWS_*` env vars + Beat schedule        | Hardcoded — should be DB-driven so admins manage sources without redeploy           |

**Bolivia-specific shape.** The `bolivian_laws/` namespace, the `LegalAreaCorpus` 1-to-1 model, and the `askBolivianLaw` GraphQL mutation are all bound to one country. A community deployment for Brazilian jurisprudence, EU regulations, internal compliance feeds, or any other recurring-scrape source would have to copy-paste the entire app and rename it.

**Architecture mismatches that would compound over time.**

- **Hardcoded Beat schedules** in `config/settings/base.py` mean adding a new source requires a code change and redeploy; OC's pattern is DB-driven config (`PeriodicTask`).
- **Specialist+orchestrator wired in code** means adding a 12th legal area requires a Python edit, a constant change, and a redeploy; the equivalent should be a single `Corpus` row in admin.
- **Concurrent dedup race window** — SHA check and create are not in a single `select_for_update` transaction; two parallel scrapes of the same PDF can both pass the dedup check.

The proposal below addresses each of these while preserving the parts of PR #1305 that genuinely belong in the codebase: the three scrapers, the dedup approach, the persona text, and the testing pattern.

---

## Phase A — Generic scheduled scraping (foundation)

### Goal

Any admin can register a scraper that runs on a schedule, deduplicates by content hash, and lands new PDFs in a `Corpus` they choose. End-users interact via the existing `<CorpusChat>` UI — no new chat transport, no new GraphQL mutation, no new React component.

### New app `opencontractserver/scraping/`

#### Models

```python
class ScrapedSource(models.Model):
    """An external publisher scraped on a schedule, landing PDFs in a Corpus."""
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    scraper_key = models.CharField(max_length=128)            # registry key, e.g. "bolivia.gaceta"
    base_url = models.URLField()
    listing_paths = models.JSONField(default=list)            # e.g. ["/leyes/", "/decretos/"]
    rate_limit_seconds = models.FloatField(default=1.0)
    request_timeout_seconds = models.FloatField(default=30.0)
    user_agent = models.CharField(max_length=200, blank=True)
    target_corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.PROTECT,
        related_name="scraped_sources",
    )
    schedule_crontab = models.CharField(max_length=64, blank=True)   # "" => manual only
    enabled = models.BooleanField(default=True)
    extra_config = models.JSONField(default=dict, blank=True)        # scraper-specific knobs
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(max_length=16, default="pending")  # pending|ok|error

    class Meta:
        permissions = [("trigger_scrape", "Can manually trigger a scrape")]


class ScrapedDocument(models.Model):
    """Per-source ingestion record for SHA-256 dedup and provenance."""
    source = models.ForeignKey(ScrapedSource, on_delete=models.CASCADE, related_name="documents")
    pdf_sha256 = models.CharField(max_length=64, db_index=True)
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="scraped_records",
    )
    external_id = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(blank=True)
    published_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, default="pending")   # pending|imported|failed
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("source", "pdf_sha256")]
        indexes = [models.Index(fields=["source", "status"])]
```

**Permissioning.** `ScrapedSource` uses django-guardian object-level perms. `visible_to_user(user)` filters by guardian AND by visibility of `target_corpus` — you can only see a source if you can see the corpus it writes into. The `triggerScrape` mutation requires the new `trigger_scrape` perm.

#### Scraper registry

`scraping/scrapers/registry.py` mirrors `opencontractserver/pipeline/registry.py`'s singleton + `_discover_subclasses` + `lru_cache` pattern.

```python
class BaseScraper:
    key: ClassVar[str]                  # "bolivia.gaceta"
    title: ClassVar[str]                # "Gaceta Oficial de Bolivia"
    config_schema: ClassVar[dict] = {}  # JSON schema for ScrapedSource.extra_config

    def __init__(self, source: ScrapedSource, http_client=None): ...

    async def aiter_entries(
        self,
        *,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[ScrapedEntry]: ...
```

`ScrapedEntry` is a dataclass: `pdf_url`, `external_id`, `published_at`, `metadata` (sala/area hint/etc). The metadata is informational only — corpus selection happens on the `ScrapedSource` row, not inside the scraper.

In-tree only for v1 (no entry-point plugin discovery). Auto-discovery walks `scraping/scrapers/` and registers every `BaseScraper` subclass at app-ready time.

#### Services

- **`ingestion.py::ingest_pdf(source_id, pdf_bytes, *, external_id, published_at, metadata)`**:
  - SHA-256 hash inside a `transaction.atomic()` block, `select_for_update` on any pre-existing `(source, sha256)` row to close the race window.
  - Idempotent: if already imported, return existing record without re-importing.
  - Else: create `ScrapedDocument(status="pending")`, call `Corpus.import_content(target_corpus, file_bytes, …)`, attach the resulting `Document` FK, mark `status="imported"`. On failure, mark `status="failed"` with `error_message`.
- **`runner.py::run_scrape(source_id, *, since_days=None, max_entries=None)`**: instantiate scraper from registry, iterate entries, fetch each PDF (httpx), call `ingest_pdf`. Returns `ScrapeReport(scraped, ingested, deduped, failed)`. Updates `source.last_run_at` and `source.last_run_status`.
- All ORM access wrapped via `sync_to_async` per CLAUDE.md pitfall #13.

#### Celery + Beat

Tasks in `scraping/tasks.py`:

- `scrape_source(source_id, since_days=None, max_entries=None)` — wraps `run_scrape`.
- `scrape_all_enabled_sources()` — fan-out to every enabled source with a non-empty schedule.

**Beat schedule built dynamically at worker startup.** A `celery.signals.beat_init` handler (and `post_save`/`post_delete` signal on `ScrapedSource`) syncs schedules into `django-celery-beat`'s `PeriodicTask` table. **No hardcoded daily Beat entries in `config/settings/base.py`** — admins manage sources via Django admin without redeploy.

#### Management commands

- `manage.py scrape <source-name> [--since-days N] [--max-entries N] [--sync]` — manual run; default `.delay()`, `--sync` runs inline.
- `manage.py ingest_scraped <source-name> <path-or-glob> [--async]` — bulk-import local PDFs into a source's target corpus, applying the same dedupe/ingestion path. Useful for backfills before turning on scheduled runs. **Replaces PR #1305's `ingest_bolivian_laws`** with a generic equivalent.
- `manage.py list_scrapers` — print all registered `scraper_key`s and their config schemas.

#### GraphQL surface

- Query: `scrapedSources(visibleToMe)` → relay-paginated list with `lastRunAt`, `lastRunStatus`, `targetCorpus`.
- Query: `scrapedDocuments(sourceId, status)` → ingestion records for status dashboards.
- Mutations: `createScrapedSource`, `updateScrapedSource`, `deleteScrapedSource` — admin-only, sets guardian perms on creation.
- Mutation: `triggerScrape(sourceId)` — gated on `trigger_scrape` perm; `.delay()`s `scrape_source`.
- All types use `AnnotatePermissionsForReadMixin`.

#### Admin

`scraping/admin.py` exposes `ScrapedSource` (with inline `ScrapedDocument` history and a "Run now" admin action) and a read-only `ScrapedDocument` admin for triage of failed ingests.

#### Tests

- `test_registry.py` — discovery covers all in-tree scrapers; unknown `scraper_key` raises.
- `test_ingestion.py` — atomic dedupe race (use `pytest.mark.serial` + threads), failure path leaves `status="failed"`, idempotent re-run.
- `test_runner.py` — `run_scrape` happy path with `httpx.MockTransport`, partial failure does not abort batch.
- `test_tasks.py` — `scrape_source.delay()` invokes runner with right args.
- `test_commands.py` — `scrape` + `ingest_scraped` flag wiring.
- `test_graphql.py` — **GraphQL coverage including permission boundary**: anonymous rejected; user without source visibility gets empty list; user with `trigger_scrape` can trigger; user without can't.
- `test_bolivia_scrapers.py` — three `httpx.MockTransport`-based fixtures parsing real-shape HTML stubs (ported from PR #1305).

#### Settings additions

- `INSTALLED_APPS += ["opencontractserver.scraping"]`
- `SCRAPING_DEFAULT_USER_AGENT` (default `"OpenContractsScraperBot/1.0 (+https://github.com/Open-Source-Legal/OpenContracts)"`)
- `SCRAPING_DEFAULT_REQUEST_DELAY_SECONDS` (default `1.0`)
- **No Beat schedule entries** — DB-driven.

### What happens to PR #1305

When Phase A lands:

- PR #1305's `opencontractserver/bolivian_laws/scrapers/{base,gaceta,tsj,tcp}.py` move into `scraping/scrapers/bolivia/{gaceta,tsj,tcp}.py`, refactored to subclass the new `BaseScraper`. The defensive HTML parsing, `httpx.MockTransport` testability, and metadata extraction stay intact.
- PR #1305's `_guess_area_*` heuristics survive as `metadata` hints in `ScrapedEntry` rather than corpus selectors.
- PR #1305's `ingest_bolivian_laws` and `scrape_bolivian_laws` management commands are replaced by the generic `manage.py scrape` and `manage.py ingest_scraped`.
- PR #1305's `bolivian_laws/` app, `BOLIVIAN_LAWS_*` settings, hardcoded Beat schedule, and `askBolivianLaw` GraphQL mutation are deleted in the same diff.
- **The eleven specialist personas survive** as `corpus_agent_instructions` text on eleven `Corpus` rows — either created via Django admin or via an optional fixture YAML at `scraping/fixtures/bolivia.yaml`.

The intent is to credit [@jseborga](https://github.com/jseborga) as co-author on the Phase A implementation PR, since the scrapers and dedup approach are direct ports of their work.

### Workflow under Phase A (Bolivia deployment example)

1. Admin loads the optional fixture (or hand-creates rows): 11 `Corpus` rows with persona text on `corpus_agent_instructions`.
2. Admin creates 3 `ScrapedSource` rows (Gaceta, TSJ, TCP), each pointing at the appropriate corpus, with `schedule_crontab="0 3 * * *"`.
3. Beat picks up the schedules at next worker restart; PDFs flow in nightly with SHA dedup. (Or the admin clicks "Run now" in admin to backfill.)
4. End-user opens any of the 11 corpora in the SPA → `<CorpusChat>` opens against `ws/agent-chat/?corpus_id=X` → asks a question → gets streaming answers with citations. The specialist persona is the corpus's `corpus_agent_instructions`.

No new UI. No new mutation. No new transport.

### Verification

1. `docker compose -f local.yml run django python manage.py migrate`
2. Admin creates a test `Corpus` and a `ScrapedSource` pointing at it.
3. `python manage.py scrape "Test Source" --max-entries 2 --sync` → check `ScrapedDocument` rows imported, `Document` rows in the corpus.
4. SPA: open the corpus → existing `CorpusChat` works against scraped PDFs.
5. `pytest opencontractserver/scraping/tests -n 4 --dist loadscope` — all green.

---

## Phase B — Corpus Groups + multi-corpus retrieval (separate, follow-up)

### Goal

An admin curates a named bundle of corpora and binds a single agent to all of them. Users chat that agent and the agent decides which corpora to consult, returning answers with per-corpus citations. **Replaces** PR #1305's specialist+orchestrator pattern with a generic primitive that costs ~20 lines of fixture data per deployment.

### `CorpusGroup` model

```python
class CorpusGroup(models.Model):
    slug = models.SlugField(unique=True, max_length=64)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    corpora = models.ManyToManyField("corpuses.Corpus", related_name="groups")
    default_agent = models.ForeignKey(
        "agents.AgentConfiguration",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="default_for_groups",
    )
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

Guardian object perms; `visible_to_user(user)` filters by perms AND filters `corpora` to those visible to the user (a half-visible group still works, just narrower).

### Multi-corpus retrieval tool

A new `CoreTool`:

```python
async def asearch_across_corpora(
    query: str,
    corpus_ids: list[int],
    *,
    user_id: int | None = None,
    top_k: int = 8,
) -> list[SourceNode]:
    """Run similarity search across multiple corpora.
    Returns chunks tagged with metadata.corpus_id and metadata.corpus_title.
    Filters corpus_ids to those visible to the calling user before searching.
    """
```

Registered in `UnifiedToolFactory`. An `AgentConfiguration` row that uses this tool stores its `corpus_ids` in tool config (frozen at config time) — that's how the orchestrator's "knows about these N corpora" works.

### WebSocket consumer

`UnifiedAgentConsumer.connect()` already accepts `?agent_id=<X>` and loads that `AgentConfiguration`. **No new transport** — Phase B agents bind to a global agent that has the multi-corpus tool.

Open question: how Conversations bind to groups. Options: (a) bind to first corpus in group, (b) add a `Conversation.chat_with_corpus_group` FK (one migration), (c) leave group conversations ephemeral. Likely (b). Resolved at implementation time, not now.

### GraphQL surface

- Query: `corpusGroups(visibleToMe)` → relay-paginated.
- Mutations: `createCorpusGroup`, `updateCorpusGroup` (sets/replaces M2M), `setCorpusGroupDefaultAgent`.
- The frontend opens a group's chat via the existing `useAgentChat` with `agentId=<group.defaultAgent.id>`.

### What happens to PR #1305 (Phase B)

The 11 Bolivian-area corpora plus a `CorpusGroup "Bolivian Laws"` plus a single `AgentConfiguration "Bolivian Laws Orchestrator"` wired with `asearch_across_corpora` + the orchestrator persona collapses PR #1305's specialist+orchestrator pattern into ~20 lines of fixture data. PR #1305's `ORCHESTRATOR_PERSONA` becomes that `AgentConfiguration`'s `system_instructions`. The eleven specialist personas live on each corpus's `corpus_agent_instructions` (where they belong).

### Tests

- `test_corpus_group_visibility.py` — group filters corpora to visible.
- `test_multi_corpus_retrieval.py` — tool searches union of corpora, tags `metadata.corpus_id`, filters out corpora user can't read.
- `test_group_chat_e2e.py` — end-to-end: open agent via WebSocket with group-bound `agent_id`, chat returns multi-corpus citations.

---

## Migration story for PR #1305

We propose to land Phase A as a follow-up PR with [@jseborga](https://github.com/jseborga) credited as co-author (via `Co-Authored-By:` trailer or PR description, whichever the contributor prefers). PR #1305 itself can stay open as the reference implementation while Phase A is reviewed and merged; once Phase A lands, PR #1305 either closes (if the contributor is happy) or rebases into a small fixture PR that creates the eleven Bolivian corpora and three `ScrapedSource` rows.

The non-negotiable preservation list:

- All three scrapers (Gaceta, TSJ, TCP) — same parsing logic, same `httpx.MockTransport` testing, same metadata extraction.
- SHA-256 dedup approach (with the race-window fix added).
- Eleven specialist persona texts (verbatim, on `corpus_agent_instructions`).
- Orchestrator persona text (verbatim, on `AgentConfiguration.system_instructions` once Phase B lands).
- The bulk-ingest workflow (generalized as `manage.py ingest_scraped`).
- The `httpx.MockTransport`-based testing pattern.

What goes away:

- The `bolivian_laws/` namespace — the work survives, the framing generalizes.
- The `LegalAreaCorpus` 1-to-1 model — `Corpus` is enough on its own.
- The `askBolivianLaw` GraphQL mutation — `ws/agent-chat/?corpus_id=X` and `?agent_id=Y` already cover this.
- Hardcoded Beat schedules — DB-driven via `ScrapedSource.schedule_crontab`.
- `BOLIVIAN_LAWS_*` settings — config moves to `ScrapedSource.base_url` + `extra_config`.

---

## Open questions / decisions deferred

- **Phase B Conversation binding** — `chat_with_corpus_group` FK vs ephemeral group convos. Resolved at implementation time.
- **Out-of-tree scrapers** — explicitly deferred; in-tree only for v1 per maintainer preference. If a community deployment wants their own scraper plugged in without forking, we can revisit with entry-point discovery later.
- **Fixture loader for Bolivia** — optional. Could ship as `manage.py loaddata bolivia.yaml`, or leave admin to create rows manually. Doesn't affect the rest of the design.

---

## Order of work (when implementation starts)

1. Phase A models, migrations, admin → smoke test.
2. Phase A scraper registry + base + Bolivia scrapers (port from PR #1305).
3. Phase A services (ingestion, runner) → unit tests.
4. Phase A Celery tasks + Beat sync signal → task tests.
5. Phase A management commands.
6. Phase A GraphQL queries + mutations → permission boundary tests.
7. Phase A: delete PR #1305's `bolivian_laws/` app and `bolivian_laws_mutations.py`.
8. Phase A: CHANGELOG, full pytest run.
9. Pause for review / merge.
10. Phase B as a separate PR.

---

## What this PR contains

This PR contains **only this design doc** — no code, no migrations, no tests. The intent is to reach alignment on the architecture before any implementation starts. If the direction lands well, Phase A will be implemented as a follow-up PR.
