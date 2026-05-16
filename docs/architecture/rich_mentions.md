# Rich Mentions

Rich mentions let a chat or thread message refer to a corpus, document, annotation, agent, or user — and have those references render as styled, navigable chips with type-aware icons and metadata-rich tooltips. This document describes the end-to-end architecture: how a mention is captured in the composer, how it survives storage as plain markdown, how the backend re-hydrates it with permission-checked metadata, and how the renderer turns it back into a chip on screen.

For the composer mechanics specifically (TipTap configuration, the picker UI, the `@`-trigger flow), see `docs/frontend/discussions.md`. For the URL grammar that mentions ride on, see `docs/frontend/routing_system.md`.

## Why a round-trip resolver

The composer naturally has full metadata for whatever the user picked from the suggestion popup — annotation raw text, label, document title, corpus context. The renderer, reading a stored message, has only the markdown the composer emitted. Trying to stuff metadata into the markdown itself (custom node attributes, JSON blobs in the link text) breaks markdown portability, leaks stale data, and bypasses permissions when a message is read by someone other than its author.

The architecture instead treats markdown as the canonical wire format and re-derives metadata at render time, on the server, with the requesting user's permissions applied. The renderer never trusts the link text — it asks the resolver for a structured `mentionedResources` list keyed by URL, and merges that back in.

This means the same stored message can render *more* metadata to a privileged reader and *less* to an anonymous one, automatically, without ever rewriting the message body.

## Data shape: markdown links all the way down

Every mention type is stored as an ordinary markdown link inside the message body. There are no custom node types, no embedded JSON, no escape hatches. The composer's job is to pick a stable URL for the resource and a human-readable label; everything else is recoverable from those two strings.

The URL grammar is the contract:

| Resource | URL shape |
|---|---|
| User | `/users/{slug}` |
| Corpus | `/c/{creator-slug}/{corpus-slug}` |
| Document (in corpus) | `/d/{creator-slug}/{corpus-slug}/{doc-slug}` |
| Document (standalone) | `/d/{creator-slug}/{doc-slug}` |
| Annotation | `/d/.../{doc-slug}?ann={id}&structural=true` |
| Source (text-block deep link) | `/d/.../{doc-slug}?tb={...}` |
| Agent (global) | `/agents/{slug}` |
| Agent (corpus-scoped) | `/c/{...}/agents/{slug}` |

The renderer detects type purely from URL shape, so any link the composer (or an agent, or a paste) inserts using one of these patterns becomes a styled chip. Conversely, the resolver only has to recognize the same URL grammar to enrich a message — there is no separate "is this a mention" flag in the database.

A handful of legacy text patterns (`@corpus:slug`, `@document:slug`, `@corpus:.../document:...`) are also recognized by the resolver. They predate the composer's "everything is a markdown link" approach and exist mainly for agent-authored messages and pasted text. New code should not introduce more text patterns; any new mention type should add a URL shape instead.

## Backend: `mentioned_resources` resolver

The `MessageType.mentioned_resources` GraphQL field returns a list of `MentionedResourceType` objects derived from the message body. The resolver:

1. Scans the message content for the supported text patterns and the markdown link grammar above.
2. For each match, looks up the resource through its `Model.objects.visible_to_user(user)` manager. This is the single permission gate — invisible resources are silently skipped, never returned with empty fields, never raise errors.
3. Builds a `MentionedResourceType` carrying `type`, `id`, `slug`, `title`, `url` (the original URL, so the frontend can match it), and type-specific extras: `corpus` parent for documents, `document` parent and `raw_text` and `annotation_label` for annotations.
4. Returns the list. Order follows pattern-scan order, which is stable for any given message.

The resolver runs per-request, so an annotation that becomes invisible to a user (re-permissioned, soft-deleted, etc.) just stops appearing in their `mentionedResources` — the chip falls back to a plain styled link without the rich tooltip.

`MentionedResourceType` is a lightweight `graphene.ObjectType`, not a `DjangoObjectType`. It is intentionally a shallow projection: enough for chips and tooltips, never a back door into the full domain object graph. If the frontend needs more, it should issue a follow-up query against the proper typed root field.

## Frontend: lookup-then-render

`MarkdownMessageRenderer` receives the message body and the `mentionedResources` array as separate props (wired through `MessageItem`). It builds a `Map<url, resource>` once per render via `useMemo`, then walks the markdown tree with `react-markdown`.

The custom `<a>` renderer:

1. Inspects the `href` and detects mention type from URL shape.
2. Looks up the URL in the resource map.
3. Renders a styled `MentionLink` chip — type-specific gradient, border, icon (from `lucide-react`), and a tooltip.
4. For tooltips, prefers metadata from the resource map. Annotations get a multi-line tooltip with the (truncated, sanitized) raw text plus label and document context. Other types fall back to the link's text content.
5. Routes clicks through `react-router-dom`'s `navigate` instead of letting the browser do a full page load. Mention types whose detail page does not yet exist (currently only `agent`) render with `$navigable={false}` and suppress the `href`/click handler.

A link whose URL does not match any known mention shape — or whose URL matches but is not in `mentionedResources` (anonymous user, deleted resource, future format) — falls through to the `RegularLink` branch and renders as an ordinary external link. This is the graceful-degradation contract: mentions never look broken, they just lose their richness.

All user-controlled strings flowing into tooltips pass through `sanitizeForTooltip`. The composer also sanitizes annotation previews via `sanitizeForMention` before they enter the markdown body. Both live in `frontend/src/utils/textSanitization.ts`.

## Type-to-route configuration

The `MENTION_TYPES` table in `frontend/src/assets/configurations/constants.ts` is the single registry of which mention types currently have a navigable detail page. The renderer reads `navigable` to decide whether the chip is clickable, and uses the same map's `label` in fallback tooltips. Adding a route for a new type is a one-line config change — no renderer edit needed.

## End-to-end flow

```
Composer (MessageComposer + UnifiedMentionPicker)
    User picks a resource from the @-suggestion popup
    getMentionData() chooses a label and URL
    TipTap inserts text + Link mark — exported as plain [label](url) markdown
        ↓
Storage (ChatMessage.content)
    A single markdown string. No metadata sidecar, no custom nodes.
        ↓
GraphQL query (chatMessage / threadMessages / etc.)
    Frontend asks for `content` and `mentionedResources { ... }` together.
    Resolver scans content, applies visible_to_user(), returns enriched list.
        ↓
Render (MessageItem → MarkdownMessageRenderer)
    react-markdown walks the body.
    Custom <a> renderer: detect type from URL → look up resource by URL →
    render MentionLink chip with icon + tooltip.
        ↓
Click
    react-router-dom navigates in-app for navigable types;
    non-navigable types render as inert chips with a "coming soon" tooltip.
```

## Security model

- **Permissions are enforced once, at resolution time**, by the `visible_to_user()` manager method for each model. There is no separate access check in the renderer — if a resource is in the response, the user is allowed to see its metadata.
- **Silent omission, not error**: an inaccessible or deleted resource produces no entry in `mentionedResources`. The chip still renders (URL is public to anyone with the message body) but without rich metadata. This avoids leaking existence-of-resource information through error states.
- **XSS**: tooltips are plain `title` attributes (browser-rendered, not HTML), and any user-generated text routed into them is run through the sanitization utilities. Markdown body rendering uses `rehype-sanitize` on top of `react-markdown`.
- **Annotation IDs in URLs may be either plain integer IDs or base64-encoded Relay global IDs**; the resolver decodes both. New URL formats should be added to the resolver's extractor in lockstep with the composer.

## When to extend this system

- **New URL shape for an existing type** — update both the composer's `getMentionData` and the resolver's pattern-matching, plus the renderer's `detectMentionType` if the shape is genuinely new.
- **New mention type** — add a row to `MENTION_TYPES`, a case to the composer's `getMentionData`, a branch in `detectMentionType` and `getMentionIcon`, and (if the type carries metadata worth showing in a tooltip) extend `MentionedResourceType` and the resolver. Stay shallow — this type is a projection, not a model mirror.
- **New metadata field for an existing type** — add the field to `MentionedResourceType`, populate it in the resolver behind the existing permission gate, and consume it in `getMentionTooltip`. The GraphQL fragment in `frontend/src/graphql/queries.ts` is the contract surface; update it there.

## Related files

- `config/graphql/conversation_types.py` — `MentionedResourceType` and `MessageType.resolve_mentioned_resources`
- `frontend/src/components/threads/MarkdownMessageRenderer.tsx` — chip rendering, tooltip composition
- `frontend/src/components/threads/MessageComposer.tsx` — composer, `getMentionData`
- `frontend/src/components/threads/UnifiedMentionPicker.tsx` — picker UI
- `frontend/src/components/threads/hooks/useUnifiedMentionSearch.ts` — search backend
- `frontend/src/assets/configurations/constants.ts` — `MENTION_TYPES` registry
- `frontend/src/utils/textSanitization.ts` — `sanitizeForTooltip`, `sanitizeForMention`
- `opencontractserver/tests/test_mentions.py` — resolver tests covering each pattern and permission gate
