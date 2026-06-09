"""Canonical "intelligence block" for a corpus ``Readme.CAML`` article.

Every corpus's ``Readme.CAML`` should compose the live corpus-intelligence
overview by default — the design goal is an *extremely structural default with
narrative override*: the article ships with the overview embedded, and an author
may edit the prose around it without ever losing the overview.

The overview is rendered by three CAML component embeds registered in the
frontend (``frontend/src/utils/camlComponentRegistry.ts``): ``insight-panel``,
``document-graph``, and ``ask-across-docs``. Each embed fetches its data live at
view time, so the block below is *fixed text* — it never goes stale and never
needs regeneration when corpus data changes.

This module is pure string transforms (no ORM access) so it can be called safely
from services, signal handlers, management commands, data migrations, and tests
— mirroring the no-Django-import discipline of ``caml_authoring.py`` and the
string helpers in ``corpuses/services/description_cache.py``.
"""

from __future__ import annotations

# The three component markers the frontend registry recognises. Used both to
# build the block and to detect (in ``ensure_intelligence_block``) whether an
# existing CAML source already embeds the overview. Kept as a tuple so the
# membership test below stays a single source of truth — adding/removing a
# marker here updates detection automatically.
CAML_INTELLIGENCE_MARKERS: tuple[str, ...] = (
    "[component:insight-panel]",
    "[component:document-graph]",
    "[component:ask-across-docs]",
)

# The canonical intelligence block. This exact text is the contract with the
# frontend CAML renderer: each ``::: oc-component`` fence wrapping a
# ``[component:...]`` marker is replaced by the live component at view time.
# Defined as a module constant so the default-README builder, the
# ensure-block helper, and the backfill command all emit byte-identical text.
CAML_INTELLIGENCE_BLOCK = """\
## At a glance

::: oc-component
[component:insight-panel]
:::

## How these documents interconnect

::: oc-component
[component:document-graph]
:::

## Ask across the collection

::: oc-component
[component:ask-across-docs]
:::"""


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


def build_default_readme_caml(
    title: str | None,
    description: str | None = None,
) -> str:
    """Build the deterministic structural ``Readme.CAML`` for a new corpus.

    The non-LLM default: a title heading, an optional description paragraph, and
    the canonical intelligence block. Produced when a corpus is created without
    LLM auto-branding (or as the structural seed a backfill writes where no
    article exists) so every corpus composes the overview out of the box.

    *title* / *description* are corpus metadata. They are interpolated as plain
    markdown — callers that surface untrusted content should sanitise upstream;
    here they originate from the corpus row's own fields.
    """
    heading = (title or "Untitled collection").strip() or "Untitled collection"
    parts = [f"# {heading}"]
    desc = (description or "").strip()
    if desc:
        parts.append(desc)
    parts.append(CAML_INTELLIGENCE_BLOCK)
    return "\n\n".join(parts)
