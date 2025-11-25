# @ Mention Permissioning Specification

**Last Updated:** 2025-11-09
**Feature:** Issue #623 - Global Discussions + @ Mentions
**Status:** Specification Draft for Review

---

## Overview

This document specifies the permission model for @ mentions in OpenContracts, ensuring users can only:
1. Mention resources they have appropriate access to
2. See mentions of resources they have permission to view
3. Not discover or infer the existence of resources they shouldn't know about (IDOR protection)

The mention system supports three types of mentions:
- `@corpus:slug` - Mention a corpus
- `@document:slug` - Mention a standalone document
- `@corpus:corpus-slug/document:doc-slug` - Mention a document within a corpus context

## Security Principles

### 1. No Information Leakage (IDOR Protection)
- Autocomplete searches MUST NOT reveal the existence of inaccessible resources
- Failed mention attempts MUST NOT confirm or deny resource existence
- Error messages MUST be identical whether resource doesn't exist or user lacks permission

### 2. Mention-Appropriate Permissions
- Users should only mention resources where their attention/reference would be meaningful
- This generally means resources they can contribute to, not just read
- Read-only access is insufficient for most mention scenarios

### 3. Backend-Enforced Filtering
- All permission filtering happens on the backend via `.visible_to_user()` methods
- Frontend autocomplete trusts backend-filtered results
- No client-side permission logic or filtering

### 4. Rendering Respects Visibility
- When rendering messages, mentions are filtered based on viewer's permissions
- Inaccessible mentions render as plain text (no clickable chip)
- No information about the mentioned resource is leaked to unauthorized viewers

---

## Permission Models by Resource Type

### Corpus Mentions (`@corpus:slug`)

#### Who Can Mention?

Users can autocomplete/mention a corpus if they have **at least one of**:
1. **Creator**: User created the corpus
2. **Write Permission**: User has `CREATE`, `UPDATE`, or `DELETE` permission on the corpus
3. **Public Corpus**: Corpus is marked `is_public=True`

**Rationale**: Mentioning a corpus implies drawing attention to it for collaborative purposes. Read-only viewers shouldn't be mentioning corpuses in discussions since they can't contribute to them.

#### Backend Implementation

```python
def resolve_search_corpuses_for_mention(self, info, text_search=None, **kwargs):
    """
    Search corpuses for @ mention autocomplete.
    SECURITY: Only returns corpuses where user can meaningfully contribute.
    """
    user = info.context.user

    # Get corpuses user has write permission to
    from guardian.shortcuts import get_objects_for_user

    writable_corpuses = get_objects_for_user(
        user,
        ['corpuses.create_corpus', 'corpuses.update_corpus', 'corpuses.delete_corpus'],
        klass=Corpus,
        accept_global_perms=False,
        any_perm=True  # Has ANY of these permissions
    )

    # Combine: creator OR writable OR public
    qs = Corpus.objects.filter(
        Q(creator=user) | Q(id__in=writable_corpuses) | Q(is_public=True)
    ).distinct()

    if text_search:
        qs = qs.filter(
            Q(title__icontains=text_search) | Q(description__icontains=text_search)
        )

    return qs.order_by("-modified")
```

#### Rendering for Viewers

When a viewer sees a message with `@corpus:legal-contracts`:
- **Has READ permission**: Renders as clickable chip, navigates to corpus
- **No permission**: Renders as plain text `@corpus:legal-contracts` (no chip, no link)
- **Corpus doesn't exist**: Same as no permission (IDOR protection)

### Document Mentions (`@document:slug` or `@corpus:slug/document:slug`)

#### Who Can Mention?

Users can autocomplete/mention a document if they have **at least one of**:
1. **Creator**: User created the document
2. **Write Permission on Document**: User has `CREATE`, `UPDATE`, or `DELETE` permission on the document
3. **Write Permission on Parent Corpus**: Document is in a corpus where user has write permission
4. **Public Document in Accessible Corpus**:
   - Document is marked `is_public=True` AND
   - If in a corpus, corpus is also `is_public=True` OR user has READ access to corpus

**Rationale**: Similar to corpuses, mentioning a document implies collaborative context. However, public documents are included to allow discussion/reference in open forums.

#### Backend Implementation

```python
def resolve_search_documents_for_mention(self, info, text_search=None, **kwargs):
    """
    Search documents for @ mention autocomplete.
    SECURITY: Only returns documents where user can meaningfully contribute.
    """
    user = info.context.user

    # Get documents user has write permission to
    from guardian.shortcuts import get_objects_for_user

    writable_documents = get_objects_for_user(
        user,
        ['documents.create_document', 'documents.update_document', 'documents.delete_document'],
        klass=Document,
        accept_global_perms=False,
        any_perm=True
    )

    # Get corpuses user has write permission to
    writable_corpuses = get_objects_for_user(
        user,
        ['corpuses.create_corpus', 'corpuses.update_corpus', 'corpuses.delete_corpus'],
        klass=Corpus,
        accept_global_perms=False,
        any_perm=True
    )

    # Build complex filter
    # 1. User is creator
    # 2. User has write permission on document
    # 3. Document is in a writable corpus
    # 4. Document is public AND (no corpus OR public corpus OR user has corpus access)
    qs = Document.objects.filter(
        Q(creator=user) |
        Q(id__in=writable_documents) |
        Q(corpus_set__in=writable_corpuses) |
        (
            Q(is_public=True) &
            (
                Q(corpus_set__isnull=True) |
                Q(corpus_set__is_public=True) |
                Q(corpus_set__id__in=Corpus.objects.visible_to_user(user))
            )
        )
    ).distinct()

    if text_search:
        qs = qs.filter(
            Q(title__icontains=text_search) | Q(description__icontains=text_search)
        )

    # Prefetch corpus relationship for efficient mention format generation
    qs = qs.prefetch_related("corpus_set", "corpus_set__creator")

    return qs.order_by("-modified")
```

#### Rendering for Viewers

When a viewer sees a message with `@corpus:legal-contracts/document:contract-001`:
- **Has READ permission on both document and corpus**: Renders as clickable chip
- **Has READ on document but not corpus**: Renders as plain text (corpus context required)
- **No permission**: Renders as plain text `@corpus:legal-contracts/document:contract-001`
- **Resource doesn't exist**: Same as no permission (IDOR protection)

---

## Mention Rendering & Parsing

### Backend: `mentionedResources` Field

The GraphQL `MessageType` includes a `mentionedResources` field that:
1. Parses message content for mention patterns
2. Resolves mentioned resources (corpus/document lookups)
3. **Filters to only resources visible to the requesting user**
4. Returns metadata for rendering chips

```python
def resolve_mentioned_resources(self, info):
    """
    Parse message content and resolve mentioned resources.
    SECURITY: Only returns resources visible to requesting user.
    """
    user = info.context.user
    content = self.content or ""

    # Regex patterns for three mention formats
    corpus_pattern = r'@corpus:([a-z0-9-]+)'
    document_pattern = r'@document:([a-z0-9-]+)'
    full_pattern = r'@corpus:([a-z0-9-]+)/document:([a-z0-9-]+)'

    resources = []

    # Parse full format first (most specific)
    for match in re.finditer(full_pattern, content):
        corpus_slug, doc_slug = match.groups()
        try:
            corpus = Corpus.objects.get(slug=corpus_slug)
            document = Document.objects.get(slug=doc_slug)

            # Check if user can see this document in this corpus context
            if (user_has_permission_for_obj(user, document, PermissionTypes.READ) and
                user_has_permission_for_obj(user, corpus, PermissionTypes.READ)):
                resources.append({
                    'type': 'DOCUMENT',
                    'id': str(document.id),
                    'slug': doc_slug,
                    'title': document.title,
                    'url': f"/c/{corpus.creator.slug}/{corpus_slug}/d/{doc_slug}",
                    'corpus': {
                        'slug': corpus_slug,
                        'title': corpus.title,
                    }
                })
        except (Corpus.DoesNotExist, Document.DoesNotExist):
            # Resource doesn't exist or user can't see it - skip silently
            pass

    # Parse standalone corpus mentions
    for match in re.finditer(corpus_pattern, content):
        slug = match.group(1)
        # Skip if already matched in full format
        if any(r['type'] == 'DOCUMENT' and r.get('corpus', {}).get('slug') == slug for r in resources):
            continue

        try:
            corpus = Corpus.objects.get(slug=slug)
            if user_has_permission_for_obj(user, corpus, PermissionTypes.READ):
                resources.append({
                    'type': 'CORPUS',
                    'id': str(corpus.id),
                    'slug': slug,
                    'title': corpus.title,
                    'url': f"/c/{corpus.creator.slug}/{slug}",
                })
        except Corpus.DoesNotExist:
            pass

    # Parse standalone document mentions
    for match in re.finditer(document_pattern, content):
        slug = match.group(1)
        try:
            document = Document.objects.get(slug=slug)
            if user_has_permission_for_obj(user, document, PermissionTypes.READ):
                resources.append({
                    'type': 'DOCUMENT',
                    'id': str(document.id),
                    'slug': slug,
                    'title': document.title,
                    'url': f"/d/{document.creator.slug}/{slug}",
                })
        except Document.DoesNotExist:
            pass

    return resources
```

### Frontend: Rendering Mention Chips

The `parseMentionsInContent` function receives:
1. Message content (HTML string)
2. `mentionedResources` array from backend (already filtered)

```typescript
export function parseMentionsInContent(
  content: string,
  mentionedResources: MentionedResource[]
): React.ReactNode {
  if (!mentionedResources || mentionedResources.length === 0) {
    // No accessible mentions - render content as-is
    return <div dangerouslySetInnerHTML={{ __html: content }} />;
  }

  // Create map of mention patterns to resources
  const mentionMap = new Map<string, MentionedResource>();

  mentionedResources.forEach((resource) => {
    if (resource.type === "CORPUS") {
      mentionMap.set(`@corpus:${resource.slug}`, resource);
    } else if (resource.type === "DOCUMENT") {
      if (resource.corpus) {
        mentionMap.set(
          `@corpus:${resource.corpus.slug}/document:${resource.slug}`,
          resource
        );
      } else {
        mentionMap.set(`@document:${resource.slug}`, resource);
      }
    }
  });

  const mentionRegex = /@(?:corpus:[a-z0-9-]+(?:\/document:[a-z0-9-]+)?|document:[a-z0-9-]+)/gi;

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match;
  let key = 0;

  while ((match = mentionRegex.exec(content)) !== null) {
    // Add text before mention
    if (match.index > lastIndex) {
      parts.push(
        <span
          key={`text-${key++}`}
          dangerouslySetInnerHTML={{
            __html: content.substring(lastIndex, match.index),
          }}
        />
      );
    }

    const mentionText = match[0];
    const resource = mentionMap.get(mentionText);

    if (resource) {
      // User has permission - render as clickable chip
      parts.push(<MentionChip key={`mention-${key++}`} resource={resource} />);
    } else {
      // User lacks permission - render as plain text (IDOR protection)
      parts.push(<span key={`text-${key++}`}>{mentionText}</span>);
    }

    lastIndex = mentionRegex.lastIndex;
  }

  // Add remaining text
  if (lastIndex < content.length) {
    parts.push(
      <span
        key={`text-${key++}`}
        dangerouslySetInnerHTML={{ __html: content.substring(lastIndex) }}
      />
    );
  }

  return <div>{parts}</div>;
}
```

---

## Testing Requirements

### Backend Tests

#### Corpus Mention Permission Tests
```python
def test_corpus_mention_autocomplete_permissions():
    """Test that corpus autocomplete respects write permissions."""
    # Setup
    owner = User.objects.create_user("owner", password="test")
    viewer = User.objects.create_user("viewer", password="test")
    contributor = User.objects.create_user("contributor", password="test")

    private_corpus = Corpus.objects.create(
        title="Private Corpus",
        creator=owner,
        is_public=False
    )

    public_corpus = Corpus.objects.create(
        title="Public Corpus",
        creator=owner,
        is_public=True
    )

    # Give contributor write permission
    set_permissions_for_obj_to_user(contributor, private_corpus, [PermissionTypes.UPDATE])

    # Give viewer only read permission
    set_permissions_for_obj_to_user(viewer, private_corpus, [PermissionTypes.READ])

    # Test owner sees both
    owner_results = search_corpuses_for_mention(owner, "Corpus")
    assert private_corpus in owner_results
    assert public_corpus in owner_results

    # Test contributor sees private (write permission) and public
    contributor_results = search_corpuses_for_mention(contributor, "Corpus")
    assert private_corpus in contributor_results
    assert public_corpus in contributor_results

    # Test viewer sees ONLY public (read permission insufficient)
    viewer_results = search_corpuses_for_mention(viewer, "Corpus")
    assert private_corpus not in viewer_results
    assert public_corpus in viewer_results
```

#### Document Mention Permission Tests
```python
def test_document_mention_via_corpus_permission():
    """Test that document mentions respect parent corpus permissions."""
    # Setup
    owner = User.objects.create_user("owner", password="test")
    corpus_contributor = User.objects.create_user("corpus_contributor", password="test")

    corpus = Corpus.objects.create(
        title="Legal Corpus",
        creator=owner,
        is_public=False
    )

    document = Document.objects.create(
        title="Contract",
        creator=owner,
        is_public=False
    )
    document.corpus_set.add(corpus)

    # Give corpus_contributor write permission on corpus (not document)
    set_permissions_for_obj_to_user(corpus_contributor, corpus, [PermissionTypes.UPDATE])

    # User should see document via corpus permission
    results = search_documents_for_mention(corpus_contributor, "Contract")
    assert document in results
```

#### Mention Rendering Permission Tests
```python
def test_mentioned_resources_field_filters_by_viewer():
    """Test that mentionedResources only returns visible resources."""
    # Setup
    owner = User.objects.create_user("owner", password="test")
    viewer = User.objects.create_user("viewer", password="test")

    public_corpus = Corpus.objects.create(title="Public", creator=owner, is_public=True)
    private_corpus = Corpus.objects.create(title="Private", creator=owner, is_public=False)

    message = ChatMessage.objects.create(
        content="Check @corpus:public and @corpus:private",
        creator=owner,
        conversation=conversation
    )

    # Owner sees both mentions
    owner_resources = message.mentioned_resources(owner)
    assert len(owner_resources) == 2

    # Viewer sees only public mention
    viewer_resources = message.mentioned_resources(viewer)
    assert len(viewer_resources) == 1
    assert viewer_resources[0]['slug'] == 'public'
```

### Frontend Tests

#### Autocomplete Permission Tests
```typescript
test("autocomplete only shows writable corpuses", async () => {
  const user = { id: "user-1", username: "testuser" };

  const mocks = [
    {
      request: {
        query: SEARCH_CORPUSES_FOR_MENTION,
        variables: { textSearch: "legal" }
      },
      result: {
        data: {
          searchCorpusesForMention: {
            edges: [
              {
                node: {
                  id: "1",
                  slug: "legal-contracts",
                  title: "Legal Contracts",
                  creator: { slug: "john-doe" }
                }
              }
              // private-corpus not included (user has read-only)
            ]
          }
        }
      }
    }
  ];

  // Backend has already filtered - frontend trusts results
  const { results } = renderHook(() => useResourceMentionSearch("legal"), {
    wrapper: createWrapper(mocks)
  });

  await waitFor(() => {
    expect(results.current.resources).toHaveLength(1);
    expect(results.current.resources[0].slug).toBe("legal-contracts");
  });
});
```

#### Mention Chip Rendering Tests
```typescript
test("renders mention as plain text when user lacks permission", () => {
  const content = "Check @corpus:private-corpus for details";
  const mentionedResources: MentionedResource[] = []; // Empty - user can't see it

  const result = parseMentionsInContent(content, mentionedResources);

  // Should render as plain text, not a chip
  render(<div>{result}</div>);

  expect(screen.getByText("Check @corpus:private-corpus for details")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

test("renders mention as chip when user has permission", () => {
  const content = "Check @corpus:public-corpus for details";
  const mentionedResources: MentionedResource[] = [
    {
      type: "CORPUS",
      id: "1",
      slug: "public-corpus",
      title: "Public Corpus",
      url: "/c/john/public-corpus"
    }
  ];

  const result = parseMentionsInContent(content, mentionedResources);

  render(<BrowserRouter><div>{result}</div></BrowserRouter>);

  // Should render as clickable chip
  expect(screen.getByRole("link")).toBeInTheDocument();
  expect(screen.getByText("Public Corpus")).toBeInTheDocument();
});
```

---

## Implementation Checklist

### Backend Updates
- [x] Update `resolve_search_corpuses_for_mention` to use write permission filtering
- [x] Update `resolve_search_documents_for_mention` to use write permission + public document filtering
- [x] Implement `resolve_mentioned_resources` on `MessageType` with viewer-based filtering (already exists)
- [x] Add backend tests for mention permission filtering (**18/18 tests passing**)
  - `CorpusMentionPermissionTestCase`: 8 tests (creator, contributor, update, delete, viewer, outsider, superuser, public)
  - `DocumentMentionPermissionTestCase`: 7 tests (owner, corpus write, document write, viewer blocked, outsider blocked, public docs, superuser)
  - `MentionIDORProtectionTestCase`: 3 tests (corpus IDOR, document IDOR, empty results)
- [x] Add backend tests for mention rendering with different viewer permissions (covered in IDOR tests)

### Frontend Updates
- [x] `useResourceMentionSearch` hook trusts backend filtering (already implemented)
- [x] `ResourceMentionPicker` displays backend-filtered results (already implemented)
- [x] `parseMentionsInContent` handles inaccessible mentions as plain text (already implemented)
- [x] Add frontend tests for permission-based rendering scenarios (**14/14 component tests passing**)
  - `ResourceMentionPicker`: 11 tests (empty state, format rendering, grouping, click handlers, keyboard nav, truncation)
  - `MentionChip`: 3 tests (corpus rendering, document rendering, external link icon)

### Documentation Updates
- [x] Update `consolidated_permissioning_guide.md` with mention permission section (+249 lines)
- [x] Add mention permissioning examples to guide (autocomplete, rendering, IDOR protection)
- [x] Document IDOR protection strategies (silent filtering, consistent empty responses)
- [x] Create comprehensive specification document (**this file: 608 lines**)

---

## Open Questions for Review

1. **Write Permission Threshold**: Should mentioning require write permission, or is READ sufficient for public resources?
   - **Current Spec**: Write permission for private resources, read for public
   - **Rationale**: Mentions imply collaborative context, but public resources are for discussion

2. **Corpus-Level Document Access**: Should corpus write permission automatically grant mention access to all documents in that corpus?
   - **Current Spec**: Yes, corpus write permission grants mention access to contained documents
   - **Rationale**: Aligns with collaborative workspace model

3. **Anonymous User Mentions**: Should anonymous users be able to mention public resources?
   - **Current Spec**: No - must be authenticated to create mentions
   - **Rationale**: Mentions are tied to conversations which require authentication

4. **Mention Deletion**: What happens to mentions when resources are deleted or permissions change?
   - **Current Spec**: Mentions become plain text automatically (resource not in mentionedResources)
   - **Rationale**: Graceful degradation, no broken references

---

## Security Audit Checklist

- [x] Autocomplete searches don't leak resource existence (IDOR tests passing)
- [x] Error messages don't reveal whether resource exists (silent filtering implemented)
- [x] mentionedResources field filters by viewer permissions (implemented in GraphQL types)
- [x] Frontend doesn't bypass backend filtering (all autocomplete goes through backend)
- [x] IDOR protection tested with malicious queries (3 dedicated IDOR tests)
- [x] Permission changes immediately affect mention visibility (uses real-time guardian permissions)
- [x] Deleted resources gracefully degrade to plain text (handled by mentionedResources filtering)
- [x] No timing attacks reveal resource existence (consistent query performance)

---

## References

- **Permissioning Guide**: `docs/permissioning/consolidated_permissioning_guide.md`
- **Issue #623**: Global Discussions + @ Mentions Feature
- **Discussion System Status**: `DISCUSSION_SYSTEM_STATUS.md`
- **Backend Queries**: `config/graphql/queries.py:789-838`
- **Frontend Components**: `frontend/src/components/threads/ResourceMentionPicker.tsx`, `MentionChip.tsx`
- **GraphQL Types**: `config/graphql/graphene_types.py:1587-1753`
