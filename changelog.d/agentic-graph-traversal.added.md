- **Agentic reference-graph traversal ("contracts-as-codebase").** Added four
  read-only agent tools that let document and corpus agents *walk* the
  already-materialised reference graph one hop at a time, instead of relying on
  semantic retrieval alone:
  `get_document_references` (what a document cites / what cites it),
  `read_reference_target` (open a cited statute/contract and read its text),
  `find_documents_citing` (who relies on an authority/document), and
  `get_reference_neighborhood` (the local governance graph). Implemented in
  `opencontractserver/llms/tools/core_tools/graph_navigation.py`; registered in
  `opencontractserver/llms/tools/tool_registry.py` (new `ToolCategory.GRAPH`)
  and wired into both agent factories in
  `opencontractserver/llms/agents/pydantic_ai_agents.py`. The tools route
  exclusively through the enrichment service layer (`CorpusReferenceService`,
  `GovernanceGraphService`, `enrichment.authorities.find_authority_target`), so
  they inherit `MIN(document, corpus)` visibility. Document/corpus agent
  instructions (`config/settings/base.py`) gained a find→traverse→read loop
  nudge. Caps live in `opencontractserver/enrichment/constants.py` (`NAV_*`).
- **Traversal A/B benchmark harness.** Added
  `opencontractserver/benchmarks/traversal_benchmark.py` and the
  `manage.py benchmark_traversal` command to compare "heavy RAG"
  (`similarity_search` only) vs "RAG + traversal" on real corpus questions,
  reporting tokens, tool-call counts, latency and authority-grounding — the
  instrument for later deciding, with data, whether eager indexing still earns
  its keep. Fixtures in
  `opencontractserver/benchmarks/fixtures/traversal_questions.yaml`; run steps
  in `docs/test_scripts/traversal_benchmark.md`.
