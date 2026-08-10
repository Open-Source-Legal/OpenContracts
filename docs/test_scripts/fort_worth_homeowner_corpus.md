# Test: Fort Worth homeowner authority pack + corpus

## Purpose

Verify that the `fort_worth` authority pack's residential-construction corpora
install correctly, that a corpus of City of Fort Worth permit guidance enriches
against them, and that the corpus agent answers homeowner questions with
pinpoint citations rather than plausible-sounding generalities.

This is the acceptance gate for the pack extension in
`Open-Source-Legal/authority-packs` PR #1.

## Prerequisites

- A running local stack (`local.yml`) with `postgres` on the **local** volume
  (`opencontracts_local_postgres_data`, not the test volume).
- The pack checked out, e.g. `~/Code/Authorities/authority-packs/fort_worth`.
- A superuser named `admin`.
- Free disk on `/tmp` — Chromium and Celery both need it. A full `/tmp` will
  crash headless Chromium mid-harvest and can truncate downloads.

## Steps

### 1. Preflight the pack

```bash
docker cp ~/Code/Authorities/authority-packs/fort_worth opencontracts-django-1:/tmp/fw_pack
docker compose -f local.yml -p opencontracts exec -T django \
  python manage.py load_authority_pack --path /tmp/fw_pack --creator admin --check
```

Expect: `pack is valid; 7 corpus/corpora would converge` — 3 UPDATE
(`fort-worth-city-code`, `fort-worth-charter`, `texas-procurement-law`) and
4 CREATE.

### 2. Install

```bash
docker compose -f local.yml -p opencontracts exec -d django sh -c \
  "python manage.py load_authority_pack --path /tmp/fw_pack --creator admin --public \
   > /tmp/pack_install.log 2>&1"
```

**Only ever run one install at a time.** Two concurrent runs deadlock on the
`AuthorityNamespace` `select_for_update`, and because the install is atomic it
shows no partial progress while blocked — it looks hung rather than stuck. If
an install appears hung, check for a second process before assuming failure:

```bash
docker compose -f local.yml -p opencontracts exec -T django sh -c \
  'for p in /proc/[0-9]*; do c=$(tr "\0" " " < $p/cmdline 2>/dev/null); \
   case "$c" in *load_authority_pack*) echo "$p :: $c";; esac; done'
```

### 3. Verify namespace bindings

```bash
docker compose -f local.yml -p opencontracts exec -T django python manage.py shell -c "
from opencontractserver.annotations.models import AuthorityNamespace as AN
for n in AN.objects.filter(prefix__in=['muni-fort-worth','fw-admin-code','fw-res-code','fw-zoning','tx-occ','tx-prop','irc']).order_by('prefix'):
    print(n.prefix, n.authority_corpus_id, n.is_global, n.display_name)"
```

Expect each new prefix bound to exactly one corpus, and — importantly — `irc`
still **global** and still displaying as *Internal Revenue Code*. The
International Residential Code must never take that prefix.

### 4. Restart workers

The pack-config loader is `lru_cache`d per process, so the pack's
`abbreviations` do not reach the grammar tier until workers restart.

```bash
docker restart celeryworker celeryworker_parse
```

### 5. Ingest the document corpus

```bash
docker cp <staged-pdfs>/ opencontracts-django-1:/tmp/fw_corpus
docker compose -f local.yml -p opencontracts exec -d django sh -c \
  "python manage.py ingest_corpus --path /tmp/fw_corpus \
   --title 'Fort Worth Homeowner — Permits, Codes & DIY' \
   --owner admin --wait --enrich --public --timeout 5400 > /tmp/corpus_ingest.log 2>&1"
```

Note `--owner`, not `--creator`.

**Expect a queue wait.** The pack seeds 881 sections as documents, and each one
runs the full parse+embed chain. Those tasks land on the **default** `celery`
queue — as does `convert_document_to_pdf`, the head of every parse chain — so a
corpus ingested right after a pack install queues behind roughly 2,300 tasks.
The dedicated `doc_parse` worker cannot help: it only serves `doc_parse`, and
the chain head is not on that queue.

```bash
docker exec redis redis-cli LLEN celery      # backlog
docker exec redis redis-cli LLEN doc_parse
```

`vector-embedder` is CPU-bound (~400% on 8 cores). Batches occasionally exceed
the 60 s client read timeout and retry; this is throughput, not failure.
Running fewer all-queue workers concurrently reduces the retry rework.

### 6. Run the gold questions

```bash
docker cp run_gold_questions.py opencontracts-django-1:/tmp/
docker compose -f local.yml -p opencontracts exec -T django \
  sh -c "python manage.py shell < /tmp/run_gold_questions.py"
```

## Expected Results

Ground truth is quoted from primary sources, not recalled. An answer is wrong
if it misses the "must-not-miss" point even when it sounds right.

| # | Question | Must-not-miss |
|---|---|---|
| 1 | Water heater replacement | Plumbing permit required; `tx-occ:1301.051` exempts the owner from *licensure* in their homestead but waives neither permit nor inspection |
| 2 | Fence height / permit | No **building** permit up to 7 ft (open wire without slats, 8 ft) per § 105.2 — **but zoning still governs** height and placement |
| 3 | Own electrical work | `tx-occ:1305.003(a)(6)` applies only to work *"not specifically regulated by a municipal ordinance"* — quote the conditioning clause; not the same shape as the plumbing exemption |
| 4 | Drywall replacement | Permit at **16 sq ft or more**; § 105.2 exempts finish work (paint, paper, tile, carpet, cabinets, countertops), which drywall is not |
| 5 | Re-roof | Exemption covers material **above but not including** decking/lathing/sheathing — touching decking ends the exemption |
| 6 | Storage shed | § 105.2 has **no** small-accessory-building exemption; do not import the "under 200 sq ft" rule from other jurisdictions |
| 7 | Contractor registration | `fw-admin-code:118` |
| 8 | Inspections | Sequence 105 → 115 → 108 → 110 → 100, trade finals 200/300/400; `fw-admin-code:110` |
| 9 | HOA vs solar | `tx-prop:202.010`; agent holds the statute, not the covenants — must not state what a particular HOA allows |
| 10 | Adopted code editions | Mixed vintage: 2021 IRC/IBC/IMC/IPC/IFGC/IEBC, **2015** IECC, **2018** ISPSC, **2023** NEC |

Fee figures must always be flagged verify-with-Development-Services: the
codified tables (§§ 109, 119) are law, but the published Development Fees
Schedule is revised more often.

## Cleanup

```bash
docker compose -f local.yml -p opencontracts exec -T django python manage.py shell -c "
from opencontractserver.corpuses.models import Corpus
Corpus.objects.filter(id__in=[119,120,121,122,123]).delete()"
```

Deleting the pack corpora leaves the `AuthorityNamespace` rows bound to
now-missing corpora; re-running the install re-converges them.
