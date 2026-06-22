"""
Tests for CorpusAccessToken ("WorkerKey") authentication on the document
import endpoints (PR #2038 follow-up).

The worker-token path must replicate the /api/worker-uploads/ trust model
exactly: the corpus is taken from the token binding (non-spoofable), the
usage-cap / visible_to_user gates are skipped, and documents are owned by the
corpus creator. The JWT path must be unchanged.
"""

from __future__ import annotations

import io
import zipfile

from django.test import TestCase, override_settings
from graphql_relay import to_global_id
from rest_framework.test import APIClient

from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.document_imports.services import (
    ChunkedUploadError,
    DocumentImportPermissionError,
    import_document_for_user,
    import_zip_to_corpus_for_user,
    start_chunked_upload,
)
from opencontractserver.users.models import User
from opencontractserver.worker_uploads.models import CorpusAccessToken, WorkerAccount

_PDF = b"%PDF-1.4 test document\n%%EOF\n"


def _zip_bytes(arcname: str = "a/b.pdf") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(arcname, _PDF)
    return buf.getvalue()


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class WorkerTokenZipServiceTests(TestCase):
    owner: User
    ls: LabelSet
    corpus: Corpus
    other: Corpus
    account: WorkerAccount
    token: CorpusAccessToken

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="owner1", password="x")
        cls.ls = LabelSet.objects.create(title="LS", creator=cls.owner)
        cls.corpus = Corpus.objects.create(
            title="C1", creator=cls.owner, label_set=cls.ls
        )
        cls.other = Corpus.objects.create(
            title="C2", creator=cls.owner, label_set=cls.ls
        )
        cls.account = WorkerAccount.create_with_user(name="w1", creator=cls.owner)
        cls.token, _ = CorpusAccessToken.create_token(
            worker_account=cls.account, corpus=cls.corpus
        )

    def test_token_for_other_corpus_is_rejected(self):
        """A token bound to C1 cannot import into C2 (-> 403 at the REST layer)."""
        with self.assertRaises(DocumentImportPermissionError):
            import_zip_to_corpus_for_user(
                user=self.account.user,
                zip_source=_zip_bytes(),
                corpus_id=to_global_id("CorpusType", self.other.pk),
                access_token=self.token,
            )

    def test_token_matching_corpus_is_accepted(self):
        """A token bound to C1 imports into C1 even though the worker user is
        usage-capped and lacks guardian EDIT — the token is the authz."""
        self.assertTrue(self.account.user.is_usage_capped)  # default cap
        res = import_zip_to_corpus_for_user(
            user=self.account.user,
            zip_source=_zip_bytes(),
            corpus_id=str(self.corpus.pk),  # raw pk accepted too
            access_token=self.token,
        )
        self.assertIsNone(res.error)
        self.assertIsNotNone(res.job_id)


class WorkerTokenSingleDocServiceTests(TestCase):
    owner: User
    ls: LabelSet
    corpus: Corpus
    account: WorkerAccount
    token: CorpusAccessToken

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="owner2", password="x")
        cls.ls = LabelSet.objects.create(title="LS2", creator=cls.owner)
        cls.corpus = Corpus.objects.create(
            title="S1", creator=cls.owner, label_set=cls.ls
        )
        cls.account = WorkerAccount.create_with_user(name="w2", creator=cls.owner)
        cls.token, _ = CorpusAccessToken.create_token(
            worker_account=cls.account, corpus=cls.corpus
        )

    def test_token_single_doc_lands_in_nested_folder_owned_by_creator(self):
        res = import_document_for_user(
            user=self.account.user,
            file_bytes=_PDF,
            filename="x.pdf",
            title="x.pdf",
            description="",
            add_to_corpus_id=str(self.corpus.pk),
            add_to_folder_path="alpha/beta",
            access_token=self.token,
        )
        self.assertIsNone(res.error)
        self.assertIsNotNone(res.document)
        assert res.document is not None  # narrow Optional for type-checkers
        # Owned by the corpus creator, not the worker service account.
        self.assertEqual(res.document.creator_id, self.owner.pk)
        leaf = CorpusFolder.objects.get(corpus=self.corpus, name="beta")
        self.assertEqual(leaf.parent.name, "alpha")

    def test_token_single_doc_other_corpus_rejected(self):
        other = Corpus.objects.create(title="S2", creator=self.owner, label_set=self.ls)
        with self.assertRaises(DocumentImportPermissionError):
            import_document_for_user(
                user=self.account.user,
                file_bytes=_PDF,
                filename="x.pdf",
                title="x.pdf",
                description="",
                add_to_corpus_id=str(other.pk),
                access_token=self.token,
            )


class WorkerTokenChunkedServiceTests(TestCase):
    owner: User
    ls: LabelSet
    corpus: Corpus
    other: Corpus
    account: WorkerAccount
    token: CorpusAccessToken

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="owner3", password="x")
        cls.ls = LabelSet.objects.create(title="LS3", creator=cls.owner)
        cls.corpus = Corpus.objects.create(
            title="K1", creator=cls.owner, label_set=cls.ls
        )
        cls.other = Corpus.objects.create(
            title="K2", creator=cls.owner, label_set=cls.ls
        )
        cls.account = WorkerAccount.create_with_user(name="w3", creator=cls.owner)
        cls.token, _ = CorpusAccessToken.create_token(
            worker_account=cls.account, corpus=cls.corpus
        )

    def test_start_rejects_token_for_other_corpus(self):
        with self.assertRaises(ChunkedUploadError):
            start_chunked_upload(
                user=self.account.user,
                kind="zip_to_corpus",
                filename="b.zip",
                total_size=10,
                chunk_size=10,
                total_chunks=1,
                metadata={"corpus_id": str(self.other.pk)},
                access_token=self.token,
            )

    def test_start_accepts_token_for_bound_corpus(self):
        session = start_chunked_upload(
            user=self.account.user,
            kind="zip_to_corpus",
            filename="b.zip",
            total_size=10,
            chunk_size=10,
            total_chunks=1,
            metadata={"corpus_id": str(self.corpus.pk)},
            access_token=self.token,
        )
        self.assertEqual(session.creator_id, self.account.user.pk)

    def test_start_rejects_unsupported_kind_for_token(self):
        with self.assertRaises(ChunkedUploadError):
            start_chunked_upload(
                user=self.account.user,
                kind="corpus_export",
                filename="b.zip",
                total_size=10,
                chunk_size=10,
                total_chunks=1,
                metadata={},
                access_token=self.token,
            )


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class WorkerTokenRestEndpointTests(TestCase):
    owner: User
    ls: LabelSet
    corpus: Corpus
    other: Corpus
    account: WorkerAccount
    token: CorpusAccessToken
    plaintext: str

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="rowner", password="x")
        cls.ls = LabelSet.objects.create(title="RLS", creator=cls.owner)
        cls.corpus = Corpus.objects.create(
            title="RC1", creator=cls.owner, label_set=cls.ls
        )
        cls.other = Corpus.objects.create(
            title="RC2", creator=cls.owner, label_set=cls.ls
        )
        cls.account = WorkerAccount.create_with_user(name="rw", creator=cls.owner)
        cls.token, cls.plaintext = CorpusAccessToken.create_token(
            worker_account=cls.account, corpus=cls.corpus
        )

    def _client(self) -> APIClient:
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.plaintext}")
        return c

    def _zip_upload(self):
        return io.BytesIO(_zip_bytes())

    def test_workerkey_zip_to_corpus_accepted(self):
        r = self._client().post(
            "/api/imports/zip-to-corpus/",
            {
                "file": self._zip_upload(),
                "corpus_id": str(self.corpus.pk),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertIn(r.status_code, (200, 202), r.content)
        self.assertTrue(r.json().get("ok"))

    def test_workerkey_wrong_corpus_forbidden(self):
        r = self._client().post(
            "/api/imports/zip-to-corpus/",
            {
                "file": self._zip_upload(),
                "corpus_id": to_global_id("CorpusType", self.other.pk),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertEqual(r.status_code, 403, r.content)

    def test_no_credentials_rejected(self):
        r = APIClient().post(
            "/api/imports/zip-to-corpus/",
            {"file": self._zip_upload(), "corpus_id": str(self.corpus.pk)},
            format="multipart",
        )
        self.assertIn(r.status_code, (401, 403), r.content)

    def test_workerkey_single_doc_add_to_folder_path(self):
        """``add_to_folder_path`` round-trips through ``POST /api/imports/
        documents/`` under WorkerKey auth, building the nested CorpusFolder tree
        under the token-bound corpus."""
        r = self._client().post(
            "/api/imports/documents/",
            {
                "file": io.BytesIO(_PDF),
                "filename": "x.pdf",
                "title": "x.pdf",
                "add_to_corpus_id": str(self.corpus.pk),
                "add_to_folder_path": "alpha/beta",
            },
            format="multipart",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json().get("ok"))
        leaf = CorpusFolder.objects.get(corpus=self.corpus, name="beta")
        self.assertEqual(leaf.parent.name, "alpha")
