- **The document References panel badges in-flight references "In progress".**
  `frontend/src/components/knowledge_base/document/DocumentReferencesPanel.tsx`
  now selects the `isProvisional` field (exposed on `CorpusReferenceType`) and
  renders an indigo "In progress" chip on any reference written by an enrichment
  run that is still in flight — taking precedence over its preliminary
  Linked / Awaiting-source state until the run finalizes. The "Cites" header
  summary counts it as in-progress (not linked/awaiting) to match.
