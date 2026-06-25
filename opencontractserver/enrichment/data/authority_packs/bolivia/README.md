# Bolivia authority pack

A reference **authority pack** — the Phase-1 (seed-based) implementation of
[`docs/architecture/proposals/0002-authority-packs.md`](../../../../../docs/architecture/proposals/0002-authority-packs.md).
It stands up a Bolivian body-of-law deployment as **data** (taxonomy + curated
content + persona) bound to the existing Authority architecture — no bespoke
Django app.

> **Authoring your own pack?** This directory is the canonical worked example;
> the step-by-step how-to (pack layout, shipping a scraper inside the pack,
> `source_hosts`, add/remove/copy) lives in
> [Authoring an Authority Pack](../../../../../docs/guides/authoring-authority-packs.md).

## What it ships

| File | Binds to |
|---|---|
| `authority_mappings.bolivia.yaml` | `AuthorityNamespace` / `AuthorityKeyEquivalence` via `AuthorityMappingLoader.load_all(path=…)` — five Bolivian prefixes (`cpe`, `bo-ley`, `bo-ds`, `bo-scp`, `bo-as`), `jurisdiction: bo`, Spanish aliases. |
| `specs/constitucional.json` | `bootstrap_authority_corpus()` — keyed text documents (`cpe:1/8/13/14`). |
| `personas/constitucional.es.txt` | `Corpus.corpus_agent_instructions` (injected by `CoreCorpusAgentFactory`). |
| `pack.yaml` | the `load_authority_pack` management command (the manifest). |

## Load it

```bash
docker compose -f local.yml run --rm django python manage.py load_authority_pack \
  --path opencontractserver/enrichment/data/authority_packs/bolivia \
  --creator <username> --public
```

Idempotent and re-runnable: the taxonomy upsert never clobbers `source="manual"`
rows, and the corpus bootstrap skips unchanged sections / version-ups changed
text. `--path` accepts any directory, so out-of-tree packs load the same way.

## Scope (Phase 1)

This pack recognises Bolivian citations (taxonomy) and seeds curated
public-domain content per area. It does **not** fetch from the live Bolivian
publishers: the Gaceta Oficial / TSJ / TCP are **listing-page** sites, not
key-addressable, so a deterministic `canonical_key → URL` provider is deferred
to **Phase 2 — authority discovery providers (issue #2054)**. Until then,
authority content is curated into `specs/*.json` (this file) or ingested by
operators from official sources.

> **Content note.** The seeded CPE articles are faithful reference excerpts of
> the 2009 Constitución Política del Estado for demonstration; operators should
> verify against, and expand from, the official Gaceta Oficial de Bolivia text.

## Add the remaining areas

PR #1305 (@jseborga) defined eleven legal areas — `constitucional` (shipped),
`penal`, `civil`, `administrativo`, `laboral`, `tributario`, `familia`,
`comercial`, `agrario`, `ambiental`, `otros` — each with a Spanish specialist
persona. To add one:

1. Drop a `specs/<area>.json` section spec (curated public-domain text).
2. Drop a `personas/<area>.es.txt` (the persona texts are ported verbatim from
   PR #1305's `AREA_PROFILES`).
3. Add a `corpora[]` entry to `pack.yaml` pointing at both.
4. Re-run `load_authority_pack`.

A unified cross-area query over all eleven corpora (PR #1305's `askBolivianLaw`
orchestrator) needs multi-corpus retrieval — **Phase 4, issue #2056**
(`CorpusGroup` + `asearch_across_corpora`). Today each area corpus is queried
independently via its own agent.

## Provenance

Personas, the eleven-area taxonomy, and the source-publisher knowledge are
ported from PR #1305 by @jseborga (credited per the #1444 migration story).
