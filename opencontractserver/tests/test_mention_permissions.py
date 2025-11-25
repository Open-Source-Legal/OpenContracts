"""
Tests for @ mention permission filtering.

Tests verify that mention autocomplete (corpus and document searches) properly
enforce write-permission-required model for private resources while allowing
public resource mentions with read access.

See: docs/permissioning/mention_permissioning_spec.md
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusMentionPermissionTestCase(TestCase):
    """Test corpus mention autocomplete respects write permissions."""

    def setUp(self):
        """Create test users and corpuses."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.contributor = User.objects.create_user(
            username="contributor", password="test"
        )
        self.viewer = User.objects.create_user(username="viewer", password="test")
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Private corpus owned by owner
        self.private_corpus = Corpus.objects.create(
            title="Private Legal Corpus",
            description="Confidential legal documents",
            creator=self.owner,
            is_public=False,
        )

        # Public corpus
        self.public_corpus = Corpus.objects.create(
            title="Public Legal Corpus",
            description="Open legal resources",
            creator=self.owner,
            is_public=True,
        )

        # Give contributor write permission on private corpus
        set_permissions_for_obj_to_user(
            self.contributor, self.private_corpus, [PermissionTypes.UPDATE]
        )

        # Give viewer only read permission on private corpus
        set_permissions_for_obj_to_user(
            self.viewer, self.private_corpus, [PermissionTypes.READ]
        )

    def test_owner_can_mention_own_corpus(self):
        """Owner can mention their own private corpus."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.owner

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_ids = [c.id for c in results]
        self.assertIn(
            self.private_corpus.id,
            corpus_ids,
            "Owner should be able to mention their own corpus",
        )
        self.assertIn(
            self.public_corpus.id,
            corpus_ids,
            "Owner should be able to mention public corpus",
        )

    def test_contributor_with_write_permission_can_mention(self):
        """User with write permission can mention private corpus."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.contributor

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_ids = [c.id for c in results]
        self.assertIn(
            self.private_corpus.id,
            corpus_ids,
            "Contributor with write permission should be able to mention corpus",
        )
        self.assertIn(
            self.public_corpus.id,
            corpus_ids,
            "Contributor should be able to mention public corpus",
        )

    def test_viewer_with_read_only_cannot_mention_private(self):
        """User with only read permission CANNOT mention private corpus."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.viewer

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_ids = [c.id for c in results]
        self.assertNotIn(
            self.private_corpus.id,
            corpus_ids,
            "Viewer with read-only permission should NOT be able to mention private corpus",
        )
        self.assertIn(
            self.public_corpus.id,
            corpus_ids,
            "Viewer should still be able to mention public corpus",
        )

    def test_outsider_cannot_mention_private_corpus(self):
        """User with no permission cannot mention private corpus."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.outsider

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_ids = [c.id for c in results]
        self.assertNotIn(
            self.private_corpus.id,
            corpus_ids,
            "Outsider should NOT be able to mention private corpus",
        )
        self.assertIn(
            self.public_corpus.id,
            corpus_ids,
            "Outsider should be able to mention public corpus",
        )

    def test_anonymous_user_cannot_mention(self):
        """Anonymous users cannot mention any corpus."""
        from django.contrib.auth.models import AnonymousUser

        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = AnonymousUser()

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        self.assertEqual(
            len(list(results)),
            0,
            "Anonymous users should not be able to mention any corpus",
        )

    def test_superuser_can_mention_all(self):
        """Superusers can mention all corpuses."""
        superuser = User.objects.create_superuser(
            username="super", password="test", email="super@test.com"
        )

        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = superuser

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_ids = [c.id for c in results]
        self.assertIn(
            self.private_corpus.id, corpus_ids, "Superuser should see private corpus"
        )
        self.assertIn(
            self.public_corpus.id, corpus_ids, "Superuser should see public corpus"
        )

    def test_create_permission_allows_mention(self):
        """CREATE permission is sufficient to mention (write permission)."""
        creator_user = User.objects.create_user(
            username="creator_user", password="test"
        )
        set_permissions_for_obj_to_user(
            creator_user, self.private_corpus, [PermissionTypes.CREATE]
        )

        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = creator_user

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_ids = [c.id for c in results]
        self.assertIn(
            self.private_corpus.id,
            corpus_ids,
            "User with CREATE permission should be able to mention",
        )

    def test_delete_permission_allows_mention(self):
        """DELETE permission is sufficient to mention (write permission)."""
        deleter_user = User.objects.create_user(
            username="deleter_user", password="test"
        )
        set_permissions_for_obj_to_user(
            deleter_user, self.private_corpus, [PermissionTypes.DELETE]
        )

        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = deleter_user

            context = MockContext()

        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Legal"
        )

        corpus_titles = [c.title for c in results]
        self.assertIn(
            self.private_corpus.title,
            corpus_titles,
            "User with DELETE permission should be able to mention",
        )


class DocumentMentionPermissionTestCase(TestCase):
    """Test document mention autocomplete respects write permissions."""

    def setUp(self):
        """Create test users, corpuses, and documents."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.corpus_contributor = User.objects.create_user(
            username="corpus_contributor", password="test"
        )
        self.doc_contributor = User.objects.create_user(
            username="doc_contributor", password="test"
        )
        self.viewer = User.objects.create_user(username="viewer", password="test")
        self.outsider = User.objects.create_user(username="outsider", password="test")

        # Private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

        # Public corpus
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )

        # Private document in private corpus (using ManyToMany)
        self.private_doc_in_private_corpus = Document.objects.create(
            title="Private Contract",
            description="Confidential contract",
            creator=self.owner,
            is_public=False,
        )
        self.private_doc_in_private_corpus, _, _ = self.private_corpus.add_document(
            document=self.private_doc_in_private_corpus, user=self.owner
        )

        # Private document in public corpus (using ManyToMany)
        self.private_doc_in_public_corpus = Document.objects.create(
            title="Draft Document",
            description="Work in progress",
            creator=self.owner,
            is_public=False,
        )
        self.private_doc_in_public_corpus, _, _ = self.public_corpus.add_document(
            document=self.private_doc_in_public_corpus, user=self.owner
        )

        # Public document in public corpus (using ManyToMany)
        self.public_doc_in_public_corpus = Document.objects.create(
            title="Public Template",
            description="Open template",
            creator=self.owner,
            is_public=True,
        )
        self.public_doc_in_public_corpus, _, _ = self.public_corpus.add_document(
            document=self.public_doc_in_public_corpus, user=self.owner
        )

        # Standalone public document (no corpus)
        self.standalone_public_doc = Document.objects.create(
            title="Public Guide",
            description="Open guide",
            creator=self.owner,
            is_public=True,
        )

        # Standalone private document (no corpus)
        self.standalone_private_doc = Document.objects.create(
            title="Private Note",
            description="Personal note",
            creator=self.owner,
            is_public=False,
        )

        # Give corpus_contributor write permission on private corpus
        set_permissions_for_obj_to_user(
            self.corpus_contributor, self.private_corpus, [PermissionTypes.UPDATE]
        )

        # Give doc_contributor write permission on private_doc_in_private_corpus
        set_permissions_for_obj_to_user(
            self.doc_contributor,
            self.private_doc_in_private_corpus,
            [PermissionTypes.UPDATE],
        )

        # Give viewer read permission on private corpus and private doc
        set_permissions_for_obj_to_user(
            self.viewer, self.private_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.viewer, self.private_doc_in_private_corpus, [PermissionTypes.READ]
        )

    def test_owner_can_mention_own_documents(self):
        """Owner can mention all their own documents."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.owner

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        doc_ids = [d.id for d in results]
        self.assertIn(
            self.private_doc_in_private_corpus.id,
            doc_ids,
            "Owner should be able to mention private doc in private corpus",
        )
        self.assertIn(
            self.private_doc_in_public_corpus.id,
            doc_ids,
            "Owner should be able to mention private doc in public corpus",
        )
        self.assertIn(
            self.public_doc_in_public_corpus.id,
            doc_ids,
            "Owner should be able to mention public doc",
        )
        self.assertIn(
            self.standalone_public_doc.id,
            doc_ids,
            "Owner should be able to mention standalone public doc",
        )
        self.assertIn(
            self.standalone_private_doc.id,
            doc_ids,
            "Owner should be able to mention standalone private doc",
        )

    def test_corpus_write_permission_grants_document_mention(self):
        """Write permission on corpus grants mention access to documents in that corpus."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.corpus_contributor

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        doc_titles = [d.title for d in results]

        self.assertIn(
            self.private_doc_in_private_corpus.title,
            doc_titles,
            f"Corpus contributor should be able to mention docs in writable corpus. Found: {doc_titles}",
        )
        self.assertIn(
            self.public_doc_in_public_corpus.title,
            doc_titles,
            "Corpus contributor should be able to mention public docs",
        )

    def test_document_write_permission_allows_mention(self):
        """Direct write permission on document allows mention."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.doc_contributor

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        doc_ids = [d.id for d in results]
        self.assertIn(
            self.private_doc_in_private_corpus.id,
            doc_ids,
            "User with doc write permission should be able to mention it",
        )

    def test_viewer_with_read_only_cannot_mention_private_doc(self):
        """User with only read permission CANNOT mention private documents."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.viewer

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        doc_ids = [d.id for d in results]
        self.assertNotIn(
            self.private_doc_in_private_corpus.id,
            doc_ids,
            "Viewer with read-only should NOT be able to mention private doc",
        )
        self.assertNotIn(
            self.private_doc_in_public_corpus.id,
            doc_ids,
            "Viewer should NOT be able to mention private doc even in public corpus",
        )

    def test_public_documents_mentionable_by_all(self):
        """Public documents can be mentioned by any authenticated user."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.outsider

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        doc_ids = [d.id for d in results]
        self.assertIn(
            self.public_doc_in_public_corpus.id,
            doc_ids,
            "Outsider should be able to mention public doc in public corpus",
        )
        self.assertIn(
            self.standalone_public_doc.id,
            doc_ids,
            "Outsider should be able to mention standalone public doc",
        )
        self.assertNotIn(
            self.private_doc_in_private_corpus.id,
            doc_ids,
            "Outsider should NOT be able to mention private docs",
        )

    def test_anonymous_user_cannot_mention_documents(self):
        """Anonymous users cannot mention any document."""
        from django.contrib.auth.models import AnonymousUser

        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = AnonymousUser()

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        self.assertEqual(
            len(list(results)),
            0,
            "Anonymous users should not be able to mention any document",
        )

    def test_superuser_can_mention_all_documents(self):
        """Superusers can mention all documents."""
        superuser = User.objects.create_superuser(
            username="super", password="test", email="super@test.com"
        )

        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = superuser

            context = MockContext()

        results = query.resolve_search_documents_for_mention(MockInfo(), text_search="")

        doc_ids = [d.id for d in results]
        self.assertIn(
            self.private_doc_in_private_corpus.id,
            doc_ids,
            "Superuser should see all documents",
        )
        self.assertIn(
            self.standalone_private_doc.id,
            doc_ids,
            "Superuser should see all documents",
        )


class MentionIDORProtectionTestCase(TestCase):
    """Test IDOR protection - no information leakage about inaccessible resources."""

    def setUp(self):
        """Create test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.attacker = User.objects.create_user(username="attacker", password="test")

        self.private_corpus = Corpus.objects.create(
            title="Secret Project", creator=self.owner, is_public=False
        )

        self.private_doc = Document.objects.create(
            title="Confidential Plan", creator=self.owner, is_public=False
        )

    def test_inaccessible_corpus_not_in_autocomplete(self):
        """Attacker cannot discover private corpus through autocomplete."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.attacker

            context = MockContext()

        # Try to search for the private corpus
        results = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Secret"
        )

        corpus_ids = [c.id for c in results]
        self.assertNotIn(
            self.private_corpus.id,
            corpus_ids,
            "Private corpus should not appear in attacker's autocomplete",
        )

        # Verify it's completely hidden (not even with exact title match)
        results_exact = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Secret Project"
        )
        corpus_ids_exact = [c.id for c in results_exact]
        self.assertNotIn(
            self.private_corpus.id,
            corpus_ids_exact,
            "Private corpus should not appear even with exact title match",
        )

    def test_inaccessible_document_not_in_autocomplete(self):
        """Attacker cannot discover private document through autocomplete."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.attacker

            context = MockContext()

        # Try to search for the private document
        results = query.resolve_search_documents_for_mention(
            MockInfo(), text_search="Confidential"
        )

        doc_ids = [d.id for d in results]
        self.assertNotIn(
            self.private_doc.id,
            doc_ids,
            "Private document should not appear in attacker's autocomplete",
        )

        # Verify it's completely hidden (not even with exact title match)
        results_exact = query.resolve_search_documents_for_mention(
            MockInfo(), text_search="Confidential Plan"
        )
        doc_ids_exact = [d.id for d in results_exact]
        self.assertNotIn(
            self.private_doc.id,
            doc_ids_exact,
            "Private document should not appear even with exact title match",
        )

    def test_empty_autocomplete_reveals_no_information(self):
        """Empty autocomplete results don't reveal whether resources exist."""
        from config.graphql.queries import Query

        query = Query()

        class MockInfo:
            class MockContext:
                user = self.attacker

            context = MockContext()

        # Search for non-existent corpus
        results_nonexistent = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="NonExistentCorpus12345"
        )

        # Search for private corpus (exists but inaccessible)
        results_inaccessible = query.resolve_search_corpuses_for_mention(
            MockInfo(), text_search="Secret Project"
        )

        # Both should return empty results - no way to distinguish
        self.assertEqual(
            len(list(results_nonexistent)),
            0,
            "Non-existent corpus returns empty results",
        )
        self.assertEqual(
            len(list(results_inaccessible)),
            0,
            "Inaccessible corpus returns empty results",
        )

        # Attacker cannot tell the difference between non-existent and inaccessible
