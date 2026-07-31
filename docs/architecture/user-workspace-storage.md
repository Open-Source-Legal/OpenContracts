# User workspace storage

Every user owns a private `My Documents` corpus — `Corpus.is_personal`,
provisioned by the `User` `post_save` signal and reachable via
`opencontractserver/corpuses/models.py::Corpus.get_or_create_personal_corpus`.
It is an ordinary corpus, so it already has folders, versioning, permissions,
export and the document viewer.

`WorkspaceService` (`opencontractserver/corpuses/services/workspace.py`) is how
*generated* content gets filed there.

## Writing an artifact

```python
from opencontractserver.corpuses.services import WorkspaceService

document = WorkspaceService.save_markdown(
    user=user,
    title="Q3 Diligence Report",
    content=markdown,
    folder_name="Research Reports",   # created on first use
    filename_stem="q3-diligence",     # stable key; defaults to title
)
```

The service resolves the personal corpus, gets-or-creates the folder, and
writes through `documents/versioning.py::import_document`. It deliberately does
not move, delete or list — the workspace is a corpus, so `CorpusService`,
`FolderCRUDService` and `DocumentLifecycleService` already own those, with
permission surfaces that are already correct.

**Idempotency is by path.** Saving the same `filename_stem` into the same
folder versions the existing document: `version_number` increments, the prior
`Document.is_current` / `DocumentPath.is_current` flip to false, and the old
text stays retrievable in the version tree. Pass a stable `filename_stem`
(a slug) whenever the human title may change between saves — otherwise a
retitle strands the old file and starts a new one instead of versioning.

**Titles are untrusted.** They are usually model-generated, so `_safe_segment`
strips separators and control characters, collapses dot runs and drops leading
dots. Stripping `/` is what stops a title inventing a folder level; neutralising
`..` matters because these paths are written verbatim into corpus V2 export
ZIPs, where a surviving traversal segment is a zip-slip vector for whoever
extracts the archive.

## What processing a saved markdown file does and does not get

Two different signals decide this, and they disagree — which is easy to get
wrong:

- **`Document` `post_save`** (`documents/signals.py`) short-circuits the ingest
  chain for `text/markdown`: no parsing, no thumbnailing, no PAWLs, no
  annotations. It marks the document COMPLETED and, importantly, sets
  `backend_lock=False`.
- **`DocumentPath` `post_save`** then queues
  `calculate_embedding_for_doc_text` for any newly created current path whose
  document is *not* backend-locked. Markdown qualifies, so a saved artifact
  **does** get a document-level text embedding.

So the accurate statement is: a saved artifact has **no annotation-level
chunks** — nothing for passage retrieval to hit — but it **does** carry a
document-level embedding and can surface in document-level similarity search.
Saving is therefore not free: it costs one embedding call per save, and a
re-save creates a new version, hence another call.

This is ordinary platform behaviour for every markdown document, CAML articles
included; workspace saves are not special-cased.

## Making sure the file is actually visible

Markdown is hidden by default in more places than is obvious, and a saved
artifact that cannot be found is worthless. Two independent defaults:

- `Corpus._get_active_documents()` / `get_documents()` default to
  `include_caml=False`. Never use them to assert a saved artifact exists.
- `config/graphql/filters.py::DocumentFilter.filter_queryset` excludes markdown
  from any `documents(inCorpusWithId: …)` query that does not pass
  `includeCaml: true`.

`CorpusType.documents` passes `include_caml=True`, but the *corpus document
list a user actually browses* (`DocumentTableOfContents.tsx`, via
`GET_CORPUS_DOCUMENTS_FOR_TOC`) did not — so a saved report existed in the
database while `My Documents` rendered "No Documents". That query and component
now pass the flag.

**Any new consumer of `WorkspaceService` must check the surface it expects its
artifact to appear on.** Verify it in the running UI, not by querying the ORM:
the ORM will happily show you a document the interface is filtering out.
Deliberately unchanged: `RunCorpusActionModal` still omits the flag, because a
corpus action should not offer to run over a CAML article.

## Reading a saved artifact

Markdown documents open in `MarkdownDocumentViewer`
(`frontend/src/components/knowledge_base/document/document_kb/`) with a
**Rendered / Raw** toggle, using the same `MarkdownMessageRenderer` the chat
uses — so a saved answer reads in the document viewer the way it read in the
conversation.

Two things to preserve if you touch this:

- **The markdown branch must be tested before `isTextFileType`.** Markdown is a
  `text/…` subtype, so reordering the checks in `DocumentViewer` sends every
  markdown document back to the plain-text annotator and it renders as source.
  Guarded by `MarkdownDocumentViewer.ct.tsx`'s routing test.
- **Raw is the annotator, not a debug view.** Span annotations key on character
  offsets into the source text, so annotating a markdown document has to happen
  in Raw mode. Rendered is merely the default.

## Consumer: chat messages

A chat answer is otherwise saved nowhere. Unlike a research report it has no
model of its own, so the analysis exists only inside the conversation. The
`saveMessageToWorkspace` mutation
(`config/graphql/conversation_mutations.py`) files one message into the
caller's workspace, with an optional folder and a title that defaults to the
message's first meaningful line. The frontend control is
`frontend/src/components/widgets/chat/SaveMessageToWorkspace.tsx`, rendered on
finished assistant messages only.

`messageId` accepts **either** a relay global ID or a raw primary key, because
the frontend carries both: history loaded over GraphQL is a global ID
(`CorpusChat.tsx` `messageId: msg.id`) while a message streamed over the agent
WebSocket is the integer pk (`messageId: data.message_id`). Decoding blindly
turned the raw form into `''` and raised inside the ORM — so saving a
just-streamed answer, the most likely thing a user wants to keep, failed. Only
a live run catches this; a component test with a well-formed ID passes happily.

Permissioning is **visibility-based**, matching the discussion model in
`docs/permissioning/consolidated_permissioning_guide.md`: anyone who can READ
the conversation may keep a copy. That is deliberately weaker than editing
(creator-or-moderator) — a collaborator must not be blocked from keeping an
answer already on their screen — and it is safe because the copy is written to
the *saver's* private corpus, never the author's. The lookup uses
`BaseService.filter_visible`, so an invisible message and a nonexistent one are
indistinguishable.

## Consumer: deep-research reports

`ResearchReportService.finalize()` files each completed report at
`Research Reports/<report-slug>.md` in its creator's workspace, prefixed with a
provenance header (source corpus, generated date, `/research/<slug>` link) so
the file explains itself when opened outside the app. The resulting document is
linked from `ResearchReport.workspace_document` and exposed on the GraphQL type
as `workspaceDocument`.

The save runs **outside** `finalize`'s atomic block and swallows its errors: the
report is already COMPLETED with its provenance committed, and a research run
costs minutes of model time, so a failed file write must never roll that back.
On failure the report stands and `workspace_document` stays null.

Known limitation: moving or renaming the workspace file means the next save
recreates it at the canonical path rather than following it. `finalize` runs
once per report in the normal case; making the FK authoritative (resolving the
current `DocumentPath` from the linked document) is a contained follow-up.
