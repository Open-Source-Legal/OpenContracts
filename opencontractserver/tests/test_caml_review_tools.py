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
from opencontractserver.constants.document_processing import (
    CAML_ARTICLE_TITLE,
    CAML_EDIT_PREVIEW_RADIUS_CHARS,
    MARKDOWN_MIME_TYPE,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import (
    aapply_caml_article_edit,
    apropose_caml_citation_match,
    aread_corpus_caml_article,
)
from opencontractserver.llms.tools.core_tools.caml_article import (
    _apply_caml_article_edit,
    _looks_like_prose,
    _parse_directive_args,
    _read_caml_content,
    _read_corpus_caml_article,
    _safe_delete_storage_path,
)
from opencontractserver.llms.vector_stores.core_vector_stores import VectorSearchResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


def _noop_vector_store_init(self, *args, **kwargs):
    """No-op replacement for ``CoreAnnotationVectorStore.__init__``.

    Tests in ``ProposeCamlCitationMatchTests`` only exercise the adapter
    logic around ``async_search`` — they don't need real embedder resolution.
    Skipping the constructor avoids depending on ``PipelineSettings`` (the
    singleton row created by migration 0031 is truncated by every
    ``TransactionTestCase`` run, so the row may be absent when other test
    classes share our pytest-xdist worker).
    """
    return None


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
    """Create a Readme.CAML Document linked to ``corpus`` with ``content``.

    Mirrors the production CAML write path
    (:func:`opencontractserver.documents.versioning.import_document` with
    ``path=CAML_ARTICLE_TITLE``), which stores the doc at the reserved,
    slashless ``"Readme.CAML"`` path so the CAML review/edit tools and
    subsequent ``import_document`` version-ups look it up by that canonical
    path. ``corpus.add_document(path="Readme.CAML")`` is the wrong API here:
    it routes through ``CorpusPathService.disambiguate_path``, which (by
    design, see #1838) rejects any path lacking a leading ``/``.
    """
    from opencontractserver.documents.versioning import import_document

    doc, _status, _path = import_document(
        corpus=corpus,
        path=CAML_ARTICLE_TITLE,
        content=content.encode("utf-8"),
        user=user,
        file_type=MARKDOWN_MIME_TYPE,
        title=CAML_ARTICLE_TITLE,
    )
    return doc


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
        """IDOR: another user cannot enumerate or read a private corpus's CAML.

        Locks in the IDOR-safe identical-error contract by asserting the
        outsider gets the *exact* same message format as a request for a
        non-existent corpus — only the ``corpus_id`` placeholder differs, so
        the message reveals nothing the caller did not already supply.
        """
        existing_id = self.corpus.id
        nonexistent_id = self.corpus.id + 99999

        with self.assertRaises(ValueError) as ctx_existing:
            _read_corpus_caml_article(corpus_id=existing_id, author_id=self.outsider.id)
        with self.assertRaises(ValueError) as ctx_nonexistent:
            _read_corpus_caml_article(
                corpus_id=nonexistent_id, author_id=self.outsider.id
            )

        self.assertIn("Readme.CAML", str(ctx_existing.exception))
        # Substituting the corpus_id back to a fixed placeholder must yield
        # byte-identical strings: same template, different injected ID.
        self.assertEqual(
            str(ctx_existing.exception).replace(str(existing_id), "<id>"),
            str(ctx_nonexistent.exception).replace(str(nonexistent_id), "<id>"),
        )

    def test_corpus_without_caml_raises(self):
        empty_corpus = Corpus.objects.create(title="No CAML Corpus", creator=self.owner)
        with self.assertRaises(ValueError) as ctx:
            _read_corpus_caml_article(
                corpus_id=empty_corpus.id, author_id=self.owner.id
            )
        self.assertIn("Readme.CAML", str(ctx.exception))

    def test_unknown_user_raises(self):
        """A non-existent ``author_id`` must raise rather than crash silently."""
        with self.assertRaises(ValueError) as ctx:
            _read_corpus_caml_article(corpus_id=self.corpus.id, author_id=99_999_999)
        self.assertIn("does not exist", str(ctx.exception))

    def test_doc_with_no_file_returns_empty_blocks(self):
        """A CAML document whose ``txt_extract_file`` is empty yields no blocks.

        Locks in ``_read_caml_content``'s falsy-file early return: the read
        tool must succeed (returning an empty article) rather than raising,
        so the agent can detect a freshly-created CAML and prompt for content.
        """
        empty_doc = Document.objects.create(
            title="Readme.CAML",
            creator=self.owner,
            file_type=MARKDOWN_MIME_TYPE,
            processing_started=timezone.now(),
            backend_lock=False,
        )
        # No call to ``txt_extract_file.save`` -- the FieldFile is empty/falsy.
        empty_corpus = Corpus.objects.create(
            title="Empty CAML Corpus", creator=self.owner, is_public=False
        )
        empty_corpus.add_document(document=empty_doc, user=self.owner)

        result = _read_corpus_caml_article(
            corpus_id=empty_corpus.id, author_id=self.owner.id
        )
        self.assertEqual(result["content"], "")
        self.assertEqual(result["blocks"], [])
        self.assertEqual(result["candidate_block_indices"], [])
        self.assertEqual(result["total_directives"], 0)

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


class ProposeCamlCitationMatchTests(TransactionTestCase):
    """Tests for the citation candidate proposal tool.

    The vector store's ``async_search`` is patched so we don't depend on a
    configured embedder -- we only need to verify the tool's adapter logic
    (shape, capping, error handling).

    Uses ``TransactionTestCase`` (not ``TestCase``) because
    ``apropose_caml_citation_match`` now performs an inline corpus-visibility
    check via ``_db_sync_to_async`` (``thread_sensitive=False``); the helper
    thread opens a fresh DB connection that only sees committed data, so the
    fixture rows must live outside a per-test ``atomic()`` wrapper.
    """

    owner: User
    corpus: Corpus
    doc: Document
    label: AnnotationLabel
    annotation: Annotation

    def setUp(self):
        # Fixtures are recreated per-test so ``TransactionTestCase``'s
        # post-test truncation doesn't leak rows between cases, and so the
        # async helper thread sees them via its own committed view.
        self.owner = User.objects.create_user(username="propose_owner", password="pw")
        self.corpus = Corpus.objects.create(
            title="Propose Corpus", creator=self.owner, is_public=True
        )
        self.doc = Document.objects.create(
            title="Source Doc",
            creator=self.owner,
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.doc, _, _ = self.corpus.add_document(document=self.doc, user=self.owner)
        self.label = AnnotationLabel.objects.create(
            text="Liability Cap", color="#abcdef", creator=self.owner
        )
        self.annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            raw_text="Liability is capped at twice the annual fee.",
            annotation_label=self.label,
            page=3,
            is_public=True,
        )

    def _patch_async_search(self, results):
        """Return a context manager patching the vector store to return ``results``.

        Patches *both* ``__init__`` (no-op) and ``async_search`` on
        ``CoreAnnotationVectorStore``.  Bypassing the constructor matters
        under pytest-xdist's ``--dist loadscope`` runner: the real ``__init__``
        calls ``get_embedder()`` which depends on a ``PipelineSettings`` row
        seeded by migration 0031.  ``TransactionTestCase`` truncates that row
        between tests on the same worker (it has ``serialized_rollback=False``
        by default), so an unrelated test class running first would leave us
        without a default embedder and the *real* constructor would raise
        before our patched ``async_search`` could ever execute.
        """

        async def _fake_async_search(self, query):
            return list(results)

        return patch.multiple(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore",
            __init__=_noop_vector_store_init,
            async_search=_fake_async_search,
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

        with patch.multiple(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore",
            __init__=_noop_vector_store_init,
            async_search=_capture_query,
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

        with patch.multiple(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore",
            __init__=_noop_vector_store_init,
            async_search=_explode,
        ):
            with self.assertRaises(ValueError) as ctx:
                async_to_sync(apropose_caml_citation_match)(
                    corpus_id=self.corpus.id,
                    author_id=self.owner.id,
                    query_text="anything",
                )
        self.assertIn("Semantic search failed", str(ctx.exception))

    def test_constructor_failure_surfaces_as_value_error(self):
        """An exploding ``__init__`` (e.g., no embedder) is wrapped, not raw.

        Pins the production guard around ``CoreAnnotationVectorStore(...)``
        construction: the real constructor raises ``ValueError`` from
        ``get_embedder()`` when ``PipelineSettings`` has no default embedder
        and the corpus has no ``preferred_embedder``.  The tool must surface
        the failure as the same friendly "Semantic search failed" message
        the agent recognises, not leak the raw embedder error.
        """

        def _exploding_init(self, *args, **kwargs):
            raise ValueError(
                "get_embedder() resolved no embedder_path; vector search "
                "cannot proceed without one."
            )

        async def _should_not_run(self, query):  # pragma: no cover - fail-loud
            raise AssertionError("async_search must not run when __init__ raises")

        with patch.multiple(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore",
            __init__=_exploding_init,
            async_search=_should_not_run,
        ):
            with self.assertRaises(ValueError) as ctx:
                async_to_sync(apropose_caml_citation_match)(
                    corpus_id=self.corpus.id,
                    author_id=self.owner.id,
                    query_text="anything",
                )
        # The wrap message must include the raw embedder error so operators
        # can still diagnose, but it must lead with the friendly prefix.
        self.assertIn("Semantic search failed", str(ctx.exception))
        self.assertIn("embedder_path", str(ctx.exception))

    def test_unknown_user_raises_before_search(self):
        """Pin the ``User.DoesNotExist`` branch in ``_assert_corpus_visible_to_user``.

        Mirrors ``test_invisible_corpus_raises_before_search`` for the
        author-not-found path: the same opaque "not visible" error is
        emitted so a caller cannot tell "missing user" from "no permission".
        """

        async def _should_not_run(self, query):  # pragma: no cover - fail-loud
            raise AssertionError("vector search must not run for unknown user")

        with patch.multiple(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore",
            __init__=_noop_vector_store_init,
            async_search=_should_not_run,
        ):
            with self.assertRaises(ValueError) as ctx:
                async_to_sync(apropose_caml_citation_match)(
                    corpus_id=self.corpus.id,
                    author_id=99_999_999,
                    query_text="anything",
                )
        self.assertIn("not visible", str(ctx.exception))

    def test_invisible_corpus_raises_before_search(self):
        """Defense-in-depth: an outsider cannot search a private corpus.

        Pins the inline ``_assert_corpus_visible_to_user`` guard so the tool
        fails closed even when the registry wrapper is bypassed. The patched
        ``async_search`` would surface a distinguishable error if it were
        ever reached.
        """
        outsider = User.objects.create_user(username="propose_outsider", password="pw")
        private_corpus = Corpus.objects.create(
            title="Private", creator=self.owner, is_public=False
        )

        async def _should_not_run(self, query):  # pragma: no cover - fail-loud
            raise AssertionError(
                "vector search must not run when corpus is invisible to author"
            )

        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores"
            ".CoreAnnotationVectorStore.async_search",
            new=_should_not_run,
        ):
            with self.assertRaises(ValueError) as ctx:
                async_to_sync(apropose_caml_citation_match)(
                    corpus_id=private_corpus.id,
                    author_id=outsider.id,
                    query_text="anything",
                )
        self.assertIn("not visible", str(ctx.exception))


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
        """Read the body of the current Readme.CAML head.

        After the canonical-CAML refactor each edit creates a new
        Document at the head of the version_tree (spec §4.1.1), so
        ``self.caml_doc`` is the *historical* sibling once an edit lands.
        Re-resolve the current head via DocumentPath each call.
        """
        from opencontractserver.documents.models import DocumentPath

        path = (
            DocumentPath.objects.select_related("document")
            .filter(
                corpus=self.corpus,
                path="Readme.CAML",
                is_current=True,
                is_deleted=False,
            )
            .first()
        )
        if path is None:
            self.caml_doc.refresh_from_db()
            with self.caml_doc.txt_extract_file.open("r") as fh:
                return fh.read()
        head = path.document
        head.refresh_from_db()
        with head.txt_extract_file.open("r") as fh:
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
        # After the canonical-CAML refactor each edit creates a new
        # Document at the head of the version_tree (spec §4.1.1) — the
        # returned document_id therefore points at the new head, NOT
        # the historical sibling captured in self.caml_doc.
        from opencontractserver.documents.models import DocumentPath

        current_head = DocumentPath.objects.get(
            corpus=self.corpus,
            path="Readme.CAML",
            is_current=True,
            is_deleted=False,
        ).document
        self.assertEqual(result["document_id"], current_head.id)
        self.assertNotEqual(current_head.id, self.caml_doc.id)
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

    def test_unknown_user_raises(self):
        """A non-existent ``author_id`` must raise the user-not-found error."""
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=99_999_999,
                target_text="Force majeure",
                replacement_text="x",
                rationale="r",
            )
        self.assertIn("does not exist", str(ctx.exception))

    def test_empty_target_text_raises(self):
        """``target_text`` must be non-empty -- empty would match everywhere."""
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                target_text="",
                replacement_text="anything",
                rationale="r",
            )
        self.assertIn("non-empty", str(ctx.exception))

    def test_empty_caml_file_raises_not_found(self):
        """Edit against an empty CAML body surfaces the same not-found error.

        ``_read_caml_content`` returns ``""`` when ``txt_extract_file`` is
        falsy/empty; the apply tool must refuse the edit (rather than
        silently producing a no-op or ``IndexError`` from ``content.find``)
        so the agent gets a deterministic signal that it should re-read the
        article.
        """
        # Replace the body with an empty file -- the FieldFile pointer stays
        # set, but ``_read_caml_content`` returns "" because the blob has no
        # content to count target_text occurrences in.
        self.caml_doc.txt_extract_file.save(
            "Readme.CAML.md",
            ContentFile(b""),
            save=True,
        )
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.owner.id,
                target_text="anything",
                replacement_text="anything else",
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

    def test_creator_without_explicit_perm_can_edit(self):
        """The CAML document's creator can edit it without an explicit guardian perm.

        Phase E (#1659) drops the legacy ``locked_doc.creator_id == user.pk``
        short-circuit because ``user_can`` now honours creator access uniformly
        (Phase A — #1655). This test pins the semantic widening: a user who is
        the ``locked_doc.creator`` but holds no explicit guardian UPDATE row
        must still pass the gate. Without the creator-honoring path baked into
        ``user_can``, the edit would now raise ``cannot modify``.
        """
        from guardian.shortcuts import get_perms

        # The owner is the creator of the CAML doc (via ``_create_caml_doc``
        # and ``corpus.add_document``) but ``add_document`` never assigns
        # guardian UPDATE perms, so this is the creator-without-explicit-perm
        # case the issue calls out. Make the relationship explicit so a future
        # refactor that auto-grants doc perms on creation won't silently mask
        # the regression we're guarding against.
        self.caml_doc.refresh_from_db()
        self.assertEqual(self.caml_doc.creator_id, self.owner.id)
        self.assertNotIn(
            "update_document",
            get_perms(self.owner, self.caml_doc),
            "Setup invariant violated: owner unexpectedly has explicit UPDATE perm "
            "on the CAML doc — this test must exercise the creator-only path.",
        )

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
            rationale="Creator edits CAML article.",
        )
        self.assertTrue(result["applied"])
        self.assertIn("{{@cite sentence}}", self._read_caml_body())

    def test_superuser_edit_computed_like_normal_user(self):
        """A superuser's DATA authorization is computed like a normal user.

        Post-refactor a no-grant superuser is a "stranger": it has no blanket
        bypass over corpus/document data. Editing a private stranger corpus's
        CAML article requires corpus READ (to resolve the article) and
        document UPDATE (to write it), computed normally.

        Denied path: the no-grant superuser cannot even resolve the private
        corpus's Readme.CAML, so it gets the same opaque "no CAML article"
        error an outsider receives — it must NOT be able to apply the edit.
        Allowed path: once the corpus is shared READ-able and the superuser is
        granted UPDATE on the CAML document, the edit succeeds via the normal
        gate (no superuser exception involved).
        """
        target = "Liability is capped at twice the annual fee. {{@cite sentence}}"
        replacement = (
            "Liability is capped at twice the annual fee. {{@cite sentence mode=all}}"
        )

        # Denied: no-grant superuser is computed like a stranger.
        with self.assertRaises(ValueError) as ctx:
            _apply_caml_article_edit(
                corpus_id=self.corpus.id,
                author_id=self.superuser.id,
                target_text=target,
                replacement_text=replacement,
                rationale="superuser update (should be denied)",
            )
        self.assertIn("Readme.CAML", str(ctx.exception))
        # The edit must not have landed.
        self.assertNotIn("mode=all", self._read_caml_body())

        # Allowed: grant the superuser exactly what a normal user would need —
        # corpus READ (so the article resolves) and document UPDATE (so it can
        # be written). The edit now succeeds through the ordinary permission
        # path, with no superuser bypass.
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        self.caml_doc.is_public = True
        self.caml_doc.save(update_fields=["is_public"])
        set_permissions_for_obj_to_user(
            self.superuser,
            self.caml_doc,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        _apply_caml_article_edit(
            corpus_id=self.corpus.id,
            author_id=self.superuser.id,
            target_text=target,
            replacement_text=replacement,
            rationale="superuser update (granted)",
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

    def test_edit_creates_new_version_tree_sibling(self):
        """Each edit must create a new Document at the head of the version
        tree, leaving the previous Document as a historical sibling.

        After the canonical-CAML refactor (spec §4.1.1) CAML edits no
        longer overwrite the same blob in place; they go through
        ``import_document`` which creates a new Document sharing the
        existing ``version_tree_id`` and flips ``DocumentPath.is_current``
        flags atomically. The old Document retains its blob — it's a
        historical version, not orphaned storage.
        """
        from django.core.files.storage import default_storage

        from opencontractserver.documents.models import Document, DocumentPath

        old_name = self.caml_doc.txt_extract_file.name
        old_doc_id = self.caml_doc.id
        tree_id = self.caml_doc.version_tree_id
        assert old_name, "Fixture CAML doc must have a non-empty file name."
        self.assertTrue(default_storage.exists(old_name))

        _apply_caml_article_edit(
            corpus_id=self.corpus.id,
            author_id=self.owner.id,
            target_text=(
                "Force majeure clauses were updated in 2023 to "
                "cover supply-chain shocks."
            ),
            replacement_text=(
                "Force majeure clauses were updated in 2023 to "
                "cover supply-chain shocks. {{@cite sentence}}"
            ),
            rationale="version up",
        )

        # New head is a different Document sharing the version_tree_id
        new_head = DocumentPath.objects.get(
            corpus=self.corpus,
            path="Readme.CAML",
            is_current=True,
            is_deleted=False,
        ).document
        self.assertNotEqual(new_head.id, old_doc_id)
        self.assertEqual(new_head.version_tree_id, tree_id)

        # Two Documents in the tree now (head + historical sibling)
        self.assertEqual(Document.objects.filter(version_tree_id=tree_id).count(), 2)

        # Both blobs persist — the old one is a historical record, not
        # orphaned storage.
        self.assertTrue(default_storage.exists(old_name))
        self.assertNotEqual(new_head.txt_extract_file.name, old_name)
        self.assertTrue(default_storage.exists(new_head.txt_extract_file.name))


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


class ParseDirectiveArgsTests(TestCase):
    """Pure-function tests for the directive-arg parser used by the read tool."""

    def test_returns_empty_for_none_or_blank(self):
        self.assertEqual(_parse_directive_args(None), {})
        self.assertEqual(_parse_directive_args(""), {})
        self.assertEqual(_parse_directive_args("   "), {})

    def test_parses_unquoted_key_value_pairs(self):
        self.assertEqual(
            _parse_directive_args("mode=all limit=5"),
            {"mode": "all", "limit": "5"},
        )

    def test_parses_double_quoted_values_with_spaces(self):
        """Quoted values may contain spaces; the regex must capture them whole."""
        self.assertEqual(
            _parse_directive_args('mode="all phrases" label="Force Majeure"'),
            {"mode": "all phrases", "label": "Force Majeure"},
        )

    def test_mixes_quoted_and_unquoted_values(self):
        self.assertEqual(
            _parse_directive_args('mode="all phrases" limit=5'),
            {"mode": "all phrases", "limit": "5"},
        )


class LooksLikeProseTests(TestCase):
    """Pure-function tests for the citation-candidate prose heuristic."""

    def test_rejects_blank_and_whitespace(self):
        self.assertFalse(_looks_like_prose(""))
        self.assertFalse(_looks_like_prose("   \n  \t "))

    def test_rejects_headings_blockquotes_tables(self):
        self.assertFalse(_looks_like_prose("# Heading"))
        self.assertFalse(_looks_like_prose("## Sub-heading"))
        self.assertFalse(_looks_like_prose("> A blockquote"))
        self.assertFalse(_looks_like_prose("| col | col2 |"))

    def test_rejects_list_markers_with_required_whitespace(self):
        """``-``, ``*``, ``+`` only count as list markers when followed by whitespace."""
        self.assertFalse(_looks_like_prose("- bullet"))
        self.assertFalse(_looks_like_prose("* bullet"))
        self.assertFalse(_looks_like_prose("+ bullet"))
        self.assertFalse(_looks_like_prose("-\tbullet"))

    def test_rejects_thematic_breaks_and_setext_underlines(self):
        self.assertFalse(_looks_like_prose("---"))
        self.assertFalse(_looks_like_prose("___"))
        self.assertFalse(_looks_like_prose("==="))
        self.assertFalse(_looks_like_prose("- - -"))
        # ``***`` is a valid CommonMark thematic break — characters are
        # all ``*``, so the subset-of-{-, _, =, *} guard rejects it.
        self.assertFalse(_looks_like_prose("***"))
        self.assertFalse(_looks_like_prose("* * *"))

    def test_rejects_code_fences(self):
        self.assertFalse(_looks_like_prose("```python"))
        self.assertFalse(_looks_like_prose("```"))

    def test_accepts_paragraph_starting_with_emphasis_run(self):
        """``*italic*`` is an emphasis run, not a list marker, and IS prose.

        The earlier heuristic rejected any block whose first character was
        ``*``; CommonMark requires a *space* after ``*`` for it to be a
        list marker.  Pin this so a paragraph like
        ``*Force majeure* clauses…`` is included as a citation candidate.
        """
        self.assertTrue(
            _looks_like_prose("*Force majeure* clauses were updated in 2023.")
        )
        self.assertTrue(_looks_like_prose("**Bold** opener for a paragraph."))

    def test_accepts_normal_prose(self):
        self.assertTrue(
            _looks_like_prose(
                "Liability is capped at twice the annual fee under section 5."
            )
        )

    def test_rejects_component_markers(self):
        """``[component:...]`` blocks are embedded UI, not citable prose."""
        self.assertFalse(_looks_like_prose("[component:Disclaimer]"))
        self.assertFalse(
            _looks_like_prose("[component:CitationCard id=42 mode=preview]")
        )

    def test_rejects_numbered_lists(self):
        """``1. item`` style ordered list markers are not prose openings."""
        self.assertFalse(_looks_like_prose("1. First step in the procedure."))
        self.assertFalse(_looks_like_prose("12. A later numbered item."))


class SafeDeleteStoragePathTests(TestCase):
    """Pure-function tests for the orphan-blob cleanup helper.

    The function runs as a transaction-on-commit callback so its contract is
    "never raise" — that's load-bearing for the apply tool, which would
    otherwise return a successful edit while letting a transient storage
    error blow up the caller.
    """

    def test_no_op_for_empty_name(self):
        """Empty / falsy name short-circuits before touching storage.

        A guard against accidentally calling ``default_storage.delete("")``
        which on some backends deletes the storage root directory entry.
        """
        # Should not raise, regardless of whether storage backend is configured.
        _safe_delete_storage_path("")
        _safe_delete_storage_path("   ")  # NB: still treated as a real path
        # Whitespace strings ARE truthy in Python so the function will attempt
        # the delete; what we care about for this branch is the empty-string
        # short-circuit.

    def test_swallows_storage_errors(self):
        """Storage errors during cleanup are logged, never re-raised.

        ``_safe_delete_storage_path`` runs after the DB pointer has already
        been bumped, so propagating a storage failure here would surface a
        post-success exception to the agent — confusing and non-actionable.
        """
        with patch(
            "django.core.files.storage.default_storage.delete",
            side_effect=OSError("permission denied"),
        ):
            # Must not raise.
            _safe_delete_storage_path("some/orphan/path.md")


class ReadCamlContentHelperTests(TestCase):
    """Pin the empty-file early return in ``_read_caml_content``.

    The helper's docstring promises ``''`` for a falsy ``txt_extract_file``;
    the apply tool's "empty body raises not found" test exercises this
    indirectly, but a direct unit assertion makes the contract explicit.
    """

    def test_returns_empty_string_for_falsy_file(self):
        owner = User.objects.create_user(username="rcc-helper-owner", password="pw")
        # A Document with no ``txt_extract_file.save`` call has a falsy
        # ``FieldFile`` (no underlying name), so the early return fires.
        doc = Document.objects.create(
            title="Readme.CAML",
            creator=owner,
            file_type=MARKDOWN_MIME_TYPE,
            processing_started=timezone.now(),
            backend_lock=False,
        )
        self.assertEqual(_read_caml_content(doc), "")


class ApplyCamlArticleEditPreviewTests(TestCase):
    """Verify the ``preview`` window returned by the apply tool."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            username="caml-preview-owner", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Preview Test", creator=self.owner, is_public=False
        )
        # Body long enough to exercise the radius-bounded preview window:
        # the target sits at a known offset so we can predict its expansion.
        body_prefix = "alpha " * 40  # ~240 chars of filler
        self.body = (
            f"{body_prefix}" "TARGET-PHRASE." f"{body_prefix}" "Trailing content."
        )
        self.caml_doc = _create_caml_doc(self.corpus, self.owner, content=self.body)

    def test_preview_window_centers_around_replacement(self):
        result = _apply_caml_article_edit(
            corpus_id=self.corpus.id,
            author_id=self.owner.id,
            target_text="TARGET-PHRASE.",
            replacement_text="REPLACED.",
            rationale="Sanity-check the preview window",
        )

        preview = result["preview"]
        # The replacement text must appear in the preview.
        self.assertIn("REPLACED.", preview)
        # The preview is bounded by ``CAML_EDIT_PREVIEW_RADIUS_CHARS`` on each
        # side of the replacement.  Cap the maximum length: radius before +
        # replacement length + radius after.
        max_expected = (
            CAML_EDIT_PREVIEW_RADIUS_CHARS
            + len("REPLACED.")
            + CAML_EDIT_PREVIEW_RADIUS_CHARS
        )
        self.assertLessEqual(len(preview), max_expected)
        # Some context from the prefix and suffix should also be visible.
        self.assertIn("alpha", preview)

    def test_preview_window_clamps_at_document_boundaries(self):
        """A target near the start of the body must not wander past offset 0."""
        # Replace the body so the target is at position 0.
        edge_body = "TARGET-PHRASE. " + ("alpha " * 30)
        self.caml_doc.txt_extract_file.save(
            "Readme.CAML.md",
            ContentFile(edge_body.encode("utf-8")),
            save=False,
        )
        self.caml_doc.save(update_fields=["txt_extract_file", "modified"])

        result = _apply_caml_article_edit(
            corpus_id=self.corpus.id,
            author_id=self.owner.id,
            target_text="TARGET-PHRASE.",
            replacement_text="EDGE.",
            rationale="Edge-of-document preview",
        )

        # ``preview_start`` clamps to 0, so the preview begins with the edit.
        self.assertTrue(result["preview"].startswith("EDGE."))
        # And the offset reported back is also 0.
        self.assertEqual(result["char_offset"], 0)


class ApplyCamlArticleEditCreatesVersionTreeSiblingTest(TransactionTestCase):
    """Pin Task 8.5: agent CAML edits create a version-tree sibling.

    After the refactor, ``_apply_caml_article_edit`` routes its write through
    ``opencontractserver.documents.versioning.import_document`` (the canonical
    dual-tree workhorse).  Each successful edit:

    1. Creates a NEW ``Document`` sharing the existing ``version_tree_id``
       with the previous head.
    2. Flips the old ``DocumentPath.is_current`` to ``False``.
    3. Creates a new ``DocumentPath`` with ``is_current=True`` and a bumped
       ``version_number``.

    The previous Document remains in the version tree as a historical
    sibling (its blob is NOT orphaned).  The returned ``document_id`` now
    points at the new head, not the old locked doc.

    Uses ``TransactionTestCase`` because the async tool wrapper
    (``_db_sync_to_async`` with ``thread_sensitive=False``) runs on a helper
    thread with its own DB connection; ``TestCase`` rollback isolation would
    hide the setUp data from that thread.

    Spec: ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``
    §4.1.1 §4.7.
    """

    def setUp(self):
        from opencontractserver.documents.versioning import import_document

        self.user = User.objects.create_user(username="aae", password="x")
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        import_document(
            corpus=self.corpus,
            path="Readme.CAML",
            content=b"Hello target world.",
            user=self.user,
            file_type="text/markdown",
            title="Readme.CAML",
        )

    def test_edit_creates_new_version_tree_sibling(self):
        import asyncio

        from opencontractserver.documents.models import Document, DocumentPath

        # Capture pre-edit head: the DocumentPath ``is_current`` row pins
        # the head, not the Document row (the FK direction is
        # DocumentPath → Document).
        first = DocumentPath.objects.get(
            corpus=self.corpus, path="Readme.CAML", is_current=True
        ).document
        tree_id = first.version_tree_id

        result = asyncio.run(
            aapply_caml_article_edit(
                corpus_id=self.corpus.pk,
                author_id=self.user.pk,
                target_text="target",
                replacement_text="replacement",
                rationale="test",
            )
        )
        self.assertTrue(result["applied"])

        # New current head exists and is a sibling sharing the tree id.
        current = DocumentPath.objects.get(
            corpus=self.corpus, path="Readme.CAML", is_current=True
        ).document
        self.assertEqual(current.version_tree_id, tree_id)
        self.assertNotEqual(current.pk, first.pk)
        # The old doc remains in the version tree.
        self.assertEqual(Document.objects.filter(version_tree_id=tree_id).count(), 2)
        # The returned ``document_id`` points at the new head, not the
        # previously-locked (now historical) doc.
        self.assertEqual(result["document_id"], current.pk)
        # Body of the new head reflects the substitution.
        current.refresh_from_db()
        current.txt_extract_file.open("r")
        try:
            body = current.txt_extract_file.read()
        finally:
            current.txt_extract_file.close()
        self.assertEqual(body, "Hello replacement world.")
