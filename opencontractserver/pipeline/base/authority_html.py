"""Small, dependency-free HTML helpers for deterministic authority providers.

The authority-pack loader imports provider modules by file path under synthetic
module names, so reusable parsing primitives must live in core rather than in a
pack sibling module.  These helpers deliberately stop at mechanical HTML/URL
normalization; publisher-specific classification remains in each provider.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

_SPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_NAMES = {"fbclid", "gclid"}


def normalize_html_text(value: str) -> str:
    """Collapse whitespace in one HTML-derived label deterministically."""

    return _SPACE_RE.sub(" ", value).strip()


@dataclass(frozen=True)
class AuthorityLink:
    """One normalized anchor found in publisher HTML."""

    url: str
    text: str
    raw_href: str
    attributes: tuple[tuple[str, str], ...] = ()

    def attribute(self, name: str, default: str | None = None) -> str | None:
        wanted = name.lower()
        for key, value in self.attributes:
            if key == wanted:
                return value
        return default


class _AuthorityHTMLParser(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }
    _HIDDEN_TAGS = {"noscript", "script", "style", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str, tuple[tuple[str, str], ...]]] = []
        self._active_href: str | None = None
        self._active_attrs: tuple[tuple[str, str], ...] = ()
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in self._HIDDEN_TAGS:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        if lowered in self._BLOCK_TAGS:
            self.text_parts.append("\n")
        normalized_attrs = tuple(
            sorted((key.lower(), value or "") for key, value in attrs)
        )
        if lowered == "a":
            # Malformed nested anchors are finalized rather than allowed to
            # merge into one misleading candidate.
            self._finish_link()
            attr_map = dict(normalized_attrs)
            self._active_href = attr_map.get("href", "").strip()
            self._active_attrs = normalized_attrs
            self._active_text = []
        elif lowered == "img" and self._active_href is not None:
            alt = dict(normalized_attrs).get("alt", "")
            if alt:
                self._active_text.append(alt)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._HIDDEN_TAGS:
            self.hidden_depth = max(0, self.hidden_depth - 1)
            return
        if self.hidden_depth:
            return
        if lowered == "a":
            self._finish_link()
        if lowered in self._BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        self.text_parts.append(data)
        if self._active_href is not None:
            self._active_text.append(data)

    def close(self) -> None:
        super().close()
        self._finish_link()

    def _finish_link(self) -> None:
        if self._active_href is None:
            return
        attr_map = dict(self._active_attrs)
        label = normalize_html_text("".join(self._active_text))
        if not label:
            label = normalize_html_text(
                attr_map.get("aria-label") or attr_map.get("title") or ""
            )
        self.links.append((self._active_href, label, self._active_attrs))
        self._active_href = None
        self._active_attrs = ()
        self._active_text = []


def canonicalize_authority_url(
    url: str,
    *,
    base_url: str | None = None,
    keep_fragment: bool = False,
) -> str:
    """Resolve and normalize one HTTP(S) source URL.

    Only known tracking query parameters are removed; publisher/session/document
    identifiers are preserved verbatim.  The safe HTTP layer remains responsible
    for the stronger scheme, host, DNS, and redirect policy at fetch time.
    """

    resolved = urljoin(base_url or "", (url or "").strip())
    split = urlsplit(resolved)
    if split.scheme.lower() not in {"http", "https"} or not split.netloc:
        raise ValueError(f"authority link is not an absolute HTTP(S) URL: {url!r}")
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_QUERY_NAMES
            and not key.lower().startswith(_TRACKING_QUERY_PREFIXES)
        ],
        doseq=True,
    )
    return urlunsplit(
        (
            split.scheme.lower(),
            split.netloc.lower(),
            split.path or "/",
            query,
            split.fragment if keep_fragment else "",
        )
    )


def extract_authority_links(
    html: str,
    *,
    base_url: str,
    keep_fragments: bool = True,
) -> list[AuthorityLink]:
    """Return deterministic, de-duplicated HTTP(S) links in document order."""

    parser = _AuthorityHTMLParser()
    parser.feed(html)
    parser.close()
    found: list[AuthorityLink] = []
    seen: set[tuple[str, str]] = set()
    for raw_href, text, attrs in parser.links:
        try:
            url = canonicalize_authority_url(
                raw_href,
                base_url=base_url,
                keep_fragment=keep_fragments,
            )
        except ValueError:
            # mailto:, javascript:, empty anchors, and malformed URLs are not
            # source-document candidates.
            continue
        identity = (url, text)
        if identity in seen:
            continue
        seen.add(identity)
        found.append(
            AuthorityLink(
                url=url,
                text=text,
                raw_href=raw_href,
                attributes=attrs,
            )
        )
    return found


def visible_html_text(html: str) -> str:
    """Extract visible HTML text while preserving useful block boundaries."""

    parser = _AuthorityHTMLParser()
    parser.feed(html)
    parser.close()
    lines = [
        normalize_html_text(line)
        for line in "".join(parser.text_parts)
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    ]
    compact: list[str] = []
    for line in lines:
        if line:
            compact.append(line)
        elif compact and compact[-1]:
            compact.append("")
    return "\n".join(compact).strip()


def extract_labeled_value(text: str, label: str) -> str | None:
    """Read ``Label: value`` or a label followed by a value on the next line."""

    wanted = normalize_html_text(label).rstrip(":").casefold()
    lines = [normalize_html_text(line) for line in text.splitlines()]
    for index, line in enumerate(lines):
        normalized = line.rstrip(":")
        folded = normalized.casefold()
        if folded == wanted:
            for following in lines[index + 1 :]:
                if following:
                    return following
            return None
        prefix = f"{wanted}:"
        if line.casefold().startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def stable_source_slug(value: str, *, max_length: int = 96) -> str:
    """Create a bounded stable key segment from a title, filename, or source id."""

    raw = normalize_html_text(value).casefold()
    filename = PurePosixPath(urlsplit(raw).path).name if "://" in raw else raw
    stem = PurePosixPath(filename).stem or filename
    slug = _SLUG_RE.sub("-", stem).strip("-") or "document"
    if len(slug) <= max_length:
        return slug
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{slug[: max_length - 13].rstrip('-')}-{digest}"
