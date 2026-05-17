# Key Concepts

This page walks through the core data types and patterns in OpenContracts. It is the recommended starting point for the [walkthrough](step-1-add-documents.md).

## Data Types

OpenContracts organises knowledge into a small set of first-class entities:

1. **Documents** — uploaded files. PDFs are the primary format (full layout and annotation fidelity via the Docling microservice); DOCX (Docxodus) and plain text (`.txt`) are also supported. See [Supported File Formats](../upload_methods/supported_formats.md).
2. **Corpuses** — collections of documents. A document can live in zero or more corpuses. Corpuses can be nested into folder hierarchies (`CorpusFolder`), forked from public corpuses, exported, imported, and version-controlled.
3. **Annotations** — text-level spans (highlighted text), document-level type labels, or token-level spans. Annotations can be created by humans, by analyzers, or by AI agents. Each annotation has a `LabelSet`-scoped `AnnotationLabel`.
4. **Relationships** — directed edges between annotations, with their own `AnnotationLabel`. Used for cross-references, parent/child structural relationships, and pre-materialised `OC_SUBTREE_GROUP` rows for efficient block-level retrieval.
5. **Notes** — long-form prose attached to a document or corpus. Distinct from annotations; intended for human-written commentary.
6. **Conversations & Threads** — persistent chat history. Conversations come in two flavours: `CHAT` (one-on-one chat with an AI agent) and `THREAD` (forum-style discussion). Threads support voting, moderation, @-mentions, and agent participation.
7. **Analyses** — read-only annotation sets produced by a document analyzer (see [analyzers documentation](../architecture/analyzers.md)).
8. **Extracts / Fieldsets / Datacells** — structured data extraction across documents. A `Fieldset` defines columns (`Column` rows) with prompts; running it against a corpus produces an `Extract` with one `Datacell` per (document, column).
9. **Metadata** — typed custom metadata fields with validation, attached to corpuses and documents. See [Metadata Overview](../metadata/metadata_overview.md).
10. **Badges & Reputation** — gamified recognition tied to community contributions. See [Badge System](../features/badge_system.md).
11. **Corpus Actions** — automation triggers. Run a fieldset, analyzer, or AI agent automatically when a document is added/edited or a new thread/message arrives. See [Corpus Actions](../corpus_actions/intro_to_corpus_actions.md).
12. **Agent Configurations** — saved configurations for AI agents (`AgentConfiguration` model) with scope (`GLOBAL` or corpus-scoped), tool allowlists, and approval policies.

## Permissioning

OpenContracts uses [`django-guardian`](https://django-guardian.readthedocs.io/) for per-object permissions, layered with custom queryset managers:

- Each `Model.objects.visible_to_user(user)` returns the queryset of objects the user can see (public + owned + explicitly shared).
- Annotations and Relationships do **not** carry individual permissions; access is inherited from the document and corpus they live in (effective permission = `min(document_permission, corpus_permission)`).
- Documents and Corpuses carry direct object-level permissions.
- Analyses and Extracts use a hybrid model (own permissions + corpus permissions + document filtering).
- Structural annotations (those bound to a `StructuralAnnotationSet`) are read-only except for superusers.

The full guide is at [Consolidated Permissioning Guide](../permissioning/consolidated_permissioning_guide.md).

## Sharing & Forking

Public visibility is a first-class UI feature: the corpus settings tab exposes a "make public" toggle, the corpus card shows the visibility badge, and anyone can fork a public corpus from the corpus home page. Forking is now implemented as `export-V2 → import-V2` so the fork format is guaranteed to round-trip cleanly (see [Corpus Forking](../architecture/corpus_forking.md)).

Behind the UI, the underlying GraphQL mutations are `setCorpusVisibility` and `startCorpusFork`. The `makeAnalysisPublic` mutation is also available for analysis sharing.

## GraphQL

OpenContracts uses [Graphene](https://graphene-python.org/) to serve GraphQL. The GraphiQL playground lives at the application root URL `/graphql/`:

- Local development: `http://localhost:8000/graphql/`
- Demo / production: e.g., `https://contracts.opensource.legal/graphql/`

Anonymous requests can see public data. To act as a user you can either log in to the Django admin (session cookie) or call the `tokenAuth` mutation to obtain a JWT.

The schema is checked into the repository at [`schema.graphql`](https://github.com/Open-Source-Legal/OpenContracts/blob/main/schema.graphql); GraphiQL's built-in docs explorer is the easiest way to browse types interactively.

## WebSockets

Real-time streaming chat is delivered over Django Channels. Three consumer endpoints are exposed (see [WebSocket Protocol](../architecture/websocket/protocol.md)):

- `ws/agent-chat/` — unified agent conversation (document chat, corpus chat, standalone agent chat). Context is supplied via query parameters: `?corpus_id=X`, `?document_id=X`, `?agent_id=X`, `?conversation_id=X`.
- `ws/thread-updates/` — agent-mention streaming inside discussion threads. Requires `?conversation_id=X`.
- `ws/notification-updates/` — real-time notification push (badges, moderation events, agent responses).

All WebSocket connections are authenticated by the shared `JWTAuthMiddleware`, which handles both Django session auth and Auth0 JWTs.
