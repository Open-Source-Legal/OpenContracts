"""V2 import shim: artifacts with ``md_description`` + revisions must
synthesize a Readme.CAML Document + version-tree siblings.

Task 14 of the Canonical-CAML Corpus Description Refactor — see
``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``
§4.8.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath


class V2ImportBackCompatTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="v2-import", password="x")

    def test_md_description_becomes_readme_caml_doc(self):
        from opencontractserver.utils.import_v2 import (
            import_md_description_revisions,
        )

        corpus = Corpus.objects.create(title="C", creator=self.user)
        with self.captureOnCommitCallbacks(execute=True):
            import_md_description_revisions(
                md_description="# V2 body",
                revisions_data=[],
                corpus=corpus,
                user_obj=self.user,
                doc_filename_to_doc={},
                annot_old_id_to_new_pk={},
            )
        # Synthesized CAML doc exists
        path = DocumentPath.objects.filter(
            corpus=corpus, path="Readme.CAML", is_current=True
        ).first()
        self.assertIsNotNone(path)
        self.assertEqual(path.document.title, "Readme.CAML")
        self.assertEqual(path.document.file_type, "text/markdown")
        # Cache populated via signal
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "V2 body")

    def test_revisions_become_version_tree_siblings(self):
        from opencontractserver.utils.import_v2 import (
            import_md_description_revisions,
        )

        corpus = Corpus.objects.create(title="C", creator=self.user)
        with self.captureOnCommitCallbacks(execute=True):
            import_md_description_revisions(
                md_description="v3 body",
                revisions_data=[
                    {
                        "version": 1,
                        "author_email": self.user.email,
                        "snapshot": "v1 body",
                        "diff": "",
                        "checksum_base": "",
                        "checksum_full": "",
                        "created": "2025-01-01T00:00:00Z",
                        "modified": "2025-01-01T00:00:00Z",
                    },
                    {
                        "version": 2,
                        "author_email": self.user.email,
                        "snapshot": "v2 body",
                        "diff": "",
                        "checksum_base": "",
                        "checksum_full": "",
                        "created": "2025-01-02T00:00:00Z",
                        "modified": "2025-01-02T00:00:00Z",
                    },
                ],
                corpus=corpus,
                user_obj=self.user,
                doc_filename_to_doc={},
                annot_old_id_to_new_pk={},
            )
        corpus.refresh_from_db()
        head = corpus.readme_caml_document
        self.assertIsNotNone(head)
        tree_id = head.version_tree_id
        # 2 revisions + 1 current body = 3 Documents
        self.assertEqual(Document.objects.filter(version_tree_id=tree_id).count(), 3)

    def test_skips_when_artifact_already_contains_caml_doc(self):
        """If annotated_docs already created a Readme.CAML, md_description
        is ignored (logged warning)."""
        from opencontractserver.documents.versioning import import_document
        from opencontractserver.utils.import_v2 import (
            import_md_description_revisions,
        )

        corpus = Corpus.objects.create(title="C", creator=self.user)
        # Simulate the annotated_docs path having already imported a CAML
        with self.captureOnCommitCallbacks(execute=True):
            import_document(
                corpus=corpus,
                path="Readme.CAML",
                content=b"From annotated_docs.",
                user=self.user,
                file_type="text/markdown",
                title="Readme.CAML",
            )
        with self.captureOnCommitCallbacks(execute=True):
            import_md_description_revisions(
                md_description="should be ignored",
                revisions_data=[],
                corpus=corpus,
                user_obj=self.user,
                doc_filename_to_doc={},
                annot_old_id_to_new_pk={},
            )
        # Still exactly one Readme.CAML head; body matches annotated_docs
        heads = DocumentPath.objects.filter(
            corpus=corpus, path="Readme.CAML", is_current=True
        )
        self.assertEqual(heads.count(), 1)
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "From annotated_docs.")

    def test_empty_inputs_are_noop(self):
        """V3 archives don't carry md_description / revisions — shim must
        be a clean no-op so the dispatcher can call it unconditionally."""
        from opencontractserver.utils.import_v2 import (
            import_md_description_revisions,
        )

        corpus = Corpus.objects.create(title="C", creator=self.user)
        with self.captureOnCommitCallbacks(execute=True):
            import_md_description_revisions(
                md_description=None,
                revisions_data=[],
                corpus=corpus,
                user_obj=self.user,
                doc_filename_to_doc={},
                annot_old_id_to_new_pk={},
            )
        # No CAML doc synthesized — corpus stays untouched.
        self.assertFalse(
            DocumentPath.objects.filter(
                corpus=corpus, path="Readme.CAML", is_current=True
            ).exists()
        )
