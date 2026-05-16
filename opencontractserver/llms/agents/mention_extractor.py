"""Shared markdown-mention extractor.

Pure-parse layer. Used by:
  - config/graphql/conversation_types.py::MessageType.resolve_mentioned_resources
  - config/graphql/conversation_types.py::ChatMessageType.resolve_mentioned_resources
  - config/websocket/consumers/unified_agent_conversation.py (per-turn @-routing)

Grammar matches docs/architecture/rich_mentions.md.
"""

from __future__ import annotations

import base64
import binascii
import re
import sys
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse

# Runtime guard: ``_LEGACY_CORPUS_RE`` below uses a possessive quantifier
# (``++``), which Python's ``re`` module only learned to compile in 3.11.
# On 3.10 and earlier the module-load step raises ``re.error: multiple
# repeat`` from the ``re.compile`` call, but the error doesn't pinpoint
# the cause — fail loudly here instead so the operator sees the real
# constraint.  The production Docker image pins 3.11.x.
if sys.version_info < (3, 11):  # pragma: no cover - guard for older runtimes
    raise RuntimeError(
        "opencontractserver.llms.agents.mention_extractor requires "
        "Python >= 3.11 (uses the ``++`` possessive quantifier in "
        "``_LEGACY_CORPUS_RE``).  Upgrade the interpreter or rewrite the "
        "pattern with an atomic group ``(?>...)``."
    )

MentionType = Literal["agent", "user", "corpus", "document", "annotation"]

# Markdown link pattern: [label](url)
_LINK_RE = re.compile(r"\[([^\]]*)\]\((/[^)\s]+)\)")

# Legacy text patterns. Character classes and the `@corpus:` negative
# lookahead match the existing resolver in
# config/graphql/conversation_types.py (see Pattern 2 / Pattern 3) so the
# combined `@corpus:X/document:Y` form does not double-emit a corpus mention.
# The possessive quantifier `++` prevents the slug match from backtracking
# into a shorter prefix to satisfy the lookahead — without it,
# `@corpus:acme-corp/document:spec-doc` would yield a spurious `acme-cor`
# corpus mention.  Possessive quantifiers were added to Python's ``re``
# module in 3.11 (the project's pinned production runtime); rewrite with an
# atomic group ``(?>...)`` if you ever need to support 3.10 or earlier.
_LEGACY_CORPUS_RE = re.compile(r"@corpus:([a-z0-9-]++)(?!/document:)", re.IGNORECASE)
_LEGACY_DOCUMENT_RE = re.compile(r"@document:([a-z0-9-]+)", re.IGNORECASE)
_LEGACY_CORPUS_DOC_RE = re.compile(
    r"@corpus:([a-z0-9-]+)/document:([a-z0-9-]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedMention:
    type: MentionType
    slug: str | None = None
    id: int | None = None
    corpus_slug: str | None = None
    url: str = ""
    label: str = ""


def _decode_annotation_id(raw: str) -> int | None:
    """Decode either a plain int or a base64 Relay global id."""
    try:
        decoded = base64.b64decode(raw, validate=True).decode("utf-8")
        parts = decoded.split(":")
        if len(parts) == 2:
            return int(parts[1])
    except (ValueError, binascii.Error, UnicodeDecodeError):
        # Not a valid base64-encoded Relay global id — fall through to the
        # plain-integer path below.  Both forms are legitimate inputs from
        # the frontend, so a decode failure here is expected, not an error.
        pass
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _classify_url(url: str, label: str) -> ExtractedMention | None:
    """Map a path URL to an ExtractedMention. Returns None if not a known shape."""
    parsed = urlparse(url)
    path = parsed.path
    parts = [p for p in path.strip("/").split("/") if p]

    # /users/{slug}
    if len(parts) == 2 and parts[0] == "users":
        return ExtractedMention(type="user", slug=parts[1], url=url, label=label)

    # /agents/{slug}
    if len(parts) == 2 and parts[0] == "agents":
        return ExtractedMention(type="agent", slug=parts[1], url=url, label=label)

    # /c/{...}/agents/{slug} (corpus-scoped agent)
    # The corpus slug is the path segment immediately before `agents/{slug}`,
    # which covers both `/c/{corpus-slug}/agents/{slug}` (4 parts) and the
    # longer `/c/{creator-slug}/{corpus-slug}/agents/{slug}` (5 parts) form.
    # Pinned to exactly those two shapes: a path like
    # ``/c/x/agents/foo/agents/bar`` would otherwise accidentally match the
    # ``parts[-2] == "agents"`` heuristic and emit a wrong (corpus_slug,
    # slug) pair.
    if len(parts) in (4, 5) and parts[0] == "c" and parts[-2] == "agents":
        corpus_slug = parts[-3]
        return ExtractedMention(
            type="agent",
            slug=parts[-1],
            corpus_slug=corpus_slug,
            url=url,
            label=label,
        )

    # /c/{creator-slug}/{corpus-slug} (corpus)
    if len(parts) == 3 and parts[0] == "c":
        return ExtractedMention(type="corpus", slug=parts[2], url=url, label=label)

    # /d/.../doc?ann=... (annotation)
    if parts and parts[0] == "d" and parsed.query:
        query = parse_qs(parsed.query)
        ann_values = query.get("ann") or []
        ann_raw = ann_values[0] if ann_values else ""
        if ann_raw:
            ann_id = _decode_annotation_id(ann_raw)
            if ann_id is not None:
                return ExtractedMention(
                    type="annotation", id=ann_id, url=url, label=label
                )

    # /d/{creator-slug}/{doc-slug}  (standalone doc)
    if len(parts) == 3 and parts[0] == "d":
        return ExtractedMention(type="document", slug=parts[2], url=url, label=label)

    # /d/{creator-slug}/{corpus-slug}/{doc-slug}  (doc-in-corpus)
    if len(parts) == 4 and parts[0] == "d":
        return ExtractedMention(
            type="document",
            slug=parts[3],
            corpus_slug=parts[2],
            url=url,
            label=label,
        )

    return None


def extract_mentions(markdown: str | None) -> list[ExtractedMention]:
    """Extract every supported mention from a markdown body.

    Returns mentions in document order. Duplicates by `url` are removed
    (first occurrence wins). Pure function: no DB, no permissions.
    """
    if not markdown:
        return []

    seen_urls: set[str] = set()
    # Secondary index keyed by ``(type, slug, corpus_slug)`` so the legacy
    # text patterns can deduplicate against the markdown-link results in
    # O(1) instead of an O(n) scan over ``out`` (the previous ``any(...)``
    # check was O(n^2) overall for messages with many corpus/document
    # mentions). ``corpus_slug`` is included so a corpus-scoped doc and a
    # standalone doc with the same slug remain distinct entries.
    seen_keys: set[tuple[str, str | None, str | None]] = set()
    out: list[ExtractedMention] = []

    def _key(m: ExtractedMention) -> tuple[str, str | None, str | None]:
        return (m.type, m.slug, m.corpus_slug)

    def _append(m: ExtractedMention) -> None:
        seen_urls.add(m.url)
        seen_keys.add(_key(m))
        out.append(m)

    # Markdown links
    for match in _LINK_RE.finditer(markdown):
        label, url = match.group(1), match.group(2)
        if url in seen_urls:
            continue
        m = _classify_url(url, label)
        if m is None:
            continue
        _append(m)

    # Legacy text patterns (corpus-scoped doc first to win over its sub-parts)
    for match in _LEGACY_CORPUS_DOC_RE.finditer(markdown):
        synthetic_url = f"/d/_/{match.group(1)}/{match.group(2)}"
        if synthetic_url in seen_urls:
            continue
        _append(
            ExtractedMention(
                type="document",
                slug=match.group(2),
                corpus_slug=match.group(1),
                url=synthetic_url,
                label=match.group(0),
            )
        )

    for match in _LEGACY_CORPUS_RE.finditer(markdown):
        synthetic_url = f"/c/_/{match.group(1)}"
        if synthetic_url in seen_urls or ("corpus", match.group(1), None) in seen_keys:
            continue
        _append(
            ExtractedMention(
                type="corpus",
                slug=match.group(1),
                url=synthetic_url,
                label=match.group(0),
            )
        )

    for match in _LEGACY_DOCUMENT_RE.finditer(markdown):
        synthetic_url = f"/d/_/{match.group(1)}"
        if (
            synthetic_url in seen_urls
            or (
                "document",
                match.group(1),
                None,
            )
            in seen_keys
        ):
            continue
        _append(
            ExtractedMention(
                type="document",
                slug=match.group(1),
                url=synthetic_url,
                label=match.group(0),
            )
        )

    return out


def extract_agent_mentions(markdown: str | None) -> list[ExtractedMention]:
    """Convenience filter: return only mentions where type == 'agent'."""
    return [m for m in extract_mentions(markdown) if m.type == "agent"]
