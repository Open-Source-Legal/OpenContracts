# Corpus Export and Import

OpenContracts can export an entire corpus -- documents, annotations, labels,
folder structure, and configuration -- as a ZIP archive. This archive can be
imported into the same or a different OpenContracts instance to recreate the
corpus in full.

Two export format versions exist. V2 is the current default and is a strict
superset of V1.

| Version | Marker | Contents |
|---------|--------|----------|
| V1 | `version` absent or `"1.0"` | Documents, annotations, labels, corpus metadata |
| V2 | `"version": "2.0"` | Everything in V1 plus structural annotations, folders, versioning, relationships, agent config, conversations |

## Exporting a Corpus

1. Right-click a corpus in the corpus list
2. Select **Export** from the context menu
3. Choose an export format:
   - **OpenContracts** (default) -- full archive for backup/transfer
   - **FUNSD** -- form understanding research format
4. Optionally select post-processors
5. Click **Start Export**

The export runs asynchronously. Download the result from the user dropdown menu
once complete.

**Note**: Corpus export/import must be enabled on your instance via the
`REACT_APP_ALLOW_IMPORTS` frontend environment variable.

## ZIP Archive Layout

The export produces a ZIP with this structure:

```
corpus_export.zip
+-- data.json           # Metadata, annotations, labels, configuration
+-- document_a.pdf      # Original document files
+-- document_b.pdf
+-- report.txt
+-- ...
```

All files sit at the ZIP root (no subdirectories). Every key in
`annotated_docs` within `data.json` must have a corresponding file in the ZIP.

## data.json Structure

### V1 Fields (always present)

| Field | Description |
|-------|-------------|
| `annotated_docs` | Map of filename to document export data (text, annotations, PAWLs tokens) |
| `doc_labels` | Map of label name to document-level label definitions |
| `text_labels` | Map of label name to text annotation label definitions |
| `corpus` | Corpus metadata (title, description, icon, creator) |
| `label_set` | Label set metadata |

### V2 Additional Fields

| Field | Description |
|-------|-------------|
| `structural_annotation_sets` | Shared parser output keyed by content hash (deduplicated across documents) |
| `folders` | Corpus folder hierarchy |
| `document_paths` | Document version trees (DocumentPath history) |
| `relationships` | Cross-document annotation relationships |
| `agent_config` | Corpus-level and document-level agent instructions |
| `md_description` | Markdown corpus description |
| `md_description_revisions` | Description revision history |
| `post_processors` | Post-processor configuration |
| `conversations` | Chat threads (optional, controlled by export flag) |
| `messages` | Chat messages (optional) |
| `message_votes` | Message votes (optional) |

## Importing a Corpus

**GraphQL Mutation**: `UploadCorpusImportZip`

The import accepts a base64-encoded ZIP and creates a new corpus with all
contained data. Format version is auto-detected from `data.json`.

### Import Behavior

- **ID remapping**: All IDs in the export are treated as opaque references. New
  database IDs are assigned on import and cross-references (relationships,
  parent annotations, etc.) are remapped automatically.
- **User mapping**: `creator_email` fields are matched to existing users. If no
  match is found, the importing user is used.
- **Structural set deduplication**: If a structural annotation set with the same
  content hash already exists in the database, it is reused rather than
  duplicated.
- **Corpus isolation**: Documents are copied into the new corpus; edits do not
  affect any other corpus.
- **Embeddings regenerated**: Vector embeddings are not exported -- they are
  regenerated on import because different deployments may use different
  embedding models.

### CAML README References (`oc-import://`)

The corpus README (`md_description`) supports placeholder URLs that the
importer rewrites to live document and annotation URLs after the rest of the
zip has been imported.  This lets a zip author hand-write a README that
references resources bundled in the same zip without knowing the destination
deployment's primary keys or slugs.

| Placeholder | Resolves to |
|-------------|-------------|
| `oc-import://document/<filename-in-zip>` | `/d/<user-slug>/<corpus-slug>/<doc-slug>` |
| `oc-import://annotation/<id-in-data.json>` | `/d/<user-slug>/<corpus-slug>/<doc-slug>?ann=<new-pk>` |

`<filename-in-zip>` must match a key under `annotated_docs` in `data.json`
(typically the path of the document file inside the zip, e.g.
`documents/lease.pdf`).  Leading `./` is tolerated.

`<id-in-data.json>` must match the `"id"` field of an annotation under
`annotated_docs.<filename>.labelled_text[*]`.  The annotation's parent
document is resolved automatically so the rewritten URL is fully qualified
and recognised by the [@ mention parser](../architecture/llms/README.md).

**Example** — README authored inside the zip:

```markdown
# Onboarding

Start with [the master lease](oc-import://document/documents/lease.pdf).
The renewal mechanic lives in [section 4(b)](oc-import://annotation/old-42).
```

After import, that same content reads:

```markdown
# Onboarding

Start with [the master lease](/d/jane/my-corpus/lease).
The renewal mechanic lives in [section 4(b)](/d/jane/my-corpus/lease?ann=587).
```

Unresolved references (filename not present in the zip, annotation id absent
from `data.json`) are **left intact** and a warning is logged so the author
can fix and re-import.  Revision snapshots are not rewritten — their
checksums refer to historical content, and bulk-import authors only write the
current README.

## Label Types in Exports

Labels in the export are categorized by type:

| Label Type | Location in data.json | Purpose |
|------------|----------------------|---------|
| `DOC_TYPE_LABEL` | `doc_labels` | Document-level classification labels |
| `TOKEN_LABEL` | `text_labels` | Token-level annotations (PDF bounding boxes) |
| `SPAN_LABEL` | `text_labels` | Character-offset annotations (text documents) |
| `RELATIONSHIP_LABEL` | `text_labels` | Labels for annotation-to-annotation relationships |

## Annotation Types in Exports

Each annotation in `labelled_text` carries positional data in `annotation_json`.
The format depends on the annotation type:

**Token annotations** (PDFs) reference PAWLs tokens by page and token index,
with bounding box coordinates.

**Span annotations** (text documents) use character offsets (`start`, `end`)
into the document's `content` string.

See the [Corpus Export Format Specification](../architecture/corpus-export-format-spec.md)
for the complete field reference, referential integrity rules, and security
limits.

For the V2 design rationale and implementation architecture, see
[Corpus Export/Import V2](../architecture/corpus_export_import_v2.md).
