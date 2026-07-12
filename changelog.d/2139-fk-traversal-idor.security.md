- Closed a systematic cross-boundary information-disclosure regression in the
  graphene→strawberry migration: **singular to-one FK object fields lost their
  per-row visibility filter.** graphene-django auto-converted a FK whose target
  type overrode `get_queryset` into a permission-filtered resolver
  (`convert_field_to_djangomodel` → `target.get_node`), so an invisible FK
  target resolved to `null`. The strawberry port declared these as plain
  getattr fields, leaking the target row's fields across a permission boundary.
  Added `config/graphql/core/relay.py::resolve_visible_fk` (applies the target
  type's registered `get_node`/`get_queryset` hook) and routed the affected
  **nullable** FK fields through it, restoring the graphene contract. Fields
  fixed include the confirmed-exploitable cross-boundary edges —
  `AnnotationType.corpus`, `RelationshipType.corpus`/`document`,
  `CorpusReferenceType.targetDocument`/`targetCorpus`/`targetAnnotation`,
  `ConversationType.chatWithCorpus`/`chatWithDocument`,
  `MessageType.sourceDocument`, `DocumentType.parent`/`sourceDocument`,
  `CorpusType.parent`/`memoryDocument` — plus the lower-severity theoretical
  edges on `agent_types`/`extract_types`/`social_types`/`user_types`/
  `research_types`/`document_types` for consistency.
- `config/graphql/document_types.py::_get_queryset_DocumentPathType`: the
  **non-null** `DocumentPathType.document` FK cannot resolve to `null`, so its
  leak (DocumentPath membership is corpus-as-gate — a public/shared corpus
  lists paths for its *private* documents too) is closed at the list level by
  adding a `document_id__in=<visible documents>` MIN(document, corpus) filter,
  the same semantic `CorpusType.documents` uses (issue #1682).
- FK edges whose source-row visibility already implies READ on the target
  (e.g. `NoteType.corpus`/`document`, `DocumentRelationshipType.*`, corpus-gated
  `*.corpus`, same-parent `parent`) are left as fast plain fields — filtering
  them is a no-op that only adds per-row queries.
- Regression coverage: `opencontractserver/tests/test_fk_visibility_traversal.py`
  pins both branches of `resolve_visible_fk`, the DocumentPath MIN filter, and an
  end-to-end schema query (`CorpusType.parent` → `null` for a non-owner).
