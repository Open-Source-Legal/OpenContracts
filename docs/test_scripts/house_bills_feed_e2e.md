# Test: House-bills feed → authority-section push → enrichment → closure crawl

## Purpose
End-to-end verification of the house-bills core seams (PR #2279) with the real
`us-house-bill-feed` scraper and the `us-house-bills` pack (authority-packs
PR #12): pack install, token-gated push, drain into
`bootstrap_authority_corpus`, bill-grammar enrichment, and cited-USC closure
via the existing crawl.

## Prerequisites
- OpenContracts on `feature/us-house-bills-pack` (or main after #2279 merges).
- An isolated stack. With another compose project holding the fixed container
  names, use a neutral project + a `container_name` override file (see
  "Worktree Docker tests" memory; this run used `-p oc-seams-test`).
- Clones of `Open-Source-Legal/authority-packs` (branch with `us-house-bills`)
  and `Open-Source-Legal/us-house-bill-feed`.

## Steps
1. Migrate, create users, install the pack (sideload):
   ```bash
   docker compose -f test.yml -p oc-seams-test run --rm django bash -c "
     python manage.py migrate -v 0
     python manage.py shell -c \"from django.contrib.auth import get_user_model; get_user_model().objects.get_or_create(username='packcheck')\"
     python manage.py load_authority_pack --path /app/<mounted>/us-house-bills --creator packcheck --public"
   ```
   Expected: corpus `house-bills-119` created public with persona applied,
   `hr` namespace bound (`authority_type=bill`), seed docs + verified
   relationships + Fieldset present.
2. Lift the creator's usage cap (a 170-bill batch exceeds the 10-doc default):
   `u.is_usage_capped = False; u.save()`.
3. Mint a capability-granting token:
   ```bash
   python manage.py mint_worker_token --corpus <pk> --worker-name bill-feed-e2e \
     --allow-authority-sections --as-user <superuser>
   ```
   (Without `--allow-authority-sections` the push endpoint returns 403 — that
   IS a test case.)
4. Start a server and push a real window:
   ```bash
   docker compose -f test.yml -p oc-seams-test run --rm -d -p 18123:8000 django \
     python manage.py runserver 0.0.0.0:8000
   cd us-house-bill-feed && BILLFEED_WORKER_KEY=<token> \
     uv run billfeed sync --congress 119 --window-days 2 --push http://localhost:18123
   ```
5. Drain (test settings have no celery worker consuming the queue):
   `process_pending_section_batches.apply().get()` via `manage.py shell`.
6. Enrich: `EnrichmentService().apply(corpus_id=<pk>, creator_id=<packcheck>)`.
7. Close cited law:
   `CrawlAuthoritiesService.crawl(creator_id=…, corpus_id=<pk>, max_depth=0,
   min_demand=3, max_authorities=3, per_jurisdiction_cap=3)`.

## Expected Results (observed 2026-08-26)
- Sync: 170 bills seen, 169 built/pushed (1 **oversized** — `hr:119-8800` at
  2.8M chars — skipped AND reported; shipping it fails the whole batch on the
  ingest chain's 1M-char spaCy cap).
- Drain: batch COMPLETED; idempotence proven (78 created + 91 skipped after an
  interrupted earlier run); 791 `AuthorityRelationship` rows, 328 AMENDS, all
  `verified=True`; 164 worker-owned equivalences with 5 `skipped_owned`
  (pack-owned seed rows protected by the source-ownership partition).
- Enrichment: 4,070 references across 171 documents; 170 resolve immediately
  (bill-to-bill via `hr:` keys + equivalences); top externals are
  NDAA/SSA/PHSA/`publ:119-60` — the expected House-bill citation profile.
- Crawl: 333 frontier rows seeded; 3 USC sections fetched live from OLRC by
  the core `USCodeAuthoritySourceProvider` into an auto-created public
  `United-States-Code` corpus; resolved references 241; residuals honest
  (311 queued under the cap, 18 unsupported `act:*` keys, 1 failed).

## Cleanup
```bash
docker compose -f test.yml -p oc-seams-test down -v   # removes the demo stack
docker stop <runserver container>                      # if left running
```
