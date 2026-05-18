"""
Regression tests for ``DocumentFilter.in_folder`` corpus-scoping.

Background
----------
Before the fix, ``in_folder("__root__")`` matched documents with a
``DocumentPath`` whose ``folder=NULL`` *anywhere in the database* and
left the corpus restriction entirely to the chained ``in_corpus``
filter. The two filters intersect on document IDs via ``id__in``, so a
document with a path in corpus A (under some folder) AND a path in
corpus B (at root) would falsely surface in corpus A's root view.

In production the corpus-isolated copy model keeps a Document's
``DocumentPath`` rows pinned to a single corpus, so the leak is rare —
but it can be triggered by ``add_document_to_corpus`` (the secondary
multi-corpus path used in the service layer for legacy data) or by
direct ``DocumentPath`` creation in tests / migrations.

The filter is now corpus-scoped at the subquery level (reads
``in_corpus_with_id`` from ``self.data``) so the inner ``DocumentPath``
restriction matches the outer corpus restriction, closing the leak.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()


class _Ctx:
    def __init__(self, user):
        self.user = user


class InFolderFilterCorpusScopeTest(TestCase):
    """``in_folder`` must restrict to the corpus selected by ``in_corpus``."""

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="x")
        self.corpus_a = Corpus.objects.create(title="A", creator=self.user)
        self.corpus_b = Corpus.objects.create(title="B", creator=self.user)
        self.folder_in_a = CorpusFolder.objects.create(
            name="Filings", corpus=self.corpus_a, creator=self.user
        )

        # ``shared`` has paths in BOTH corpora — folder=folder_in_a in
        # A, folder=NULL in B. Without corpus scoping, querying corpus
        # A's root would falsely return ``shared`` (via its B path).
        # Build the paths directly so each is the single owner of one
        # Document id (rather than corpus-isolated copies) and the
        # cross-corpus leak is reachable in test.
        self.shared = Document.objects.create(title="Shared", creator=self.user)
        DocumentPath.objects.create(
            document=self.shared,
            corpus=self.corpus_a,
            folder=self.folder_in_a,
            path="/shared-in-folder",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=self.shared,
            corpus=self.corpus_b,
            folder=None,
            path="/shared-at-root",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # A second doc that legitimately lives at corpus A root, to
        # prove the filter still returns true-positives.
        self.root_doc = Document.objects.create(title="RootOnly", creator=self.user)
        DocumentPath.objects.create(
            document=self.root_doc,
            corpus=self.corpus_a,
            folder=None,
            path="/root-only",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        self.client = Client(schema, context_value=_Ctx(self.user))
        self.corpus_a_gid = to_global_id("CorpusType", self.corpus_a.id)
        self.corpus_b_gid = to_global_id("CorpusType", self.corpus_b.id)
        self.folder_in_a_gid = to_global_id("CorpusFolderType", self.folder_in_a.id)

    def _titles(self, result):
        return sorted(
            edge["node"]["title"] for edge in result["data"]["documents"]["edges"]
        )

    def test_root_filter_excludes_cross_corpus_root_leak(self):
        query = """
        query($corpusId: String, $folderId: String) {
            documents(inCorpusWithId: $corpusId, inFolderId: $folderId, includeCaml: true) {
                edges { node { title } }
            }
        }
        """
        result = self.client.execute(
            query,
            variable_values={
                "corpusId": self.corpus_a_gid,
                "folderId": "__root__",
            },
        )
        # Without the fix, ``Shared`` would leak in because its
        # corpus-B path has folder=NULL.
        self.assertEqual(self._titles(result), ["RootOnly"])

    def test_folder_filter_returns_doc_assigned_to_that_folder(self):
        query = """
        query($corpusId: String, $folderId: String) {
            documents(inCorpusWithId: $corpusId, inFolderId: $folderId, includeCaml: true) {
                edges { node { title } }
            }
        }
        """
        result = self.client.execute(
            query,
            variable_values={
                "corpusId": self.corpus_a_gid,
                "folderId": self.folder_in_a_gid,
            },
        )
        self.assertEqual(self._titles(result), ["Shared"])

    def test_root_filter_returns_genuine_root_doc_in_other_corpus(self):
        # Sanity: the corpus restriction is symmetric. Querying corpus
        # B's root returns ``Shared`` (it's at root there).
        query = """
        query($corpusId: String, $folderId: String) {
            documents(inCorpusWithId: $corpusId, inFolderId: $folderId, includeCaml: true) {
                edges { node { title } }
            }
        }
        """
        result = self.client.execute(
            query,
            variable_values={
                "corpusId": self.corpus_b_gid,
                "folderId": "__root__",
            },
        )
        self.assertEqual(self._titles(result), ["Shared"])
