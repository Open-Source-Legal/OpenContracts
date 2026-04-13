"""
Unit tests for the text alignment utility.

These are pure Python tests with no Django dependencies.
"""

from django.test import SimpleTestCase

from opencontractserver.utils.text_alignment import (
    MatchType,
    align_text_to_document,
)


class TestAlignTextToDocument(SimpleTestCase):
    """Tests for align_text_to_document()."""

    def test_exact_match_single(self):
        doc = "The quick brown fox jumps over the lazy dog."
        results = align_text_to_document(["brown fox"], doc)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.match_type, MatchType.EXACT)
        self.assertEqual(r.match_quality, 1.0)
        self.assertEqual(r.char_start, 10)
        self.assertEqual(r.char_end, 19)
        self.assertEqual(r.matched_text, "brown fox")

    def test_exact_match_multiple_queries(self):
        doc = "Alice signed the contract on January 1, 2024. Bob witnessed."
        results = align_text_to_document(
            ["Alice", "January 1, 2024", "Bob witnessed"],
            doc,
            min_query_length=3,
        )
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.match_type == MatchType.EXACT for r in results))

    def test_normalized_match_whitespace(self):
        """LLMs often collapse multiple spaces/newlines into one.

        Verifies that doc_text[char_start:char_end] contains the full
        expected content, including when a normalized match ends on
        collapsed whitespace boundaries.
        """
        doc = "Section 4.2:\n  Indemnification\n  and Hold Harmless"
        query = "Section 4.2: Indemnification and Hold Harmless"
        results = align_text_to_document([query], doc)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertIn(r.match_type, (MatchType.EXACT, MatchType.NORMALIZED))
        self.assertGreater(r.match_quality, 0.8)
        # The matched slice must cover the full original content
        matched_slice = doc[r.char_start : r.char_end]
        self.assertEqual(matched_slice, r.matched_text)
        self.assertIn("Section 4.2:", matched_slice)
        self.assertIn("Hold Harmless", matched_slice)

    def test_normalized_match_case(self):
        """LLMs sometimes change case."""
        doc = "ACME CORPORATION hereby agrees to the following terms."
        query = "Acme Corporation hereby agrees"
        results = align_text_to_document([query], doc)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].match_type, MatchType.NORMALIZED)

    def test_fuzzy_match_minor_differences(self):
        """Small wording differences should still match."""
        doc = "The Seller shall deliver the goods within thirty (30) calendar days."
        query = "The Seller shall deliver goods within thirty (30) calendar days."
        results = align_text_to_document(
            [query], doc, fuzzy_threshold=0.75, enable_fuzzy=True
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].match_type, MatchType.FUZZY)
        self.assertGreater(results[0].match_quality, 0.75)

    def test_no_match_returns_empty(self):
        doc = "This is a document about penguins."
        results = align_text_to_document(
            ["completely unrelated text that does not appear"], doc
        )
        self.assertEqual(len(results), 0)

    def test_short_queries_skipped(self):
        """Queries shorter than min_query_length are skipped."""
        doc = "The cat sat on the mat."
        results = align_text_to_document(["cat"], doc, min_query_length=4)
        self.assertEqual(len(results), 0)

    def test_empty_document(self):
        results = align_text_to_document(["something"], "")
        self.assertEqual(len(results), 0)

    def test_empty_queries(self):
        results = align_text_to_document([], "Some document text.")
        self.assertEqual(len(results), 0)

    def test_fuzzy_disabled(self):
        """With fuzzy disabled, only exact and normalized should match."""
        doc = "The Seller shall deliver the goods within thirty days."
        query = "Seller shall deliver goods within thirty days."
        # This has a word removed ("the") so exact/normalized won't match
        results = align_text_to_document([query], doc, enable_fuzzy=False)
        # May or may not match via normalized depending on the diff —
        # but should not use fuzzy
        for r in results:
            self.assertNotEqual(r.match_type, MatchType.FUZZY)

    def test_multiple_occurrences_returns_first(self):
        """align_text_to_document returns the first occurrence."""
        doc = "Party A and Party B agree. Party A shall pay Party B."
        results = align_text_to_document(["Party"], doc, min_query_length=3)
        # Should find first occurrence
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].char_start, 0)

    def test_result_is_frozen_dataclass(self):
        doc = "Hello world example text here."
        results = align_text_to_document(["example text"], doc)
        self.assertEqual(len(results), 1)
        with self.assertRaises(AttributeError):
            results[0].char_start = 999  # type: ignore[misc]

    def test_long_document_performance(self):
        """Ensure alignment doesn't hang on moderately large documents."""
        # 100KB document
        doc = "The quick brown fox. " * 5000
        results = align_text_to_document(
            ["quick brown fox"],
            doc,
            enable_fuzzy=False,  # Skip fuzzy for speed
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].match_type, MatchType.EXACT)

    def test_fuzzy_skipped_for_large_documents(self):
        """Fuzzy matching should be skipped for documents exceeding the size limit."""
        from opencontractserver.constants.extraction import MAX_DOC_LENGTH_FOR_FUZZY

        # Create a document just over the threshold
        doc = "x" * (MAX_DOC_LENGTH_FOR_FUZZY + 1)
        # This query won't match exactly or normalized, so fuzzy is the only path
        results = align_text_to_document(
            ["something completely different here"],
            doc,
            enable_fuzzy=True,
            fuzzy_threshold=0.1,  # Very low threshold to ensure fuzzy would match
        )
        # Should return empty because fuzzy is skipped for large docs
        self.assertEqual(len(results), 0)


class TestAlignTextContract(SimpleTestCase):
    """Tests with realistic contract-like text."""

    SAMPLE_CONTRACT = (
        "ASSET PURCHASE AGREEMENT\n\n"
        'This Asset Purchase Agreement (this "Agreement") is entered into as of '
        "March 15, 2024, by and between Acme Holdings, Inc., a Delaware corporation "
        '("Seller"), and Global Acquisitions LLC, a New York limited liability '
        'company ("Buyer").\n\n'
        "ARTICLE I - DEFINITIONS\n\n"
        '1.1 "Purchased Assets" means all of the assets, properties, and rights '
        "of every type and description, real and personal, tangible and intangible, "
        "owned by Seller.\n\n"
        '1.2 "Purchase Price" means the sum of Fifty Million Dollars '
        "($50,000,000.00), subject to adjustment as set forth in Section 2.3.\n\n"
        "ARTICLE II - PURCHASE AND SALE\n\n"
        "2.1 Purchase and Sale. Subject to the terms and conditions of this Agreement, "
        "at the Closing, Seller shall sell, convey, transfer, assign and deliver to "
        "Buyer, and Buyer shall purchase from Seller, free and clear of all "
        "Encumbrances, all of Seller's right, title and interest in and to the "
        "Purchased Assets.\n\n"
        "2.2 Closing Date. The closing of the transactions contemplated by this "
        'Agreement (the "Closing") shall take place on April 30, 2024.'
    )

    def test_extract_party_names(self):
        results = align_text_to_document(
            ["Acme Holdings, Inc.", "Global Acquisitions LLC"],
            self.SAMPLE_CONTRACT,
        )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.match_type == MatchType.EXACT for r in results))

    def test_extract_dates(self):
        results = align_text_to_document(
            ["March 15, 2024", "April 30, 2024"],
            self.SAMPLE_CONTRACT,
        )
        self.assertEqual(len(results), 2)

    def test_extract_monetary_value(self):
        results = align_text_to_document(
            ["Fifty Million Dollars ($50,000,000.00)"],
            self.SAMPLE_CONTRACT,
        )
        self.assertEqual(len(results), 1)

    def test_extract_clause_text(self):
        clause = (
            "Seller shall sell, convey, transfer, assign and deliver to "
            "Buyer, and Buyer shall purchase from Seller"
        )
        results = align_text_to_document([clause], self.SAMPLE_CONTRACT)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].match_type, MatchType.EXACT)

    def test_llm_reformatted_whitespace(self):
        """LLM might return clause with single spaces where doc has newlines."""
        query = "ARTICLE II - PURCHASE AND SALE 2.1 Purchase and Sale."
        results = align_text_to_document([query], self.SAMPLE_CONTRACT)
        self.assertEqual(len(results), 1)
        self.assertIn(results[0].match_type, (MatchType.NORMALIZED, MatchType.FUZZY))
