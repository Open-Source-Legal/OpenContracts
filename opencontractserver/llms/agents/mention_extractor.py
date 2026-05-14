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
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse

MentionType = Literal["agent", "user", "corpus", "document", "annotation"]

# Markdown link pattern: [label](url)
_LINK_RE = re.compile(r"\[([^\]]*)\]\((/[^)\s]+)\)")

# Legacy text patterns
_LEGACY_CORPUS_RE = re.compile(r"@corpus:([a-z0-9][-a-z0-9_]*)", re.IGNORECASE)
_LEGACY_DOCUMENT_RE = re.compile(r"@document:([a-z0-9][-a-z0-9_]*)", re.IGNORECASE)
_LEGACY_CORPUS_DOC_RE = re.compile(
    r"@corpus:([a-z0-9][-a-z0-9_]*)/document:([a-z0-9][-a-z0-9_]*)",
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
    # which covers both `/c/{corpus-slug}/agents/{slug}` and the longer
    # `/c/{creator-slug}/{corpus-slug}/agents/{slug}` form.
    if len(parts) >= 4 and parts[0] == "c" and parts[-2] == "agents":
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
    out: list[ExtractedMention] = []

    # Markdown links
    for match in _LINK_RE.finditer(markdown):
        label, url = match.group(1), match.group(2)
        if url in seen_urls:
            continue
        m = _classify_url(url, label)
        if m is None:
            continue
        seen_urls.add(url)
        out.append(m)

    # Legacy text patterns (corpus-scoped doc first to win over its sub-parts)
    for match in _LEGACY_CORPUS_DOC_RE.finditer(markdown):
        synthetic_url = f"/d/_/{match.group(1)}/{match.group(2)}"
        if synthetic_url in seen_urls:
            continue
        seen_urls.add(synthetic_url)
        out.append(
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
        if synthetic_url in seen_urls or any(
            m.type == "corpus" and m.slug == match.group(1) for m in out
        ):
            continue
        seen_urls.add(synthetic_url)
        out.append(
            ExtractedMention(
                type="corpus",
                slug=match.group(1),
                url=synthetic_url,
                label=match.group(0),
            )
        )

    for match in _LEGACY_DOCUMENT_RE.finditer(markdown):
        synthetic_url = f"/d/_/{match.group(1)}"
        if synthetic_url in seen_urls or any(
            m.type == "document" and m.slug == match.group(1) and m.corpus_slug is None
            for m in out
        ):
            continue
        seen_urls.add(synthetic_url)
        out.append(
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
