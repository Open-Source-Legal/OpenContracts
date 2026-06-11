# Test: Corpus Reference Enrichment on a real S-1 corpus

## Purpose
Prove the corpus reference enrichment engine (`opencontractserver/enrichment/`)
detects, normalizes, and persists the explicit references in a *real* S-1
filing corpus: external law citations (as cross-corpus-trackable stubs),
document/exhibit references (as in-app links), and internal section references.

## Prerequisites
- Migration `annotations/0078_corpusreference` applied.
- Local dev stack up (`docker compose -f local.yml`).
- An S-1 corpus loaded. NOTE: the local dev DB "thrashes" — corpus IDs get
  reassigned out from under you mid-session. Root cause (diagnosed 2026-06-09):
  this is NOT a periodic/celery-beat task and NOT this feature's code; it is
  *external manual activity* against the shared local Postgres — the
  `docs/test_scripts/smoke_reingest_remap.py` smoke script ("Smoke Source …"
  corpuses) and EDGAR scrape imports run from the `~/Code/EDGARx2/` workspace
  (an additional working dir) create/delete corpuses. The isolated **test
  database is unaffected**, so the pytest suite (`test_enrichment_*.py`) is the
  reproducible proof; this live run is a snapshot. Find the current S-1 corpus
  by title rather than assuming an ID. If none is loaded, import one of the v2
  zips under `~/Code/EDGARx2/` (e.g. `spacex_s1_oc_corpus_v3.zip`).

  For defined-term coverage, pass
  `types=list(__import__('opencontractserver.enrichment.constants', fromlist=['ALL_REFERENCE_TYPES']).ALL_REFERENCE_TYPES)`
  (defined terms are opt-in and excluded from the default scan/apply set).

## Steps

1. Find the current S-1 corpus and a user who can read it.
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   import warnings; warnings.simplefilter('ignore')
   from opencontractserver.corpuses.models import Corpus
   for c in Corpus.objects.all():
       n = c._get_active_documents().count()
       if n > 10:
           print(c.id, n, repr(c.title), 'creator', c.creator_id)
   "
   ```

2. Scan (read-only inventory — writes nothing). Replace `<CID>`/`<UID>`.
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   import warnings; warnings.simplefilter('ignore')
   from opencontractserver.enrichment.services import EnrichmentService
   out = EnrichmentService().scan(corpus_id=<CID>, creator_id=<UID>, sample_n=10)
   print('scanned', out['documents_scanned'], 'candidates', out['total_candidates'])
   print('by_type', out['counts_by_type'])
   print('by_status', out['counts_by_status'])
   "
   ```

3. Apply (approval-gated at the agent layer; direct here for the proof).
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   import warnings; warnings.simplefilter('ignore')
   from opencontractserver.enrichment.services import EnrichmentService
   from opencontractserver.annotations.models import Annotation, CorpusReference
   out = EnrichmentService().apply(corpus_id=<CID>, creator_id=<UID>)
   print(out)
   refs = CorpusReference.objects.filter(corpus_id=<CID>)
   print('LAW keys:', sorted(set(refs.filter(reference_type='LAW').values_list('canonical_key', flat=True)))[:15])
   print('DOC resolved:', refs.filter(reference_type='DOCUMENT', target_document__isnull=False).count())
   print('link_url anns:', Annotation.objects.filter(corpus_id=<CID>).exclude(link_url__isnull=True).exclude(link_url='').count())
   # Idempotency:
   out2 = EnrichmentService().apply(corpus_id=<CID>, creator_id=<UID>)
   print('re-apply created:', out2['annotations_created'], out2['references_created'])
   "
   ```

## Expected Results / Observed (corpus 25 "Select 2026 IPO S-1 Filings (SpaceX, Fervo Energy)", 55 docs, 2026-06-09)

- **Scan:** 55 documents scanned, **348 candidates** —
  `{'LAW': 59, 'DOCUMENT': 63, 'SECTION': 226}`;
  statuses `{'EXTERNAL': 59, 'RESOLVED': 242, 'UNRESOLVED': 47}`.
- **Apply:** 348 mention annotations + 348 `CorpusReference` rows created.
  - LAW canonical keys (cross-corpus stubs) included:
    `dgcl:116, dgcl:122(17), dgcl:151, dgcl:202, dgcl:203, dgcl:212, dgcl:224,
    dgcl:228, dgcl:242(b)(2), exchange-act:10(b), exchange-act:12,
    exchange-act:13(d), irc:451, securities-act:4(a)(2),
    securities-act:7(a)(2)(b), securities-act:8(a)`.
  - **16** DOCUMENT references resolved to a target document, each mention
    carrying a site-relative `link_url` like `/corpus/25/document/774` that the
    frontend routes in-app.
  - SECTION references resolved via the heading-text fallback (this corpus's
    docs lack a dense OC_SECTION index); where an OC_SECTION annotation exists
    and matches, an `OC_REFERENCES` Relationship is created instead (proven in
    `test_enrichment_writer.py::...creates_relationship`).
- **Idempotent re-run:** `annotations_created == 0`, `references_created == 0`.
- **Defined terms (opt-in, `types=ALL_REFERENCE_TYPES`):** 599 distinct terms
  across 925 definition sites — top cross-corpus stubs `term:company` (16 docs),
  `term:board`, `term:common-stock`, `term:change-in-control`,
  `term:class-a-common-stock`, `term:affiliate`. Each is a `DEFINED_TERM`
  `CorpusReference` with `resolution_status='RESOLVED'` and `canonical_key`
  `term:<slug>` (usage→definition linking is a future increment — deferred to
  avoid the volume explosion of high-frequency terms like "Company").

## Cleanup
Delete the run's rows (the `Analysis` groups them):
```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
import warnings; warnings.simplefilter('ignore')
from opencontractserver.annotations.models import CorpusReference, Annotation
from opencontractserver.enrichment import constants as C
CorpusReference.objects.filter(corpus_id=<CID>).delete()
Annotation.objects.filter(corpus_id=<CID>, annotation_label__text__in=[
    C.LABEL_REF_LAW, C.LABEL_REF_DOC, C.LABEL_REF_SECTION, C.LABEL_REF_TERM]).delete()
"
```
