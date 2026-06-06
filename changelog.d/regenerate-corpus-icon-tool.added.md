- **Manually (re)generate a corpus icon via an agent.** A new
  `regenerate_corpus_icon` agent tool
  (`opencontractserver/llms/tools/core_tools/corpus_branding.py`) re-runs the
  corpus logo generator on demand, so a user can ask the corpus chat agent to
  give a collection a fresh icon at any time — not just at creation. It reuses
  the auto-branding primitives (`_build_logo_prompt` + `agenerate_logo_image`
  with the deterministic PIL monogram fallback) through a new public helper
  `aregenerate_corpus_logo` in `opencontractserver/corpuses/services/branding.py`
  and persists through the creator-gated `CorpusService.update_icon`. An optional
  `additional_instructions` argument lets the agent steer the look (e.g. "use
  blue tones and a gavel motif"); the hint is sanitised and length-capped
  (`CORPUS_LOGO_ADDITIONAL_INSTRUCTIONS_MAX_CHARS`) before being folded into the
  image prompt. The tool is registered in `tool_registry.py` (alias
  `generate_corpus_icon`), `requires_approval` + `requires_corpus` +
  `requires_write_permission`, creator-only, and is wired into the interactive
  corpus agent's authenticated toolset
  (`opencontractserver/llms/agents/pydantic_ai_agents.py`) alongside
  `update_corpus_description`. Unlike the create-time path it deliberately
  overwrites an existing icon and ignores `auto_branding_enabled` (a manual
  regeneration is an explicit request). Tests:
  `opencontractserver/tests/test_corpus_icon_tool.py`.
