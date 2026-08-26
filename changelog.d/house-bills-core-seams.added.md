- **Tier-2a bill-citation grammar** (`opencontractserver/enrichment/grammars.py::_bills`):
  "H.R. 1234" / "S. 987" / joint, concurrent, and simple resolution forms now
  extract as congress-unqualified shape keys (`hr:1234`, `s:987`, `hjres:44`, …)
  with guards against `U.S.` reporter citations, `U.S.C.` cites, `§` sections,
  and UK-style lowercase `s. 987`. Packs fold these onto congress-qualified
  keys via equivalences (the ECCN pattern). New classification vocabulary:
  `AUTHORITY_TYPE_BILL`, `GRAMMAR_BILL_PREFIXES`
  (`opencontractserver/enrichment/constants.py`) and
  `AuthorityWeight.PROPOSED` (`opencontractserver/enrichment/authority_sources.py`)
  for introduced-but-not-enacted instruments.
- **Authority-section push endpoint** for external harvesters:
  `POST /api/worker-uploads/authority-sections/` (+ status/list routes) accepts
  a `parse_section_spec`-shaped JSON batch (+ optional equivalence rows) under
  an existing `CorpusAccessToken`, stages it in the new
  `WorkerAuthoritySectionBatch` model (migration `worker_uploads.0005`), and a
  drain task (`process_pending_section_batches`) feeds
  `bootstrap_authority_corpus` with `relink_async=True` and upserts
  equivalences under source `worker:<account>`. Target corpus always comes from
  the token (IDOR-safe by construction), and the capability is an explicit
  off-by-default grant — `CorpusAccessToken.can_push_authority_sections`
  (migration `worker_uploads.0006`, `mint_worker_token
  --allow-authority-sections`) — so pre-existing document-upload tokens do not
  silently gain the larger blast radius. Payload cap via new
  `MAX_AUTHORITY_SECTION_PAYLOAD_BYTES` setting; stalled batches recovered by
  the existing `recover_stalled_uploads` sweep; periodic drain added to
  `CELERY_BEAT_SCHEDULE`. Docs: `docs/guides/ingesting-authorities.md` Part 3.
  This gives any external harvester (legislation feeds, eCFR watchers, caselaw
  feeds) a continuous remote update path that previously required a full pack
  re-install or in-container management commands.
