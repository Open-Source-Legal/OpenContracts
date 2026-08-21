- **`Corpus.default_agent`, plus the two changes that make it mean anything.**
  A corpus could not have a default agent. A chat opened with no `agent_id`
  always resolved to the GLOBAL `default-corpus-agent` slug, so an
  `AgentConfiguration` scoped to a corpus could never be its default however it
  was configured — and even when one *was* resolved, its `system_instructions`
  and `available_tools` were discarded, because those apply only on the
  explicit-`?agent_id=` path. Three things follow:
  - `Corpus.default_agent` (FK, mirroring `CorpusGroup.default_agent`). An
    explicit pointer, not "pick a CORPUS-scoped agent": corpora already carry
    scoped agents for other purposes (the inline moderator), and choosing
    positionally would silently hand chat to whichever sorted first.
    `Corpus.save` refuses a pointer at an agent scoped to a *different*
    corpus — that would serve one corpus's private instructions to another's
    users.
  - Resolution priority 3 consults it before the global slug. An inactive
    target falls back rather than failing, which is what switching an agent
    off is asking for.
  - Fallback-resolved configs are applied when `system_instructions_mode` is
    `EXTEND`. The exclusion was written when REPLACE was the only mode, and
    its stated reason — a generic default would clobber the corpus persona —
    is specific to REPLACE. EXTEND appends, so there is nothing to clobber;
    excluding it only produced a default that resolved and was then silently
    ignored. REPLACE keeps the original behaviour on the fallback path.
- **`install_domain_pack --consumer-corpus <pk>` (contract assertion C8).**
  A domain pack may now declare a `consumer_agent` — instructions, tools, and
  `mode: EXTEND` — for the corpus that *consumes* the domain. The pack supplies
  the text, because the group slug it names is the pack's own invention; the
  operator supplies the corpus, because which corpus consumes a domain is not
  knowable when the pack is written. `EXTEND` is required rather than
  preferred: REPLACE would overwrite the consuming corpus's persona with
  third-party text, which is the coupling `DOMAIN_PACKS.md` forbids. Declaring
  one without binding it reports that it was not applied (C5) instead of
  passing silently, and the same group-slug check the orchestrator is held to
  applies here — `search_across_corpora` takes the slug as a required
  argument, so an agent never told it cannot call it.
