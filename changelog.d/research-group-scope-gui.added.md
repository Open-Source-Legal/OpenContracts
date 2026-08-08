- Group-scoped deep research is now reachable from the interface.
  `startResearchReport` takes an optional `corpusGroupId`
  (`config/graphql/research_mutations.py`), and the corpus Research tab's
  **Start research** modal offers a group picker
  (`frontend/src/components/widgets/modals/StartResearchModal.tsx`, backed by
  `GET_CORPUS_GROUP_OPTIONS`). The capability already existed in
  `ResearchReportService.start` and in the chat agent's `start_deep_research`
  tool, so the only way to widen a run past the anchor corpus was to ask the
  agent in chat — the explicit kickoff path could not do it at all. A group the
  caller cannot see is REFUSED rather than ignored: a silently narrowed run
  produces a report that reads as group-wide and is not. Golden SDL
  regenerated; gate covered by
  `opencontractserver/tests/research/test_research_start_mutation.py`.
