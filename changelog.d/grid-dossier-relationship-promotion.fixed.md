- Fixed sideloaded authority corpora silently dropping every provider-authored
  relationship when the target corpus owned no canonical-key prefix.
  `_reconcile_imported_authority_metadata`
  (`opencontractserver/tasks/import_tasks_v2.py`) reconciles typed metadata and
  promotes `custom_meta["relationships"]` into `AuthorityRelationship` only for
  documents whose prefix is bound to the corpus being imported, and returns
  immediately when the corpus has no bound prefix at all. Only
  `ercot_large_load`'s revision-history corpus declared `authority_prefixes`,
  so eight of the ten GridDossier corpora imported cleanly and promoted
  nothing — 154 of 396 declared edges (every PUCT Project 59142 `FILED_IN`, 5
  Oncor `IMPLEMENTS`, 1 ERCOT-notice `CITES`) stayed stranded in document
  metadata, with no error and no failing import. All four pack manifests now
  bind every prefix they declare.
- Fixed `@`-mentioning an agent in the live chat frequently not routing to it.
  The mention attaches a `delegate_to_<slug>` tool to the corpus conductor, but
  the tool's description was the target agent's own description, which carries
  no routing intent; the conductor weighed it against its own retrieval tools
  and usually answered locally, producing a single-corpus answer that reads
  exactly like a delegated one. `build_delegation_tool`
  (`opencontractserver/llms/tools/delegation_tools.py`) now leads the
  description with the mention and the instruction to call the tool, and
  appends the agent's description as context. **Behaviour change:**
  `test_delegation_tools.py::test_tool_description_is_agent_description` is
  replaced by
  `test_tool_description_states_the_mention_and_carries_agent_description`.
- Fixed `@`-mentions typed in the live chat never being persisted.
  `link_message_to_resources` was called from the GraphQL and MCP message paths
  but not from the WebSocket path, so `ChatMessage.mentioned_agents` (and the
  mentioned user/corpus/document relations) stayed empty for every live-chat
  message — including turns where delegation demonstrably fired.
  `CoreConversationManager.store_user_message`
  (`opencontractserver/llms/agents/core_agents.py`) now links them best-effort.
- Fixed the Corpus Groups page hiding every group the viewer did not create.
  `CorpusGroupManagement.tsx` hard-coded `mine: true`, so a public or shared
  group — whose whole purpose is to be named in a cross-corpus query — was
  invisible to the collaborators it exists for. The page now lists every
  visible group, adds an Owner column, and shows edit/delete only to the owner
  (the mutations were already permission-gated server-side).
