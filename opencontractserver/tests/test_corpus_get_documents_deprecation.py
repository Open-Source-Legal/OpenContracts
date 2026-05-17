"""
Tests for the ``Corpus.get_documents()`` deprecation wrapper.

User-context callers should go through
``CorpusObjsService.get_corpus_documents(user, corpus)``. Internal/Celery
callers without a user should use ``Corpus._get_active_documents()``
directly. The public ``Corpus.get_documents()`` method survives only as a
``DeprecationWarning``-emitting shim that forwards to the private helper.
"""

from __future__ import annotations

import warnings

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()


class CorpusDeprecationTestBase(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Deprecation Corpus", creator=self.owner, is_public=False
        )
        self.doc = Document.objects.create(
            title="Doc",
            creator=self.owner,
            pdf_file="deprecation.pdf",
            slug="deprecation-doc",
        )
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/deprecation.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )


class TestCorpusGetDocumentsDeprecation(CorpusDeprecationTestBase):
    """
    SCENARIO: ``corpus.get_documents()`` is deprecated.

    BUSINESS RULE: Calling it must emit a ``DeprecationWarning`` so future
    drift is surfaced at runtime. The warning must point to the canonical
    replacements (the service for user-context, ``_get_active_documents``
    for internal).
    """

    def test_public_get_documents_emits_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.corpus.get_documents()

        deprecation_hits = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        self.assertEqual(
            len(deprecation_hits),
            1,
            f"Expected exactly one DeprecationWarning, got {len(deprecation_hits)}: "
            f"{[str(w.message) for w in deprecation_hits]}",
        )
        message = str(deprecation_hits[0].message)
        # The warning must mention both canonical replacements so a
        # grep-driven migration can find them from the message alone.
        self.assertIn("CorpusObjsService.get_corpus_documents", message)
        self.assertIn("_get_active_documents", message)

    def test_internal_helper_does_not_emit_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.corpus._get_active_documents()

        deprecation_hits = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        self.assertEqual(
            len(deprecation_hits),
            0,
            f"_get_active_documents should not warn, but emitted: "
            f"{[str(w.message) for w in deprecation_hits]}",
        )


class TestCorpusGetDocumentsParity(CorpusDeprecationTestBase):
    """
    SCENARIO: The deprecated wrapper returns the same data as the internal
    helper.

    BUSINESS RULE: The wrapper is a thin shim. It must not silently filter
    out documents or change ordering — otherwise migrating away from it
    would risk regressions.
    """

    def test_wrapper_and_internal_return_same_pks(self):
        with warnings.catch_warnings():
            # Suppress the wrapper's warning so this test doesn't fail when
            # ``filterwarnings = error::DeprecationWarning`` is configured.
            warnings.simplefilter("ignore", DeprecationWarning)
            from_wrapper = set(self.corpus.get_documents().values_list("pk", flat=True))
        from_internal = set(
            self.corpus._get_active_documents().values_list("pk", flat=True)
        )
        self.assertEqual(from_wrapper, from_internal)
        self.assertIn(self.doc.pk, from_internal)

    def test_include_caml_forwards_through_wrapper(self):
        """
        ``include_caml`` is the only kwarg on either method; it must pass
        through cleanly so legacy callers that rely on the flag (the CAML
        article paths tracked under the follow-up issue) keep working.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from_wrapper = set(
                self.corpus.get_documents(include_caml=True).values_list(
                    "pk", flat=True
                )
            )
        from_internal = set(
            self.corpus._get_active_documents(include_caml=True).values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(from_wrapper, from_internal)
