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

## Recorded run — 2026-08-09 (corpus 123, pack at 23d044b)

**6 of 10 pass on substance. 4 fail by falling back to general knowledge.**
Scored on substance, not on citation formatting — the agent cites by quoting a
source snippet more often than by section number.

| # | Result | Notes |
|---|---|---|
| 1 water heater | **pass** | "changing, moving or repairing plumbing, including water heaters … requires a plumbing permit"; homeowner may do the work; inspection required |
| 2 fence | **partial** | Correctly Fort-Worth-specific (front yard 4 ft, open design, 50% density, no chain link) but gave a 6 ft solid-fence permit threshold where § 105.2 exempts to 7 ft — two city sources disagree; worth reconciling |
| 3 own electrical | **FAIL** | Generic "depends on your state, county" — never reached `tx-occ:1305.003(a)(6)`. The single most important homeowner question |
| 4 drywall | **FAIL** | Generic; missed the 16 sq ft threshold that is in the ingested Nuts & Bolts guide |
| 5 re-roof | **pass** | Exactly right: shingles only → no permit; replacing decking/sheathing → permit. Matches the § 105.2 boundary |
| 6 shed | **pass** | "All storage sheds require a building permit, regardless of size" — correct, and contradicts the common under-200-sq-ft assumption |
| 7 contractor registration | **pass** | Homeowner may pull their own permit, no contractor registration number, proof of ownership required |
| 8 inspections | **FAIL** | Asked for more detail and listed generic inspection types instead of the Fort Worth 105/115/110/100 sequence |
| 9 HOA solar | **FAIL** | Generic "many states have solar rights acts"; never reached `tx-prop:202.010` |
| 10 code editions | **pass** | Correct list from city sources |

### Second run — full embedding coverage (2026-08-09 23:47)

Re-run after all four authority corpora reached 100% embedding coverage
(they were only ~10-20% embedded during the first run). **All four failures
reproduced identically.** Indexing was never the cause.

Counting retrieval calls per question (`Embedding text with MicroserviceEmbedder`
in the log is proof of a semantic search — a phrase lookup embeds nothing) splits
the failures cleanly:

| Question | searches | outcome |
|---|---|---|
| Q4 drywall | **0** | never searched; answered from model priors |
| Q9 HOA solar | **0** | never searched; cited **California Civil Code § 714** to a Texas homeowner |
| Q3 own electrical | 1 | searched, got results, still answered generically |
| Q8 inspections | 1 | searched, got results, still answered generically |

All other questions: 1 search each. Zero "no results from either arm" across the
whole run — when the agent searched, retrieval returned something.

**So there are two distinct defects, not one:**

1. **Tool-call omission (Q4, Q9).** The agent skips retrieval entirely and
   answers from priors. Q4's answer ("16 sq ft") is *in* the corpus; Q9's
   generic answer is actively wrong for Texas. The persona says "answer from
   these documents" but nothing *forces* a search. Fix is prompt/tool discipline
   — require a retrieval call before answering, or make the search tool
   mandatory on first turn.
2. **Grounding dilution (Q3, Q8).** Retrieval ran and returned results, and the
   model still produced generic text. Q8's inspection numbers exist in four
   corpus documents, so this is ranking/weighting rather than coverage. Q3's
   operative text (`tx-occ:1305.003`) lives in corpus 122 and is genuinely
   unreachable — see the reachability note below.

The earlier hypothesis that incomplete embeddings caused Q4/Q8 was **wrong**:
the 859 unembedded corpus-123 annotations are `OC_REF_LAW` citation markers
created by enrichment ("ORDINANCE NO. 25384-03-2022"), not document text
chunks. The document chunks were fully embedded for both runs.

### Diagnosis of the four failures

The failures are not random. **Every one of them has its answer in an authority
corpus rather than in corpus 123's own documents** — electrical exemption in
`tx-occ`, solar in `tx-prop`, the inspection sequence in `fw-admin-code` §110.
Q4 is the partial exception (the 16 sq ft rule *is* in an ingested PDF).

A corpus agent retrieves over its own chunks. It reaches an authority corpus
only through a resolved reference edge (`read_reference_target`), and only 20 of
875 references resolved — **none into `tx-occ` or `tx-prop`, because the city's
permit guides do not cite the Occupations or Property Code at all.** The
statutes are correctly installed and directly resolvable
(`find_authority_target("tx-occ:1301.051", user)` returns the section), but
nothing in the document corpus points at them, so the agent never traverses to
them.

This is an architecture gap, not a pack defect: the authority corpora need to be
*reachable* from the conversational corpus by something other than a citation
edge. The candidates, in the order worth trying:

1. Put corpora 119–123 in a **corpus group** so the agent can search across them.
2. Use **@mention delegation** to the authority corpus agents — note the prior
   finding that a mention only *offers* a delegate tool; plain phrasing silently
   answers from one corpus.
3. Seed the homeowner corpus with a short "how the law fits together" document
   that cites the key statutes, giving enrichment an edge to resolve.

Re-run this gate after any of those before claiming the corpus answers
"can I do the work myself" correctly.

## Cleanup

```bash
docker compose -f local.yml -p opencontracts exec -T django python manage.py shell -c "
from opencontractserver.corpuses.models import Corpus
Corpus.objects.filter(id__in=[119,120,121,122,123]).delete()"
```

Deleting the pack corpora leaves the `AuthorityNamespace` rows bound to
now-missing corpora; re-running the install re-converges them.
