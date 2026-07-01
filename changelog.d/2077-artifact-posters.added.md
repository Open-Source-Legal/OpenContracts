- **Corpus home: editorial redesign, data story, and shareable Artifact posters.**
  The default corpus home (the CAML article) is rebuilt as an editorial
  *Collection Overview*, joined by a derived data story and a shareable-poster
  system:
  - **Collection Overview** — `IntelligencePanel` rebuilt into a restrained
    metric band (documents, pages, law references) plus a numbered documents
    index with per-doc one-line descriptions and page-weight bars
    (`frontend/src/components/corpuses/CorpusHome/intelligence/IntelligencePanel.tsx`).
  - **Data story** — new `CollectionDataStory` component + `CorpusDataStoryService`
    (`opencontractserver/corpuses/services/data_story.py`, GraphQL
    `corpusDataStory`): document-type composition, effective-date timeline, and
    value ranking derived from the default *Collection Profile* extract; each
    facet self-hides when its data is absent. Intelligence setup now installs the
    Collection Profile fieldset + an `add_document` action that keeps the
    per-document profile growing as documents arrive
    (`CorpusIntelligenceSetupService._setup_structured_profile`).
  - **Artifact posters** — new `Artifact` model (migration `corpuses/0058`) +
    `ArtifactService` + GraphQL (`artifactBySlug` / `corpusArtifacts` /
    `corpusArtifactTemplates` with data-gated eligibility; `createArtifact` /
    `updateArtifact` / `setArtifactImage`). Templates are a renderer registry —
    adding one needs no migration. A `/a/<slug>` route renders a template
    full-bleed with download-PNG and copy-link; the first template is a d3
    `SpendingBeeswarm` (time × value). Visibility is corpus-as-gate; **creation
    is authenticated-only** (`ArtifactService.create` rejects anonymous callers,
    the mutations are `@login_required`, and `Artifact.creator` is non-null).
  - **Tooling** — `ingest_corpus` management command: folder → corpus → import
    (parse + embed) → optional `--wait` / `--enrich` / `--public`.
  - Tests: `opencontractserver/tests/test_artifact_service.py`,
    `opencontractserver/tests/test_intelligence_setup.py`,
    `frontend/tests/IntelligencePanel.ct.tsx`,
    `frontend/tests/CamlIntelligenceEmbeds.ct.tsx`.
