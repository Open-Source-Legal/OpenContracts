# Deep research recovery

`ResearchReportService.finalize_once` recovers citations from persisted findings
under the report's row lock. Both explicit and salvage finalization use this
entry point, so resumed or overlapping workers retain earlier findings without
retrieving their sources again. `record_finding` validates retrieval provenance
before saving each finding.

Finalization rechecks these citations through
`AnnotationService.get_corpus_annotations` for the report's current corpus/group
scope. Corpus, document, and analysis/extract visibility still apply, including
for shared structural annotations. New citations must come from retrieval in the
current segment; a readable annotation ID alone is insufficient.
