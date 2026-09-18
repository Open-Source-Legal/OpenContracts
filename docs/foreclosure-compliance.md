# California Foreclosure Compliance

Runs the `legalis-ca-foreclosure` ruleset — Civ. Code § 2924 et seq. encoded as
dated, versioned rules — over a corpus of recorded instruments and produces a
compliance chronology.

> **No rule encoding has been reviewed by a licensed attorney.** The analyzer
> reports this in every result. Output is not legal advice.

## Why a corpus analyzer

A foreclosure matter maps onto a corpus: each recorded instrument — Notice of
Default, Notice of Trustee's Sale, Trustee's Deed — is a document, and the
matter is the corpus they belong to.

It is corpus-scoped rather than per-document because no single instrument
answers the question. Whether the three-month period under § 2924(a)(2) elapsed
needs the Notice of Default *and* the Notice of Sale together.

## Architecture

```
Corpus of recorded instruments
      │  matter.py — instrument kind + dates off each document
      ▼
matter payload (JSON)
      │  client.py — HTTP
      ▼
foreclosure-api  (Rust, legalis-ca-foreclosure-api)
      │  dated statutory rules
      ▼
compliance report → Analysis.result_message
```

The ruleset runs as a **separate service, not in-process**. It is Rust; an FFI
boundary would couple this deployment to a Rust toolchain and turn the
ruleset's panics into Celery worker crashes. Over HTTP it is independently
deployable and independently versioned, at the cost of one network hop per
matter.

## Running it

```bash
docker compose -f local.yml --profile foreclosure up
```

Then run the **California Foreclosure Compliance** analyzer against a corpus.
It registers automatically — `auto_create_doc_analyzers` syncs any
`@corpus_analyzer_task` from the Celery registry into an `Analyzer` row on
startup.

### Settings

| Setting | Env var | Default |
|---|---|---|
| `FORECLOSURE_API_URL` | `FORECLOSURE_API_URL` | `http://foreclosure-api:8090` |
| `FORECLOSURE_API_TIMEOUT` | `FORECLOSURE_API_TIMEOUT` | `30` |

## What is read from documents, and what is not

**Read from the instruments:** instrument type, recording date, date mailed to
the trustor, first publication date, date posted, instrument number.

**Not read, because they appear on no recorded instrument:** the sale date, the
loan's purpose, the property's occupancy and unit count, reinstatement tenders,
postponements, payoff requests. These come from the analyzer's input (see the
input schema) or from `Corpus.custom_meta["foreclosure"]`.

Anything absent is **not** assumed. The ruleset reports `INSUFFICIENT RECORD`,
which is a distinct outcome from compliance. A compliance finding resting on an
assumed fact is worse than no finding.

## What it checks

| Provision | Requirement |
|---|---|
| § 2924(a)(2) | Three months between Notice of Default and Notice of Sale |
| § 2924b(b)(1) | NOD mailed within 10 **business** days of recording |
| § 2924b(b)(2) | Notice of Sale mailed ≥ 20 days before sale |
| § 2924f(b)(1) | Published and posted ≥ 20 days; recorded ≥ 14 days before sale |
| § 2924c(e) | Reinstatement until 5 **business** days before sale |
| § 2924g(d) | Postponement announced at the time and place of sale |
| § 2943(c) | Payoff demand statement within 21 days |
| § 2941(b), (d) | Reconveyance after payoff; $500 statutory damages |

Business days follow the Civ. Code § 7 holiday set, not calendar days. For a
sale on 2024-07-12 this moves the § 2924c(e) cutoff from 07-04 to 07-05 —
which decides whether a tender was timely.

## What it will not decide

Two rules exist to be refused:

- Whether service was **reasonably calculated** to reach the trustor (§ 2924b)
- Whether a default rate is an **unenforceable penalty** (§ 1671(b))

Both come back as `REQUIRES JUDGMENT`. There is no rate threshold above which
§ 1671 is satisfied, and inventing one would manufacture a legal conclusion the
engine has no basis for. The value of computing the deterministic rules
depends on being visibly unwilling to compute these.

## Outcomes

| Status | Meaning |
|---|---|
| `compliant` | Requirement met |
| `violation` | Requirement not met |
| `requires_judgment` | A human must decide |
| `insufficient_record` | Not enough in the record to evaluate — **not** a pass |
| `not_applicable` | The rule does not reach this matter |
| `record_inconsistent` | The record contradicts itself |
| `not_yet_in_force` | The provision post-dates the matter |

## Point-in-time law

Rules carry dated versions and are selected against the matter's **operative
date** — the recording of the Notice of Default. A 2011 foreclosure is not
evaluated against post-HBOR text; a provision enacted later reports
`NOT YET IN FORCE` rather than being applied retroactively.

`GET /v1/rules` on the service returns the full manifest: every provision,
its dated versions, and how many have been attorney-reviewed.

## Failure behaviour

If the service is unreachable the task **raises**. It does not return "no
violations found". A compliance analyzer that reports a clean bill of health
because it could not reach its ruleset is worse than one that crashes, and
there is a test asserting this.

The task is idempotent — it reads documents and returns a result dict, with no
side-effect writes — as required for `CELERY_TASK_ACKS_LATE`.

## Tests

```bash
pytest opencontractserver/tests/test_foreclosure_compliance.py
```

32 tests covering classification, date extraction, matter assembly and client
error handling. The ruleset itself has 94 tests in the Rust crate.
