# 0002 (companion) — The Bolivia authority pack: concrete spec + provider skeleton

Companion to [`0002-authority-packs.md`](./0002-authority-packs.md). This is the
**Phase 1** (citation-driven) artifact: a buildable specification for repackaging
PR #1305's Bolivian-law work as an authority pack. Like the parent proposal and
#1444, it ships **no live code** — the provider below is an illustrative skeleton
(it is *not* placed in the auto-discovered package and would not register), and
the URL templates / parse selectors are placeholders to be filled from the live
publisher endpoints.

All shapes below are taken verbatim from the current source:
`authority_mappings.yaml`, `BaseAuthoritySourceProvider`
(`opencontractserver/pipeline/base/base_authority_source_provider.py`),
`AuthoritySection` (`opencontractserver/enrichment/authorities.py`), the
`bootstrap_authority` command, and `ALL_AUTHORITY_TYPES`
(`opencontractserver/enrichment/constants.py`).

## Pack layout

A pack is a directory of mostly-data plus one provider module. The provider must
ultimately live in the core auto-discovered package (gap 6 in the parent); the
rest is loaded by existing commands.

```
authority-packs/bolivia/
├── README.md                         # what this pack ingests + the host-allowlist edit it needs
├── authority_mappings.bolivia.yaml   # → AuthorityMappingLoader.load_all(path=…)
├── providers/
│   └── bolivia_gaceta_provider.py    # → copied into pipeline/authority_source_providers/
├── specs/                            # → bootstrap_authority --file <each>
│   ├── constitucional.json
│   ├── penal.json
│   ├── civil.json
│   └── … (administrativo, laboral, tributario, familia, comercial, agrario, ambiental, otros)
└── personas/
    └── constitucional.es.txt         # → Corpus.corpus_agent_instructions
```

PR #1305's eleven `LegalArea` values become the eleven `specs/*.json` corpora; its
authorities (CPE, codes, decrees, rulings) become the `prefixes:` in the YAML.

## Slot 1 — Taxonomy (`authority_mappings.bolivia.yaml`)

The schema is identical to the shipped `authority_mappings.yaml`. `jurisdiction`
is free text (`bo`); every `authority_type` is drawn from the nine
`ALL_AUTHORITY_TYPES`; aliases are free-form lowercased surface strings (Spanish
fully supported and used for Tier-1 citation extraction).

```yaml
# Bolivia authority pack — namespace registry + classification.
# Load: manage.py shell -c \
#   "from opencontractserver.enrichment.services.authority_mapping_loader import AuthorityMappingLoader; \
#    AuthorityMappingLoader.load_all(path='authority-packs/bolivia/authority_mappings.bolivia.yaml')"
prefixes:
  cpe:
    display_name: "Constitución Política del Estado (2009)"
    jurisdiction: "bo"
    authority_type: "constitution"
    aliases: ["constitución política del estado", "cpe", "constitución"]
  bo-ley:
    display_name: "Leyes del Estado Plurinacional de Bolivia"
    jurisdiction: "bo"
    authority_type: "statute"
    aliases: ["ley", "leyes"]
  bo-ds:
    display_name: "Decretos Supremos"
    jurisdiction: "bo"
    authority_type: "regulation"
    aliases: ["decreto supremo", "ds", "decretos supremos"]
  bo-scp:
    display_name: "Sentencias Constitucionales Plurinacionales (TCP)"
    jurisdiction: "bo"
    authority_type: "case"
    aliases: ["sentencia constitucional plurinacional", "scp", "sentencia constitucional", "sc"]
  bo-as:
    display_name: "Autos Supremos (Tribunal Supremo de Justicia)"
    jurisdiction: "bo"
    authority_type: "case"
    aliases: ["auto supremo", "autos supremos", "as"]

# Optional — only needed if popular-name citations must reach a differently-keyed
# provider. Example: a code's popular name → its enacting Ley number.
equivalences:
  - { from_key: "codigo-penal:bo", to_key: "bo-ley:1768", note: "Código Penal (Ley 1768)" }
  - { from_key: "codigo-procesal-penal:bo", to_key: "bo-ley:1970", note: "Código de Procedimiento Penal (Ley 1970)" }

# rewrite_rules: omit unless there is a genuinely mechanical 1:1 prefix transform.
```

**Canonical-key grammar** the provider serves: `cpe:13` (CPE art. 13),
`bo-ley:1970` (Ley N° 1970), `bo-ds:29894` (Decreto Supremo 29894),
`bo-scp:0123-2018`, `bo-as:…`.

## Slot 2 — Source provider skeleton (`providers/bolivia_gaceta_provider.py`)

Modeled on `USCodeAuthoritySourceProvider`. One provider serves the three
Gaceta-published prefixes (`cpe`, `bo-ley`, `bo-ds`); sibling providers
(`BoliviaTSJProvider` for `bo-as`, `BoliviaTCPProvider` for `bo-scp`) follow the
same template against their courts' sites. `_locate_impl` is pure (URL/citation
derivation, unit-testable with no network); `_fetch_impl` does the one HTTP call
via the SSRF-safe helper and parses into `AuthoritySection[]`.

> **Skeleton.** The `_URL_TEMPLATE` and the parse logic in `_fetch_impl` are
> placeholders — fill them from the live Gaceta Oficial endpoints (PR #1305's
> `GacetaOficialScraper` is the reference for the real selectors). Keep the
> `_load_*` seam so tests patch it with `httpx.MockTransport` fixtures, exactly as
> #1305 did.

```python
"""Bolivia Gaceta Oficial authority source provider (SKELETON — illustrative).

Resolves Bolivian primary law published in the Gaceta Oficial de Bolivia:
    cpe:{article}      Constitución Política del Estado          -> cpe:13
    bo-ley:{number}    Ley del Estado Plurinacional               -> bo-ley:1970
    bo-ds:{number}     Decreto Supremo                            -> bo-ds:29894

License: public-domain (Bolivian official legal texts). All HTTP goes through
opencontractserver.utils.safe_http (the source host must be on
PUBLIC_DOMAIN_SOURCE_HOSTS — see the README's allowlist edit).
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)
from opencontractserver.utils.safe_http import safe_fetch_text

logger = logging.getLogger(__name__)

# Gaceta Oficial host — must also be added to PUBLIC_DOMAIN_SOURCE_HOSTS.
_GACETA_HOST = "gacetaoficialdebolivia.gob.bo"
# TODO(pack): replace with the real document endpoint(s) per instrument family.
_URL_TEMPLATE = "https://gacetaoficialdebolivia.gob.bo/normas/{kind}/{number}"

# Citation labels per prefix (human-readable, Spanish).
_CITATION = {
    "cpe": "Constitución Política del Estado, art. {n}",
    "bo-ley": "Ley N° {n} (Bolivia)",
    "bo-ds": "Decreto Supremo N° {n}",
}
# URL path segment per prefix.
_KIND = {"cpe": "constitucion", "bo-ley": "ley", "bo-ds": "decreto-supremo"}

# Identifier component validation (no URL/selector injection).
_NUMBER_RE = re.compile(r"^[0-9][0-9a-z\-]*$", re.IGNORECASE)


def _validate_number(prefix: str, number: str) -> None:
    if not _NUMBER_RE.match(number):
        raise ValueError(f"Invalid {prefix} identifier component: {number!r}")


class BoliviaGacetaProvider(BaseAuthoritySourceProvider):
    """Fetches Bolivian primary law from the Gaceta Oficial (public domain)."""

    title = "Gaceta Oficial de Bolivia"
    description = "Constitución, Leyes y Decretos Supremos del Estado Plurinacional."
    license: ClassVar[str] = "public-domain"
    priority: ClassVar[int] = 100          # below the agentic fallback (9999)
    enabled: ClassVar[bool] = True
    requires_approval: ClassVar[bool] = False
    supported_prefixes: ClassVar[tuple[str, ...]] = ("cpe", "bo-ley", "bo-ds")

    # ---- pure: derive the fetch plan (no I/O) -----------------------------
    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        prefix, ident = canonical_key.split(":", 1)
        _validate_number(prefix, ident)
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=_URL_TEMPLATE.format(kind=_KIND[prefix], number=ident),
            citation=_CITATION[prefix].format(n=ident),
            extra={"prefix": prefix, "ident": ident},
        )

    # ---- HTTP + parse (the only network site) -----------------------------
    def _fetch_impl(self, request: AuthorityRequest, **all_kwargs) -> list[AuthoritySection]:
        html = self._load_document(request)
        heading, text = self._parse(html, request)   # TODO(pack): real selectors
        if not text.strip():
            logger.warning("BoliviaGacetaProvider: empty body for %s", request.canonical_key)
            return []
        return [
            AuthoritySection(
                key=request.canonical_key,
                heading=heading,
                text=text,
                source_url=request.url,
            )
        ]

    # ---- test seam: patch this in tests with httpx.MockTransport fixtures --
    def _load_document(self, request: AuthorityRequest) -> str:
        text, _ = safe_fetch_text(request.url)
        return text

    def _parse(self, html: str, request: AuthorityRequest) -> tuple[str, str]:
        # TODO(pack): port PR #1305 GacetaOficialScraper's defensive parsing here.
        raise NotImplementedError("Fill from the live Gaceta Oficial document shape.")
```

## Slot 3 — Corpus + content seed (`specs/constitucional.json`)

One JSON spec per legal area, in the exact shape the `bootstrap_authority`
command validates (`{aliases?, sections: [{key, heading, text, source_url?}]}`).
Idempotent: re-running skips unchanged sections and version-ups changed text.

```json
{
  "aliases": ["Constitución Política del Estado", "CPE"],
  "sections": [
    {
      "key": "cpe:13",
      "heading": "CPE art. 13 — Derechos fundamentales",
      "text": "I. Los derechos reconocidos por esta Constitución son inviolables, universales, interdependientes, indivisibles y progresivos. El Estado tiene el deber de promoverlos, protegerlos y respetarlos. …",
      "source_url": "https://gacetaoficialdebolivia.gob.bo/normas/constitucion/13"
    },
    {
      "key": "cpe:14",
      "heading": "CPE art. 14 — Igualdad y no discriminación",
      "text": "I. Todo ser humano tiene personalidad y capacidad jurídica con arreglo a las leyes y goza de los derechos reconocidos por esta Constitución, sin distinción alguna. …",
      "source_url": "https://gacetaoficialdebolivia.gob.bo/normas/constitucion/14"
    }
  ]
}
```

The other ten area corpora (`penal.json`, `civil.json`, …) follow the same shape,
each seeded with the codes/laws that area cites.

## Slot 4 — Agent persona (`personas/constitucional.es.txt`)

Free-text, Spanish. Written into `Corpus.corpus_agent_instructions` (the field
#1305 already populated) at bootstrap time, and injected by
`CoreCorpusAgentFactory`. For richer control (preferred LLM, tools, badge), seed
an `AgentConfiguration(scope=CORPUS)` row following the `template_seeds.py`
dict pattern.

```
Eres un asistente jurídico especializado en derecho constitucional boliviano.
Respondes con base en la Constitución Política del Estado (2009) y la
jurisprudencia del Tribunal Constitucional Plurinacional. Cita siempre el
artículo o la sentencia exacta y distingue entre norma vigente y derogada.
```

## Slot 5 (required, not pack data) — host-allowlist edit

The one binding a pack cannot self-declare. Add the pack's government hosts to
`PUBLIC_DOMAIN_SOURCE_HOSTS` in `opencontractserver/constants/safe_http.py` in the
same PR (confirm the entry granularity against `safe_http`'s host-matching — list
the specific hosts the providers fetch):

```diff
 PUBLIC_DOMAIN_SOURCE_HOSTS: frozenset[str] = frozenset(
     {
         "ecfr.gov",
         "federalregister.gov",
         "govinfo.gov",
         "gpo.gov",
         "uscode.house.gov",
+        # Bolivia authority pack — official public-domain legal sources
+        "gacetaoficialdebolivia.gob.bo",  # Gaceta Oficial (CPE, leyes, decretos)
+        "tsj.bo",                          # Tribunal Supremo de Justicia (autos supremos)
+        "tcpbolivia.bo",                   # Tribunal Constitucional Plurinacional (SCP)
     }
 )
```

## Drop-in commands (Phase 1)

```bash
# 1) Provider: copy the skeleton into the auto-discovered package, then restart.
cp authority-packs/bolivia/providers/bolivia_gaceta_provider.py \
   opencontractserver/pipeline/authority_source_providers/

# 2) Apply the host-allowlist edit (Slot 5) and restart the django/celery procs.

# 3) Load the taxonomy (idempotent).
docker compose -f local.yml run --rm django python manage.py shell -c \
  "from opencontractserver.enrichment.services.authority_mapping_loader import AuthorityMappingLoader; \
   print(AuthorityMappingLoader.load_all(path='authority-packs/bolivia/authority_mappings.bolivia.yaml'))"

# 4) Verify the provider registered (Authority Console → Scrapers tab, or):
docker compose -f local.yml run --rm django python manage.py shell -c \
  "from opencontractserver.pipeline.registry import get_all_authority_source_providers_cached as g; \
   print([d.name for d in g()])"

# 5) Seed each area corpus + persona.
docker compose -f local.yml run --rm django python manage.py bootstrap_authority \
  --creator <username> --title 'Bolivia — Derecho Constitucional' \
  --file authority-packs/bolivia/specs/constitucional.json --public
#   … repeat for penal.json, civil.json, … (10 more)

# 6) Trigger discovery for authorities cited in those corpora (frontier-driven),
#    or directly via the Authority Console / RunAuthorityDiscoveryMutation.
```

## What Phase 1 deliberately does NOT include

- **Bulk publisher discovery** (crawl the Gaceta index for *unknown* new
  documents) — the provider is citation-keyed. → parent proposal Phase 2.
- **Scheduled/nightly ingestion** — no scheduling primitive exists. → Phase 3
  (= #1444 Phase A).
- **Unified cross-area `askBolivianLaw` orchestrator** — `CorpusGroup` /
  `asearch_across_corpora` do not exist; each area corpus is queried
  independently via its own agent. → Phase 4 (= #1444 Phase B).

## Provenance

PR #1305 (@jseborga) is the reference implementation for the three scrapers'
parse logic, the dedup approach, the eleven specialist personas, and the
`httpx.MockTransport` test pattern — all of which port into this pack. Credit
carries forward per #1444's migration story.
