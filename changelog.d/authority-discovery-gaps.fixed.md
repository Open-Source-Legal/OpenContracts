- **Closed five open-vocabulary authority-discovery gaps surfaced by an S-1 smoke
  test (refines the Phase 2–5 chain #1998–#2001).**
  - *Popular-name fragmentation* — `opencontractserver/enrichment/grammars.py`
    `_bare_acts` now canonicalises a recognised Act through the registry's
    `AUTHORITY_PREFIX` alias table (stripping any year and a leading
    "U.S."/"United States" qualifier), so every spelling of "the Securities
    Exchange Act of 1934" collapses to one `exchange-act` key instead of
    fragmenting into distinct `act:<slug>` rows. Unknown Acts keep the
    open-vocabulary `act:<slug>` fallback.
  - *Whole-act dead-ends* — `enrichment/authorities.py::find_authority_target`
    gained a whole-act fallback: a section-less authority key (e.g.
    `exchange-act`) resolves to a representative document of that body of law,
    so a bare "the Exchange Act" citation links into the existing authority
    corpus instead of stranding as a wanted/unsupported frontier entry. The
    reactive relink (`EnrichmentService.relink_corpora_for_keys`) pre-filter was
    widened to match exact (colon-less) keys, not only `prefix:` startswith
    forms, so whole-act keys are not silently skipped on cross-corpus converge.
  - *Lost classification* — `enrichment/constants.py::classify_prefix` now
    classifies the grammar's federal-statute meta-prefixes (`act`, `publ`,
    `stat`) as `(us-federal, statute)`, so `AuthorityFrontier` rows and
    governance-graph ghost nodes are no longer left `(None, None)`.
  - *Persisted taxonomy* — `EnrichmentWriter` (`enrichment/writer.py`) now
    classifies every `CorpusReference` at persist time via a shared
    `classify_canonical_key` ladder (candidate → `AuthorityNamespace` →
    `classify_prefix`, batched to avoid N+1) and heals pre-existing `(None,
    None)` rows on re-apply; `discover()` reuses the same ladder so the stored
    web and the inventory never disagree.
  - *apply/discover asymmetry* — `EnrichmentService.apply` now defaults to
    registry **plus** the open-vocabulary grammar tier (matching `discover`), so
    the standard enrichment path persists the open-vocab authorities into the
    frontier and governance graph (pass `extra_tiers=[]` for a registry-only
    pass; the LLM tier stays opt-in).
