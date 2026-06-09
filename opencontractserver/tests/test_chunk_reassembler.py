"""Tests for the incremental ChunkReassembler."""

from typing import Optional

from django.test import TestCase

from opencontractserver.pipeline.base.chunk_reassembler import ChunkReassembler
from opencontractserver.tests.test_chunked_parser import _make_chunk_result
from opencontractserver.types.dicts import OpenContractDocExport


class TestChunkReassembler(TestCase):
    def test_incremental_matches_contiguous_indices(self):
        r = ChunkReassembler()
        r.add_chunk(_make_chunk_result(num_pages=2), page_offset=0, chunk_index=0)
        r.add_chunk(_make_chunk_result(num_pages=2), page_offset=2, chunk_index=1)
        r.add_chunk(_make_chunk_result(num_pages=2), page_offset=4, chunk_index=2)
        result = r.finalize()
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2, 3, 4, 5])
        self.assertEqual(result["page_count"], 6)

    def test_ids_prefixed_per_chunk_index(self):
        r = ChunkReassembler()
        r.add_chunk(_make_chunk_result(), page_offset=0, chunk_index=0)
        r.add_chunk(_make_chunk_result(), page_offset=2, chunk_index=1)
        ids = [a["id"] for a in r.finalize()["labelled_text"]]
        self.assertEqual(ids, ["c0_ann-1", "c1_ann-1"])

    def test_finalize_on_empty_raises(self):
        with self.assertRaises(ValueError):
            ChunkReassembler().finalize()


# ======================================================================
# Overlap dedup + cross-boundary re-linking (issue #1961)
# ======================================================================


def _page(local_index: int) -> dict:
    """A single PAWLs page with one token, local 0-based index."""
    return {
        "page": {"width": 612, "height": 792, "index": local_index},
        "tokens": [
            {"x": 10, "y": 10, "width": 50, "height": 12, "text": f"tok_{local_index}"}
        ],
    }


def _ann(
    ann_id: str,
    label: str,
    local_pages: list[int],
    top: int,
    tokens: Optional[list[int]] = None,
    parent_id: Optional[str] = None,
) -> dict:
    """Build a (possibly multi-page) v1 annotation with deterministic geometry.

    ``top`` seeds the bounding box so two copies of the *same* structure (same
    label/pages/top) hash to the same dedup signature once offset into global
    space, while distinct structures do not collide.
    """
    tokens = tokens if tokens is not None else [0]
    annotation_json = {
        str(p): {
            "bounds": {"top": top, "left": 0, "right": 10, "bottom": top + 1},
            "tokensJsons": [{"pageIndex": p, "tokenIndex": t} for t in tokens],
            "rawText": f"raw_{ann_id}",
        }
        for p in local_pages
    }
    return {
        "id": ann_id,
        "annotationLabel": label,
        "rawText": f"raw_{ann_id}",
        "page": local_pages[0],
        "annotation_json": annotation_json,
        "parent_id": parent_id,
        "annotation_type": "TOKEN_LABEL",
        "structural": True,
    }


def _chunk(
    num_pages: int,
    annotations: list,
    relationships: Optional[list] = None,
) -> OpenContractDocExport:
    pawls: list = [_page(i) for i in range(num_pages)]
    return {
        "title": "Doc",
        "content": "c",
        "description": "d",
        "pawls_file_content": pawls,
        "page_count": num_pages,
        "doc_labels": [],
        "labelled_text": annotations,
        "relationships": relationships or [],
    }


class TestOverlapPageDedup(TestCase):
    def test_overlapping_pages_deduped_by_global_index(self):
        r = ChunkReassembler()
        # chunk0 parses global pages 0..3, chunk1 parses global 2..5 (overlap 2,3).
        r.add_chunk(_chunk(4, [_ann("a", "P", [0], 0)]), page_offset=0, chunk_index=0)
        r.add_chunk(_chunk(4, [_ann("a", "P", [0], 4)]), page_offset=2, chunk_index=1)
        result = r.finalize()
        indices = [p["page"]["index"] for p in result["pawls_file_content"]]
        self.assertEqual(indices, [0, 1, 2, 3, 4, 5])
        self.assertEqual(result["page_count"], 6)

    def test_kept_page_is_first_occurrence(self):
        r = ChunkReassembler()
        r.add_chunk(_chunk(2, []), page_offset=0, chunk_index=0)
        r.add_chunk(_chunk(2, []), page_offset=1, chunk_index=1)
        pages = r.finalize()["pawls_file_content"]
        # Global page 1 is contributed by both chunks; the first chunk wins.
        page1 = next(p for p in pages if p["page"]["index"] == 1)
        self.assertEqual(page1["tokens"][0]["text"], "tok_1")  # chunk0's local page 1


class TestOverlapAnnotationDedup(TestCase):
    def test_duplicate_annotation_in_overlap_zone_collapses(self):
        # The same structure appears on global page 2 in both chunks.
        r = ChunkReassembler()
        r.add_chunk(
            _chunk(3, [_ann("dup", "Para", [2], top=20)]),
            page_offset=0,
            chunk_index=0,
        )
        r.add_chunk(
            _chunk(3, [_ann("dup", "Para", [0], top=20)]),
            page_offset=2,
            chunk_index=1,
        )
        anns = r.finalize()["labelled_text"]
        self.assertEqual(len(anns), 1)
        # First chunk's copy is canonical.
        self.assertEqual(anns[0]["id"], "c0_dup")
        self.assertEqual(anns[0]["page"], 2)

    def test_distinct_annotations_not_collapsed(self):
        r = ChunkReassembler()
        r.add_chunk(
            _chunk(3, [_ann("x", "Para", [2], top=20)]),
            page_offset=0,
            chunk_index=0,
        )
        # Same page but different label -> different signature -> both survive.
        r.add_chunk(
            _chunk(3, [_ann("y", "Heading", [0], top=20)]),
            page_offset=2,
            chunk_index=1,
        )
        anns = r.finalize()["labelled_text"]
        self.assertEqual({a["id"] for a in anns}, {"c0_x", "c1_y"})


class TestOverlapRelationshipRelink(TestCase):
    def test_cross_boundary_relationship_relinked_to_canonical(self):
        # Annotation B sits in the overlap zone (global page 2), authored by both
        # chunks. A relationship in chunk1 links A (chunk1-only) -> B; after
        # re-linking it must point at chunk0's canonical B, not chunk1's dropped
        # copy, and the duplicate relationship collapses.
        r = ChunkReassembler()
        r.add_chunk(
            _chunk(3, [_ann("B", "Para", [2], top=20)]),
            page_offset=0,
            chunk_index=0,
        )
        r.add_chunk(
            _chunk(
                3,
                [
                    _ann("B", "Para", [0], top=20),  # duplicate of c0_B
                    _ann("A", "Para", [1], top=30),  # global page 3, unique
                ],
                relationships=[
                    {
                        "id": "rel",
                        "relationshipLabel": "next",
                        "source_annotation_ids": ["A"],
                        "target_annotation_ids": ["B"],
                        "structural": True,
                    }
                ],
            ),
            page_offset=2,
            chunk_index=1,
        )
        result = r.finalize()
        ann_ids = {a["id"] for a in result["labelled_text"]}
        self.assertEqual(ann_ids, {"c0_B", "c1_A"})

        rels = result["relationships"]
        self.assertEqual(len(rels), 1)
        rel = rels[0]
        self.assertEqual(rel["source_annotation_ids"], ["c1_A"])
        # Re-linked from the dropped c1_B onto the canonical c0_B.
        self.assertEqual(rel["target_annotation_ids"], ["c0_B"])
        # And every endpoint resolves to a surviving annotation (no orphans).
        for ref in rel["source_annotation_ids"] + rel["target_annotation_ids"]:
            self.assertIn(ref, ann_ids)

    def test_duplicate_relationship_in_overlap_collapses(self):
        # A relationship fully inside the overlap zone is authored by both chunks
        # and must collapse to a single edge after re-linking.
        rel = {
            "id": "r",
            "relationshipLabel": "next",
            "source_annotation_ids": ["B"],
            "target_annotation_ids": ["C"],
            "structural": True,
        }
        r = ChunkReassembler()
        r.add_chunk(
            _chunk(
                4,
                [_ann("B", "P", [2], top=20), _ann("C", "P", [3], top=30)],
                relationships=[dict(rel)],
            ),
            page_offset=0,
            chunk_index=0,
        )
        r.add_chunk(
            _chunk(
                4,
                [_ann("B", "P", [0], top=20), _ann("C", "P", [1], top=30)],
                relationships=[dict(rel)],
            ),
            page_offset=2,
            chunk_index=1,
        )
        result = r.finalize()
        self.assertEqual(len(result["relationships"]), 1)
        self.assertEqual(result["relationships"][0]["source_annotation_ids"], ["c0_B"])
        self.assertEqual(result["relationships"][0]["target_annotation_ids"], ["c0_C"])


class TestOverlapParentRelink(TestCase):
    def test_cross_boundary_parent_id_relinked(self):
        # Parent P lives in the overlap zone (global page 2). The child in chunk1
        # references its own (dropped) copy of P; re-linking must re-anchor it to
        # chunk0's canonical P.
        r = ChunkReassembler()
        r.add_chunk(
            _chunk(3, [_ann("P", "Section", [2], top=20)]),
            page_offset=0,
            chunk_index=0,
        )
        r.add_chunk(
            _chunk(
                3,
                [
                    _ann("P", "Section", [0], top=20),  # duplicate of c0_P
                    _ann("child", "Para", [1], top=30, parent_id="P"),
                ],
            ),
            page_offset=2,
            chunk_index=1,
        )
        result = r.finalize()
        child = next(a for a in result["labelled_text"] if a["id"] == "c1_child")
        self.assertEqual(child["parent_id"], "c0_P")
        ann_ids = {a["id"] for a in result["labelled_text"]}
        self.assertIn(child["parent_id"], ann_ids)


class TestResidualOrphansNeverFatal(TestCase):
    def test_unresolved_reference_logs_but_does_not_raise(self):
        # A reference whose target never appears in any chunk (overlap too small
        # for the spanning structure) survives as an orphan but is non-fatal.
        r = ChunkReassembler()
        r.add_chunk(
            _chunk(2, [_ann("child", "Para", [0], top=10, parent_id="missing")]),
            page_offset=0,
            chunk_index=0,
        )
        with self.assertLogs(
            "opencontractserver.pipeline.base.chunk_reassembler", level="WARNING"
        ) as cm:
            result = r.finalize()
        # The annotation is preserved; the dangling parent_id is logged, not fatal.
        self.assertEqual(len(result["labelled_text"]), 1)
        self.assertEqual(result["labelled_text"][0]["parent_id"], "c0_missing")
        self.assertTrue(any("residual" in m.lower() for m in cm.output))
