"""Tests for the CAML article review agent tools.

Covers the three tools registered by ``opencontractserver.llms.tools.core_tools.caml_article``:

- ``aread_corpus_caml_article``       (read-only)
- ``apropose_caml_citation_match``    (read-only, semantic search mocked)
- ``aapply_caml_article_edit``        (write, approval-gated by registry flag)
"""

from __future__ import annotations

from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import (
    aapply_caml_article_edit,
    apropose_caml_citation_match,
    aread_corpus_caml_article,
)
from opencontractserver.llms.tools.core_tools.caml_article import (
    _apply_caml_article_edit,
    _read_corpus_caml_article,
)
from opencontractserver.llms.vector_stores.core_vector_stores import VectorSearchResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

# Sample CAML body covering: H1 heading, a prose paragraph WITHOUT a directive,
# a prose paragraph WITH a {{@cite}} directive, a list, and a fenced code block.
SAMPLE_CAML = """\
# Master Services Agreement Notes

Force majeure clauses were updated in 2023 to cover supply-chain shocks.

Liability is capped at twice the annual fee. {{@cite sentence}}

- bullet one
- bullet two

```python
print("not prose")
```
"""


def _create_caml_doc(corpus: Corpus, user, *, content: str = SAMPLE_CAML) -> Document:
    """Create a Readme.CAML Document linked to ``corpus`` with ``content``."""
    doc = Document.objects.create(
        title="Readme.CAML",
        creator=user,
        file_type=MARKDOWN_MIME_TYPE,
        # Bypass the post_save processing pipeline -- the signal handler
        # short-circuits when processing_started is already set.
        processing_started=timezone.now(),
        backend_lock=False,
    )
    doc.txt_extract_file.save(
        "Readme.CAML.md",
        ContentFile(content.encode("utf-8")),
        save=True,
    )
    linked_doc, _, _ = corpus.add_document(document=doc, user=user)
    return linked_doc


# --------------------------------------------------------------------------- #
# Tool 1: aread_corpus_caml_article                                           #
# --------------------------------------------------------------------------- #


class ReadCorpusCamlArticleTests(TransactionTestCase):
    """Tests for the read-only CAML article reviewer tool.

    Uses ``TransactionTestCase`` (not ``TestCase``) so the per-test fixture
    rows are committed and visible to the fresh DB connection that
    ``async_to_sync(...)`` opens for ``test_async_wrapper_returns_same_payload``
    — ``_db_sync_to_async`` runs with ``thread_sensitive=False`` so the
    standard ``TestCase`` transaction wrapper would hide the data from the
    helper thread.
    """

    owner: User
    outsider: User
    corpus: Corpus
    caml_doc: Document

    def setUp(self):
        # All fixtures are recreated per-test:
        #   * Users + corpus + file rows live in the per-test transaction
        #     so async helpers' fresh DB connection can see them.
        #   * Readme.CAML.md is bound to this test's MEDIA_ROOT (set by the
        #     autouse ``media_storage`` fixture in opencontractserver/conftest.py)
        #     so the file is reachable for every test in this class.
        self.owner = User.objects.create_user(username="caml_owner", password="pw")
        self.outsider = User.objects.create_user(
            username="caml_outsider", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="CAML Review Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.caml_doc = _create_caml_doc(self.corpus, self.owner)

    def test_returns_blocks_and_existing_directives(self):
        result = _read_corpus_caml_article(
            corpus_id=self.corpus.id, author_id=self.owner.id
        )
        self.assertEqual(result["corpus_id"], self.corpus.id)
        self.assertEqual(result["document_id"], self.caml_doc.id)
        self.assertEqual(result["title"], "Readme.CAML")
        self.assertEqual(result["content"], SAMPLE_CAML)

        # Block parsing: one block per blank-line-delimited segment.
        block_texts = [b["text"] for b in result["blocks"]]
        self.assertEqual(len(block_texts), 5)
        self.assertTrue(block_texts[0].startswith("# Master Services Agreement"))
        self.assertIn("Force majeure", block_texts[1])
        self.assertIn("{{@cite sentence}}", block_texts[2])

        # Directive extraction picks up the single existing {{@cite}}.
        cite_block = result["blocks"][2]
        self.assertTrue(cite_block["has_citation_directive"])
        self.assertEqual(len(cite_block["directives"]), 1)
        self.assertEqual(cite_block["directives"][0]["agent"], "cite")
        self.assertEqual(cite_block["directives"][0]["scope"], "sentence")
        self.assertEqual(result["total_directives"], 1)

    def test_candidate_indices_skip_heading_list_and_codefence(self):
        result = _read_corpus_caml_article(
            corpus_id=self.corpus.id, author_id=self.owner.id
        )
        candidate_indices = result["candidate_block_indices"]
        # The "Force majeure" block is the only prose without a {{@cite}}.
        self.assertEqual(candidate_indices, [1])

        # Heading, cited block, list, code fence -- none should be candidates.
        self.assertFalse(result["blocks"][0]["needs_citation_candidate"])  # heading
        self.assertFalse(result["blocks"][2]["needs_citation_candidate"])  # cited
        self.assertFalse(result["blocks"][3]["needs_citation_candidate"])  # list
        self.assertFalse(result["blocks"][4]["needs_citation_candidate"])  # code

    def test_outsider_without_access_raises(self):
        """IDOR: another user cannot enumerate or read a private corpus's CAML."""
        with self.assertRaises(ValueError) as ctx:
            _read_corpus_caml_article(
                corpus_id=self.corpus.id, author_id=self.outsider.id
            )
        self.assertIn("Readme.CAML", str(ctx.exception))

    def test_corpus_without_caml_raises(self):
        empty_corpus = Corpus.objects.create(title="No CAML Corpus", creator=self.owner)
        with self.assertRaises(ValueError) as ctx:
            _read_corpus_caml_article(
                corpus_id=empty_corpus.id, author_id=self.owner.id
            )
        self.assertIn("Readme.CAML", str(ctx.exception))

    def test_async_wrapper_returns_same_payload(self):
        """The public async function returns the same dict as the sync helper."""
        sync_result = _read_corpus_caml_article(
            corpus_id=self.corpus.id, author_id=self.owner.id
        )
        async_result = async_to_sync(aread_corpus_caml_article)(
            corpus_id=self.corpus.id, author_id=self.owner.id
        )
        self.assertEqual(async_result["document_id"], sync_result["document_id"])
        self.assertEqual(async_result["content"], sync_result["content"])
        self.assertEqual(
            async_result["candidate_block_indices"],
            sync_result["candidate_block_indices"],
        )


# --------------------------------------------------------------------------- #
# Tool 2: apropose_caml_citation_match                                        #
# --------------------------------------------------------------------------- #


class ProposeCamlCitationMatchTests(TestCase):
    """Tests for the citation candidate proposal tool.

    The vector store's ``async_search`` is patched so we don't depend on a
    configured embedder -- we only need to verify the tool's adapter logic
    (shape, capping, error handling).
    """

    owner: User
    corpus: Corpus
    doc: Document
    label: AnnotationLabel
    annotation: Annotation

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="propose_owner", password="pw")
        cls.corpus = Corpus.objects.create(
            title="Propose Corpus", creator=cls.owner, is_public=True
        )
        cls.doc = Document.objects.create(
            title="Source Doc",
            creator=cls.owner,
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        cls.doc, _, _ = cls.corpus.add_document(document=cls.doc, user=cls.owner)
        cls.label = AnnotationLabel.objects.create(
            text="Liability Cap", color="#abcdef", creator=cls.owner
        )
        cls.annotation = Annotation.objects.create(
            document=cls.doc,
            corpus=cls.corpus,
            creator=cls.owner,
            raw_text="Liability is capped at twice the annual fee.",
            annotation_label=cls.label,
            page=3,
            is_public=True,
        )

    def _patch_async_search(self, results):
        """Return a context manager patching ``async_search`` to return ``results``."""

        async def _fake_async_search(self, query):
            return list(results)

        return patch(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore.async_search",
            new=_fake_async_search,
        )

    def test_returns_ranked_candidates(self):
        results = [
            VectorSearchResult(annotation=self.annotation, similarity_score=0.83)
        ]
        with self._patch_async_search(results):
            candidates = async_to_sync(apropose_caml_citation_match)(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                query_text="Liability cap is twice the annual fee.",
            )
        self.assertEqual(len(candidates), 1)
        cand = candidates[0]
        self.assertEqual(cand["annotation_id"], self.annotation.id)
        self.assertEqual(cand["raw_text"], self.annotation.raw_text)
        self.assertEqual(cand["label_text"], "Liability Cap")
        self.assertEqual(cand["label_color"], "#abcdef")
        self.assertEqual(cand["document_id"], self.doc.id)
        self.assertEqual(cand["document_title"], "Source Doc")
        self.assertEqual(cand["corpus_id"], self.corpus.id)
        self.assertEqual(cand["page"], 3)
        self.assertAlmostEqual(cand["similarity_score"], 0.83)

    def test_caps_limit_at_25(self):
        """``limit`` requests above 25 are capped to keep tool output bounded."""
        captured = {}

        async def _capture_query(self, query):
            captured["top_k"] = query.similarity_top_k
            return []

        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore.async_search",
            new=_capture_query,
        ):
            async_to_sync(apropose_caml_citation_match)(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                query_text="anything",
                limit=999,
            )
        self.assertEqual(captured["top_k"], 25)

    def test_empty_query_raises(self):
        with self.assertRaises(ValueError):
            async_to_sync(apropose_caml_citation_match)(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                query_text="   ",
            )

    def test_empty_results_returns_empty_list(self):
        with self._patch_async_search([]):
            candidates = async_to_sync(apropose_caml_citation_match)(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                query_text="anything",
            )
        self.assertEqual(candidates, [])

    def test_search_failure_surfaces_as_value_error(self):
        async def _explode(self, query):
            raise RuntimeError("embedder offline")

        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore.async_search",
            new=_explode,
        ):
            with self.assertRaises(ValueError) as ctx:
                async_to_sync(apropose_caml_citation_match)(
                    corpus_id=self.corpus.id,
                    author_id=self.owner.id,
                    query_text="anything",
                )
        self.assertIn("Semantic search failed", str(ctx.exception))


# --------------------------------------------------------------------------- #
# Tool 3: aapply_caml_article_edit                                            #
# --------------------------------------------------------------------------- #


class ApplyCamlArticleEditTests(TransactionTestCase):
    """Tests for the approval-gated CAML article edit tool.

    Uses ``TransactionTestCase`` for the same reason as
    ``ReadCorpusCamlArticleTests`` — ``test_async_wrapper_persists_edit``
    routes through ``_db_sync_to_async`` (``thread_sensitive=False``), so
    the helper thread's fresh DB connection only sees committed data.
    """

    owner: User
    editor: User
    outsider: User
    superuser: User

    def setUp(self):
        # Recreate everything per test: users + corpus + Readme.CAML.md.
        # File mutations don't leak between cases, and the per-test rows
        # are committed in time for any async path to see them.
        self.owner = User.objects.create_user(username="apply_owner", password="pw")
        self.editor = User.objects.create_user(username="apply_editor", password="pw")
        self.outsider = User.objects.create_user(
            username="apply_outsider", password="pw"
        )
        self.superuser = User.objects.create_user(
            username="apply_super", password="pw", is_superuser=True
        )
        self.corpus = Corpus.objects.create(
            title="Apply Corpus", creator=self.owner, is_public=False
        )
        self.caml_doc = _create_caml_doc(self.corpus, self.owner)

    def _read_caml_body(self) -> str:
        self.caml_doc.refresh_from_db()
        with self.caml_doc.txt_extract_file.open("r") as fh:
            return fh.read()

    def test_replaces_single_occurrence(self):
        target = (
            "Force majeure clauses were updated in 2023 to cover supply-chain shocks."
        )
        replacement = (
            "Force majeure clauses were updated in 2023 to cover supply-chain "
            "shocks. {{@cite sentence}}"
        )
        result = _apply_caml_article_edit(
            corpus_id=self.corpus.id,
            author_id=self.owner.id,
            target_text=target,
            replacement_text=replacement,
            rationale="Add citation pointing at supply-chain annotation.",
        )
        self.assertTrue(result["applied"])
        self.assertEqual(result["document_id"], self.caml_doc.id)
        self.assertIn("{{@cite sentence}}", self._read_caml_body())

    def test_zero_matches_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                target_text="this string is not in the article",
                replacement_text="anything",
                rationale="r",
            )
        self.assertIn("not found", str(ctx.exception))

    def test_multiple_matches_raises(self):
        # Inject duplicate sentences so a single substring matches twice.
        duplicated_body = "Liability is capped.\n\nLiability is capped.\n"
        self.caml_doc.txt_extract_file.save(
            "Readme.CAML.md",
            ContentFile(duplicated_body.encode("utf-8")),
            save=True,
        )
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                target_text="Liability is capped.",
                replacement_text="Liability is capped. {{@cite sentence}}",
                rationale="r",
            )
        self.assertIn("matches", str(ctx.exception))
        # Body must be untouched on failure.
        self.assertEqual(self._read_caml_body(), duplicated_body)

    def test_identical_target_and_replacement_raises(self):
        with self.assertRaises(ValueError):
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                target_text="Liability is capped at twice the annual fee.",
                replacement_text="Liability is capped at twice the annual fee.",
                rationale="r",
            )

    def test_outsider_cannot_edit_private_corpus(self):
        """IDOR: an outsider gets the same opaque error as 'no CAML article'."""
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.outsider.id,
                target_text="Liability is capped",
                replacement_text="x",
                rationale="r",
            )
        self.assertIn("Readme.CAML", str(ctx.exception))

    def test_reader_without_update_perm_raises(self):
        """A user with READ but not UPDATE on the CAML doc cannot edit it."""
        # Make the corpus public so the editor can READ via visible_to_user,
        # but explicitly grant only READ on the CAML document.
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        # Re-link the existing CAML doc into the now-public corpus already
        # implicitly; just need to mark the doc itself public/readable.
        self.caml_doc.is_public = True
        self.caml_doc.save(update_fields=["is_public"])
        set_permissions_for_obj_to_user(
            self.editor, self.caml_doc, [PermissionTypes.READ]
        )

        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.editor.id,
                target_text="Liability is capped at twice the annual fee.",
                replacement_text=(
                    "Liability is capped at twice the annual fee. {{@cite sentence}}"
                ),
                rationale="r",
            )
        self.assertIn("cannot modify", str(ctx.exception))

    def test_superuser_can_edit_any_corpus(self):
        """Superusers bypass guardian checks (matches existing tool conventions)."""
        target = "Liability is capped at twice the annual fee. {{@cite sentence}}"
        replacement = (
            "Liability is capped at twice the annual fee. {{@cite sentence mode=all}}"
        )
        _apply_caml_article_edit(
            corpus_id=self.corpus.id,
            author_id=self.superuser.id,
            target_text=target,
            replacement_text=replacement,
            rationale="superuser update",
        )
        self.assertIn("mode=all", self._read_caml_body())

    def test_async_wrapper_persists_edit(self):
        target = (
            "Force majeure clauses were updated in 2023 to cover supply-chain shocks."
        )
        replacement = (
            "Force majeure clauses were updated in 2023 to cover supply-chain "
            "shocks. {{@cite sentence}}"
        )
        result = async_to_sync(aapply_caml_article_edit)(
            corpus_id=self.corpus.id,
            author_id=self.owner.id,
            target_text=target,
            replacement_text=replacement,
            rationale="async path",
        )
        self.assertTrue(result["applied"])
        self.assertIn("{{@cite sentence}}", self._read_caml_body())


# --------------------------------------------------------------------------- #
# Registry integration                                                         #
# --------------------------------------------------------------------------- #


class CamlReviewToolRegistryTests(TestCase):
    """The new tools must be discoverable via the central tool registry."""

    @classmethod
    def setUpClass(cls):
        # Reset the registry around the whole class so an unexpected exception
        # in ``test_tool_definitions_are_registered`` cannot leak modified
        # registry state into unrelated tests sharing the same worker.
        super().setUpClass()
        from opencontractserver.llms.tools.tool_registry import ToolFunctionRegistry

        ToolFunctionRegistry.reset()

    @classmethod
    def tearDownClass(cls):
        from opencontractserver.llms.tools.tool_registry import ToolFunctionRegistry

        ToolFunctionRegistry.reset()
        super().tearDownClass()

    def test_tool_definitions_are_registered(self):
        from opencontractserver.llms.tools.tool_registry import (
            AVAILABLE_TOOLS,
            ToolFunctionRegistry,
        )

        names = {t.name for t in AVAILABLE_TOOLS}
        self.assertIn("read_corpus_caml_article", names)
        self.assertIn("propose_caml_citation_match", names)
        self.assertIn("apply_caml_article_edit", names)

        # ToolFunctionRegistry resolves each name to a CoreTool, with the
        # apply tool flagged as approval-gated and write-permission-gated.
        registry = ToolFunctionRegistry.get()

        apply_tool = registry.to_core_tool("apply_caml_article_edit")
        assert apply_tool is not None  # narrow for mypy
        self.assertTrue(apply_tool.requires_approval)
        self.assertTrue(apply_tool.requires_corpus)
        self.assertTrue(apply_tool.requires_write_permission)

        read_tool = registry.to_core_tool("read_corpus_caml_article")
        assert read_tool is not None
        self.assertFalse(read_tool.requires_approval)
        self.assertTrue(read_tool.requires_corpus)

        propose_tool = registry.to_core_tool("propose_caml_citation_match")
        assert propose_tool is not None
        self.assertFalse(propose_tool.requires_approval)
        self.assertTrue(propose_tool.requires_corpus)
