"""Iteration diff helpers for Extract.

Computes a cell-level diff between two iterations of the same Extract
series. Kept as plain functions so it can be reused from the GraphQL
resolver, the CLI, and tests without dragging Graphene into the import
graph.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract

# Status enum mirrored from ExtractDiffStatus in the GraphQL layer. Kept as
# plain strings so this module has no Graphene dependency.
DIFF_UNCHANGED = "UNCHANGED"
DIFF_CHANGED = "CHANGED"
DIFF_ONLY_IN_A = "ONLY_IN_A"
DIFF_ONLY_IN_B = "ONLY_IN_B"


@dataclass
class CellDiff:
    row_key: str
    column_key: str
    document: Document | None  # representative doc (prefers B)
    document_a: Document | None
    document_b: Document | None
    cell_a: Datacell | None
    cell_b: Datacell | None
    status: str
    column_config_changed: bool


def _cell_value(cell: Datacell | None) -> Any:
    """Effective value of a datacell — corrected_data wins, else data."""
    if cell is None:
        return None
    if cell.corrected_data is not None:
        return cell.corrected_data
    return cell.data


def _row_key(doc: Document) -> str:
    """Stable identifier across iterations for a logical document.

    Documents that share a ``version_tree_id`` represent the same logical
    document at different content versions, so the diff aligns them as one
    row even when the two iterations point at different version PKs.
    """
    if doc.version_tree_id is not None:
        return f"tree:{doc.version_tree_id}"
    return f"doc:{doc.pk}"


def _column_config_signature(col: Column) -> tuple:
    """Hashable signature of fields that meaningfully change extract behaviour.

    Two columns with the same signature should produce comparable cells. We
    deliberately leave name out so a rename alone doesn't show as a config
    change in the diff side panel.
    """
    return (
        col.query or "",
        col.match_text or "",
        col.must_contain_text or "",
        col.output_type or "",
        col.instructions or "",
        bool(col.extract_is_list),
        col.task_name or "",
        col.limit_to_label or "",
    )


def _index_cells(
    cells: Iterable[Datacell],
) -> dict[tuple[str, str], Datacell]:
    """Index cells by (row_key, column_name)."""
    by_key: dict[tuple[str, str], Datacell] = {}
    for cell in cells:
        if cell.document is None or cell.column is None:
            continue
        by_key[(_row_key(cell.document), cell.column.name)] = cell
    return by_key


def diff_extracts(
    extract_a: Extract,
    extract_b: Extract,
    *,
    cells_a: Iterable[Datacell],
    cells_b: Iterable[Datacell],
) -> list[CellDiff]:
    """Build the aligned cell-by-cell diff for two iterations.

    The caller supplies pre-permission-filtered cell iterables (typically
    from ``ExtractQueryOptimizer.get_extract_datacells``) so this helper
    stays free of permission concerns.
    """
    a_by_key = _index_cells(cells_a)
    b_by_key = _index_cells(cells_b)

    # Column config map keyed by name for the FIELDSET-axis annotation.
    a_col_sig = {
        col.name: _column_config_signature(col)
        for col in extract_a.fieldset.columns.all()
    }
    b_col_sig = {
        col.name: _column_config_signature(col)
        for col in extract_b.fieldset.columns.all()
    }

    keys = set(a_by_key) | set(b_by_key)
    results: list[CellDiff] = []
    for row_key, column_key in sorted(keys):
        cell_a = a_by_key.get((row_key, column_key))
        cell_b = b_by_key.get((row_key, column_key))

        if cell_a is None and cell_b is not None:
            status = DIFF_ONLY_IN_B
        elif cell_b is None and cell_a is not None:
            status = DIFF_ONLY_IN_A
        else:
            status = (
                DIFF_UNCHANGED
                if _cell_value(cell_a) == _cell_value(cell_b)
                else DIFF_CHANGED
            )

        # Pick a representative document — prefer B (the "new" iteration)
        # so the side panel shows the latest version metadata.
        doc = cell_b.document if cell_b else (cell_a.document if cell_a else None)

        column_changed = (
            column_key in a_col_sig
            and column_key in b_col_sig
            and a_col_sig[column_key] != b_col_sig[column_key]
        )

        results.append(
            CellDiff(
                row_key=row_key,
                column_key=column_key,
                document=doc,
                document_a=cell_a.document if cell_a else None,
                document_b=cell_b.document if cell_b else None,
                cell_a=cell_a,
                cell_b=cell_b,
                status=status,
                column_config_changed=column_changed,
            )
        )
    return results


def summarise(cells: Iterable[CellDiff]) -> dict[str, int]:
    """Count diffs by status — ready for ``ExtractDiffSummaryType``."""
    counts = {
        DIFF_UNCHANGED: 0,
        DIFF_CHANGED: 0,
        DIFF_ONLY_IN_A: 0,
        DIFF_ONLY_IN_B: 0,
    }
    total = 0
    for c in cells:
        counts[c.status] += 1
        total += 1
    return {
        "unchanged": counts[DIFF_UNCHANGED],
        "changed": counts[DIFF_CHANGED],
        "only_in_a": counts[DIFF_ONLY_IN_A],
        "only_in_b": counts[DIFF_ONLY_IN_B],
        "total": total,
    }
