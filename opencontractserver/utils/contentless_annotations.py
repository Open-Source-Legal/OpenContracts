"""Drop parser structural annotations that carry no content.

PDF text layers yield structural elements whose text is only whitespace (for
example NBSP runs), fill-in underscores, stray punctuation, or symbol-font
glyphs (bullets in the Unicode private-use area). Such an annotation is not
searchable, cannot be meaningfully embedded, and clutters the annotation
layer. The characters remain in the document's text layer; only the overlay
is dropped.

Only leaves are dropped: an annotation with children is structure, whatever
its own text. Pruning repeats until stable, so a container whose children
were all contentless is dropped too. Because nothing dropped ever has a kept
child, no re-parenting is needed.

Only parser output is filtered (see ``BaseParser.save_parsed_data``). Imported
and user-created annotations are kept as given.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping

from opencontractserver.constants.annotations import CONTENT_REGION_LABELS
from opencontractserver.types.dicts import (
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.types.enums import ContentModality


def has_word_characters(text: str | None) -> bool:
    """True when ``text`` contains at least one letter or digit in any script."""
    return any(ch.isalnum() for ch in text or "")


def is_contentless(
    text: str | None, label: str | None, modalities: Iterable[str] | None
) -> bool:
    """No letters or digits, no image content, and not a content-region label."""
    return (
        ContentModality.IMAGE.value not in (modalities or [])
        and (label or "").lower() not in CONTENT_REGION_LABELS
        and not has_word_characters(text)
    )


def prunable_leaves(
    candidates: Iterable[Hashable],
    children_of: Mapping[Hashable, Iterable[Hashable]],
) -> set[Hashable]:
    """Candidates that are, or become, leaves once prunable children go."""
    candidates = set(candidates)
    pruned: set[Hashable] = set()
    changed = True
    while changed:
        changed = False
        for node in candidates - pruned:
            if all(child in pruned for child in children_of.get(node, ())):
                pruned.add(node)
                changed = True
    return pruned


def contentless_structural_filter(
    annotations: Iterable[OpenContractsAnnotationPythonType],
    relationships: Iterable[OpenContractsRelationshipPythonType],
) -> tuple[
    list[OpenContractsAnnotationPythonType],
    list[OpenContractsRelationshipPythonType],
    int,
]:
    """Remove contentless structural leaves from a parser export.

    Relationships lose dropped endpoints, and a relationship left without a
    source or a target is removed. Returns ``(annotations, relationships,
    dropped_count)``; inputs are not mutated. IDs are compared as strings
    because exports mix ``int`` and ``str`` IDs (see ``import_annotations``).
    """
    annotations = list(annotations)
    relationships = list(relationships)

    def key(index: int) -> str:
        annotation_id = annotations[index].get("id")
        return f"#{index}" if annotation_id is None else str(annotation_id)

    index_of = {key(i): i for i in range(len(annotations))}
    children_of: dict[Hashable, list[Hashable]] = {}
    for i, annotation in enumerate(annotations):
        parent_id = annotation.get("parent_id")
        if parent_id is not None and str(parent_id) in index_of:
            children_of.setdefault(str(parent_id), []).append(key(i))
    candidates = [
        key(i)
        for i, a in enumerate(annotations)
        if a.get("structural")
        and is_contentless(
            a.get("rawText"), a.get("annotationLabel"), a.get("content_modalities")
        )
    ]
    dropped = prunable_leaves(candidates, children_of)
    if not dropped:
        return annotations, relationships, 0

    kept = [a for i, a in enumerate(annotations) if key(i) not in dropped]
    kept_relationships = []
    for relationship in relationships:
        sources = relationship.get("source_annotation_ids", [])
        targets = relationship.get("target_annotation_ids", [])
        kept_sources = [i for i in sources if str(i) not in dropped]
        kept_targets = [i for i in targets if str(i) not in dropped]
        if (sources and not kept_sources) or (targets and not kept_targets):
            continue
        if len(kept_sources) != len(sources) or len(kept_targets) != len(targets):
            relationship = relationship.copy()
            relationship["source_annotation_ids"] = kept_sources
            relationship["target_annotation_ids"] = kept_targets
        kept_relationships.append(relationship)

    return kept, kept_relationships, len(dropped)
