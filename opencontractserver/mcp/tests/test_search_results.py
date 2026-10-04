"""Database-free regression tests for MCP block search result identity."""

from types import SimpleNamespace
from unittest import TestCase

from opencontractserver.constants.mcp import MCP_BLOCK_SNIPPET_MAX_CHARS
from opencontractserver.mcp.formatters import (
    _dedupe_search_hits,
    format_search_block,
)


class MCPBlockSearchIdentityTest(TestCase):
    def block(self, relationship_id, text, score=0.9):
        return SimpleNamespace(
            relationship=(
                SimpleNamespace(pk=relationship_id)
                if relationship_id is not None
                else None
            ),
            similarity_score=score,
            source_annotation_id=1,
            target_annotation_ids=[2],
            block_text=text,
            label_text="OC_SUBTREE_GROUP",
            document_id=1,
        )

    def format_blocks(self, *blocks):
        return [
            format_search_block(block, {1: ("contract", "Contract")})
            for block in blocks
        ]

    def test_distinct_blocks_with_identical_truncated_previews_survive(self):
        prefix = "x" * MCP_BLOCK_SNIPPET_MAX_CHARS
        hits = self.format_blocks(
            self.block(101, prefix + "Payment is due in thirty days."),
            self.block(102, prefix + "Payment is due in ninety days.", 0.8),
        )
        self.assertEqual(hits[0]["text"], hits[1]["text"])
        self.assertEqual(
            [hit["relationship_id"] for hit in _dedupe_search_hits(hits)],
            ["101", "102"],
        )

    def test_distinct_blocks_with_identical_full_text_survive(self):
        hits = self.format_blocks(
            self.block(101, "Repeated boilerplate"),
            self.block(102, "Repeated boilerplate", 0.8),
        )
        self.assertEqual(len(_dedupe_search_hits(hits)), 2)

    def test_repeated_relationship_keeps_first_ranked_hit(self):
        hits = self.format_blocks(
            self.block(101, "Same block", 0.9),
            self.block(101, "Same block", 0.8),
        )
        self.assertEqual(_dedupe_search_hits(hits), [hits[0]])

    def test_missing_relationship_ids_do_not_collapse_distinct_hits(self):
        hits = self.format_blocks(
            self.block(None, "Same preview"),
            self.block(None, "Same preview", 0.8),
        )
        self.assertIsNone(hits[0]["relationship_id"])
        self.assertEqual(len(_dedupe_search_hits(hits)), 2)

    def test_passage_identity_and_order_are_preserved(self):
        hits = [
            {"type": "passage", "annotation_id": "101", "similarity_score": 0.95},
            *self.format_blocks(self.block(101, "Block", 0.9)),
            {"type": "passage", "annotation_id": "101", "similarity_score": 0.8},
            {"type": "passage", "annotation_id": None, "text": "Same text"},
            {"type": "passage", "annotation_id": None, "text": "Same text"},
        ]
        self.assertEqual(_dedupe_search_hits(hits), [hits[i] for i in [0, 1, 3, 4]])
