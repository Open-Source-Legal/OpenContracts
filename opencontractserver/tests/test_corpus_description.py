"""Canonical-CAML corpus description tests.

The legacy ``Corpus._markdown_to_plain_text`` / ``Corpus._summarize_for_preview``
unit tests have moved to ``test_corpus_description_cache.py`` (the helpers
were relocated to ``opencontractserver.corpuses.services.description_cache``
during the Canonical-CAML refactor). The ``Corpus.update_description``
in-place writer was removed in migration 0053; the canonical write path now
flows through :func:`CorpusService.update_description` →
:func:`opencontractserver.documents.versioning.import_document`. The classes
in this module cover the new contract end-to-end.
"""

from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import User


class UpdateDescriptionWritesThroughCamlTest(TestCase):
    """CorpusService.update_description must write via import_document.

    Task 8 of the Canonical-CAML Corpus Description Refactor (spec
    ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``
    §4.6): the editor's write path no longer mutates the legacy
    ``md_description`` FileField — it creates or extends the corpus's
    ``Readme.CAML`` Document version tree through
    :func:`opencontractserver.documents.versioning.import_document`. The
    Document ``post_save`` signal then cascades the cache refresh onto
    ``Corpus.description`` / ``.description_preview`` /
    ``.readme_caml_document_id``.
    """

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="utc-user", password="x")

    def test_update_description_creates_caml_doc_if_missing(self):
        from opencontractserver.corpuses.services.corpus_service import (
            CorpusService,
        )
        from opencontractserver.documents.models import DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        # The Readme.CAML cache cascade is wired via Document/DocumentPath
        # ``post_save`` + ``transaction.on_commit`` (see
        # ``opencontractserver/corpuses/signals.py``). Under ``TestCase``
        # the surrounding transaction never commits, so we wrap the call
        # in ``captureOnCommitCallbacks(execute=True)`` to run the
        # deferred refresh synchronously inside the assertion scope.
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(self.user, corpus, "# Hello\n\nWorld.")
        # Exactly one DocumentPath for Readme.CAML
        paths = DocumentPath.objects.filter(
            corpus=corpus, path="Readme.CAML", is_current=True
        )
        self.assertEqual(paths.count(), 1)
        head_path = paths.first()
        assert head_path is not None
        doc = head_path.document
        self.assertEqual(doc.title, "Readme.CAML")
        self.assertEqual(doc.file_type, "text/markdown")
        corpus.refresh_from_db()
        self.assertEqual(corpus.description, "Hello\n\nWorld.")

    def test_update_description_creates_version_tree_sibling_on_edit(self):
        from opencontractserver.corpuses.services.corpus_service import (
            CorpusService,
        )
        from opencontractserver.documents.models import Document, DocumentPath

        corpus = Corpus.objects.create(title="C", creator=self.user)
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(self.user, corpus, "v1 body")
        # Capture initial state
        first_head = DocumentPath.objects.get(
            corpus=corpus, path="Readme.CAML", is_current=True
        ).document
        tree_id = first_head.version_tree_id

        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(self.user, corpus, "v2 body")
        # New DocumentPath is now current; old one flipped to False
        current_paths = DocumentPath.objects.filter(
            corpus=corpus, path="Readme.CAML", is_current=True
        )
        self.assertEqual(current_paths.count(), 1)
        new_head_path = current_paths.first()
        assert new_head_path is not None
        new_head = new_head_path.document
        self.assertEqual(new_head.version_tree_id, tree_id)
        self.assertNotEqual(new_head.pk, first_head.pk)
        # Two versions in the version tree
        self.assertEqual(Document.objects.filter(version_tree_id=tree_id).count(), 2)

    def test_update_description_enforces_permission_for_non_creator(self):
        from opencontractserver.corpuses.services.corpus_service import (
            CorpusService,
        )

        intruder = User.objects.create_user(username="intruder", password="x")
        corpus = Corpus.objects.create(title="C", creator=self.user)
        # The existing CorpusService.update_description path gates on a
        # creator-only check. Verify the new wrapper still refuses the
        # write rather than silently routing it through import_document.
        result = CorpusService.update_description(intruder, corpus, "# Hijack")
        self.assertFalse(result.ok)
        self.assertIn("permission", result.error.lower())


class DescriptionRevisionsReadsFromVersionTreeTest(TestCase):
    """descriptionRevisions resolves from the Readme.CAML version_tree.

    Task 9 of the canonical-CAML refactor (spec §4.5): the GraphQL
    ``descriptionRevisions`` field on ``CorpusType`` now lists the
    corpus's Readme.CAML version-tree siblings instead of the legacy
    ``CorpusDescriptionRevision`` rows. The frontend revision-history
    viewer reads ``id``, ``version``, ``author``, ``snapshot``, and
    ``created`` from each entry; the resolver shape preserves all five
    even though the underlying instance is now a ``Document``.
    """

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dvt", password="x")

    def setUp(self):
        from opencontractserver.corpuses.services.corpus_service import (
            CorpusService,
        )

        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        # Three successive edits → three version-tree siblings. The CAML
        # write path defers cache refresh via transaction.on_commit, so
        # wrap each call in captureOnCommitCallbacks(execute=True) to
        # run the deferred hooks synchronously inside the TestCase
        # transaction.
        for body in ("v1 body", "v2 body", "v3 body"):
            with self.captureOnCommitCallbacks(execute=True):
                CorpusService.update_description(self.user, self.corpus, body)
        self.corpus.refresh_from_db()

    def test_revisions_list_pulls_from_caml_version_tree(self):
        from config.graphql.corpus_types import CorpusType

        revs = CorpusType.resolve_description_revisions(self.corpus, None)
        # 3 edits → 3 version-tree siblings
        self.assertEqual(len(revs), 3)

    def test_revisions_newest_first_ordering(self):
        """The list is ordered newest-first (matches the frontend
        modal which sorts by version desc but expects the array head
        to be the most recent entry)."""
        from config.graphql.corpus_types import CorpusType

        revs = CorpusType.resolve_description_revisions(self.corpus, None)
        timestamps = [rev.created for rev in revs]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    def test_revision_facade_exposes_legacy_shape(self):
        """Each Document sibling must expose the historical revision
        fields via the ``CorpusDescriptionRevisionType`` facade
        resolvers — id, version, author, snapshot, created — so the
        frontend viewer keeps rendering."""
        from config.graphql.corpus_types import (
            CorpusDescriptionRevisionType,
            CorpusType,
        )

        revs = CorpusType.resolve_description_revisions(self.corpus, None)
        # Each rev is a Document — confirm the facade resolvers map the
        # Document attributes onto the legacy field names.
        for rev in revs:
            self.assertEqual(
                CorpusDescriptionRevisionType.resolve_id(rev, None), rev.pk
            )
            self.assertIs(
                CorpusDescriptionRevisionType.resolve_author(rev, None), rev.creator
            )
            self.assertEqual(
                CorpusDescriptionRevisionType.resolve_created(rev, None),
                rev.created,
            )
            # version is 1-indexed within the tree; for 3 siblings it
            # must be in {1,2,3}.
            self.assertIn(
                CorpusDescriptionRevisionType.resolve_version(rev, None),
                {1, 2, 3},
            )

    def test_revision_snapshot_reads_txt_extract_file_body(self):
        """``snapshot`` reads the Document's ``txt_extract_file`` body
        on demand via the shared ``read_caml_body`` helper."""
        from config.graphql.corpus_types import (
            CorpusDescriptionRevisionType,
            CorpusType,
        )

        revs = CorpusType.resolve_description_revisions(self.corpus, None)
        bodies = {
            CorpusDescriptionRevisionType.resolve_snapshot(rev, None) for rev in revs
        }
        # All three edits should be retrievable as snapshots.
        self.assertSetEqual(bodies, {"v1 body", "v2 body", "v3 body"})

    def test_version_is_1_indexed_and_unique_oldest_first(self):
        """The 1-indexed version counter must mirror the legacy
        ``CorpusDescriptionRevision.version`` semantic — oldest = 1,
        newest = N — so the frontend "Version N" label stays stable."""
        from config.graphql.corpus_types import (
            CorpusDescriptionRevisionType,
            CorpusType,
        )

        revs = CorpusType.resolve_description_revisions(self.corpus, None)
        # Revs are newest-first; reverse to get oldest-first.
        oldest_first = list(reversed(revs))
        versions = [
            CorpusDescriptionRevisionType.resolve_version(rev, None)
            for rev in oldest_first
        ]
        self.assertEqual(versions, [1, 2, 3])

    def test_empty_when_corpus_has_no_caml_document(self):
        """A fresh corpus with no Readme.CAML doc returns the empty
        list (must not raise on ``readme_caml_document_id is None``)."""
        from config.graphql.corpus_types import CorpusType

        bare = Corpus.objects.create(title="Bare", creator=self.user)
        self.assertEqual(CorpusType.resolve_description_revisions(bare, None), [])
