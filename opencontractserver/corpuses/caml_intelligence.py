"""Canonical "intelligence block" for a corpus ``Readme.CAML`` article.

Every corpus's ``Readme.CAML`` should compose the live corpus-intelligence
overview by default — the design goal is an *extremely structural default with
narrative override*: the article ships with the overview embedded, and an author
may edit the prose around it without ever losing the overview.

The overview is rendered by four CAML component embeds registered in the
frontend (``frontend/src/utils/camlComponentRegistry.ts``): ``insight-panel``,
``governance-graph``, ``document-graph``, and ``ask-across-docs``. Each embed
fetches its data live at view time, so the block below is *fixed text* — it
never goes stale and never needs regeneration when corpus data changes. The
governance-graph embed doubles as the reference web's entry point: on an
unmapped corpus it renders the "Map the reference web" bootstrap CTA.

This module is pure string transforms (no ORM access) so it can be called safely
from services, signal handlers, management commands, data migrations, and tests
— mirroring the no-Django-import discipline of ``caml_authoring.py`` and the
string helpers in ``corpuses/services/description_cache.py``.
"""

from __future__ import annotations

import re

# The component markers the frontend registry recognises. Used both to
# build the block and to detect (in ``ensure_intelligence_block``) whether an
# existing CAML source already embeds the overview. Kept as a tuple so the
# membership test below stays a single source of truth — adding/removing a
# marker here updates detection automatically.
CAML_INTELLIGENCE_MARKERS: tuple[str, ...] = (
    "[component:insight-panel]",
    "[component:collection-datastory]",
    "[component:governance-graph]",
    "[component:document-graph]",
    "[component:ask-across-docs]",
)

# The canonical intelligence block. This exact text is the contract with the
# frontend CAML renderer: each ``::: oc-component`` fence wrapping a
# ``[component:...]`` marker is replaced by the live component at view time.
# Defined as a module constant so the default-README builder, the
# ensure-block helper, and the backfill command all emit byte-identical text.
CAML_INTELLIGENCE_BLOCK = """\
::: oc-component
[component:insight-panel]
:::

::: oc-component
[component:collection-datastory]
:::

::: oc-component
[component:governance-graph]
:::

::: oc-component
[component:document-graph]
:::

::: oc-component
[component:ask-across-docs]
:::"""


#: ``[component:name key=value key2=value2]`` — the prop syntax the frontend
#: registry already uses. Values are unquoted and whitespace-delimited, which
#: is what an author writing a marker by hand will produce.
#: Named-group variant used to READ a marker's props. Deliberately a separate
#: pattern from ``_COMPONENT_MARKER_RE`` below, which strips markers out of
#: user-controlled metadata — that one must stay a blunt "remove any marker"
#: and must not grow groups or an author-supplied prop could survive stripping.
_COMPONENT_PROPS_RE = re.compile(
    r"\[component:(?P<name>[a-z0-9-]+)(?P<props>[^\]]*)\]", re.IGNORECASE
)
_PROP_RE = re.compile(r"(?P<key>[A-Za-z_][\w-]*)=(?P<value>\S+)")


def parse_component_props(
    caml_source: str | None, component: str
) -> dict[str, str] | None:
    """Props of the first ``[component:<component> ...]`` marker, or ``None``.

    A corpus's CAML article is where its author already describes what the
    corpus IS, which makes it the natural place to configure how the corpus is
    read — the alternative is a settings column nobody discovers. This reads
    the same marker syntax the frontend registry renders, so one marker can
    both configure the backend and display something to a reader.

    Returns ``None`` when the marker is absent and ``{}`` when it is present
    with no props; callers can tell "not configured" from "configured empty".
    """
    if not caml_source:
        return None
    for match in _COMPONENT_PROPS_RE.finditer(caml_source):
        if match.group("name").lower() != component.lower():
            continue
        return {
            m.group("key"): m.group("value")
            for m in _PROP_RE.finditer(match.group("props"))
        }
    return None


def has_intelligence_block(caml_source: str | None) -> bool:
    """Return ``True`` iff *any* of the three intelligence markers is present.

    Detection is intentionally lenient — a single marker counts as "the author
    has the overview" — so a partial/hand-tuned block (e.g. an author who kept
    only the graph) is never clobbered by a re-appended full block. The markers
    are the load-bearing tokens the renderer keys on; surrounding ``:::`` fences
    and headings may legitimately vary in author-edited articles.
    """
    if not caml_source:
        return False
    return any(marker in caml_source for marker in CAML_INTELLIGENCE_MARKERS)


def ensure_intelligence_block(caml_source: str | None) -> str:
    """Return *caml_source* with the intelligence block appended **iff absent**.

    Idempotent and narrative-preserving:

    * If any intelligence marker is already present, the source is returned
      unchanged (calling twice never duplicates the block).
    * Otherwise the canonical block is appended after the existing content,
      separated by a blank line, so author prose is preserved and the overview
      is composed below it.

    An empty/None source yields just the block (a bare structural article).
    """
    existing = caml_source or ""
    if has_intelligence_block(existing):
        return existing
    if not existing.strip():
        return CAML_INTELLIGENCE_BLOCK
    # Normalise the seam to exactly one blank line so the appended block renders
    # as its own section regardless of how the author's content terminated.
    return f"{existing.rstrip()}\n\n{CAML_INTELLIGENCE_BLOCK}"


# Directive syntax that must never survive metadata interpolation:
# ``[component:...]`` markers (the renderer would mount the named component)
# and ``:::``-prefixed lines (CAML/remark directive fences, which could open
# or close a container and re-scope everything after them).
_COMPONENT_MARKER_RE = re.compile(r"\[component:[^\]]*\]", re.IGNORECASE)
_DIRECTIVE_FENCE_LINE_RE = re.compile(r"^[ \t]*:{3,}.*$", re.MULTILINE)


def _strip_caml_directives(value: str) -> str:
    """Strip CAML directive syntax from interpolated corpus metadata.

    Corpus title/description are user-controlled. Interpolating them verbatim
    into the generated article would let a crafted value (e.g. a title
    containing ``::: oc-component\\n[component:...]\\n:::``) smuggle arbitrary
    component embeds or break the document's fence structure — and the backfill
    command feeds *every historical corpus* through this builder. The metadata
    is prose, never markup, so directive tokens are simply removed.
    """
    value = _COMPONENT_MARKER_RE.sub("", value)
    value = _DIRECTIVE_FENCE_LINE_RE.sub("", value)
    return value.strip()


def build_default_readme_caml(
    title: str | None,
    description: str | None = None,
) -> str:
    """Build the deterministic structural ``Readme.CAML`` for a new corpus.

    The non-LLM default: a title heading, an optional description paragraph, and
    the canonical intelligence block. Produced when a corpus is created without
    LLM auto-branding (or as the structural seed a backfill writes where no
    article exists) so every corpus composes the overview out of the box.

    *title* / *description* are corpus metadata — user-controlled, so CAML
    directive syntax is stripped via :func:`_strip_caml_directives` before
    interpolation. The title is additionally collapsed to a single line so a
    multi-line value cannot break out of the ``#`` heading.
    """
    heading = " ".join(_strip_caml_directives(title or "").split())
    heading = heading or "Untitled collection"
    parts = [f"# {heading}"]
    desc = _strip_caml_directives(description or "")
    if desc:
        parts.append(desc)
    parts.append(CAML_INTELLIGENCE_BLOCK)
    return "\n\n".join(parts)
