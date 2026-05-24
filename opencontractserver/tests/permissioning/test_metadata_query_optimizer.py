"""
Comprehensive tests for MetadataService permission filtering.

This test suite covers:

1. MetadataService._compute_effective_permissions()
   - Tests MIN(document_permission, corpus_permission) logic for READ
   - Tests superuser, anonymous, and authenticated user handling

2. MetadataService.get_corpus_metadata_columns()
   - Tests column retrieval with corpus permission filtering
   - Tests manual_only parameter

3. MetadataService.get_document_metadata()
   - Tests single document metadata retrieval
   - Tests document + corpus permission requirements

4. MetadataService.get_documents_metadata_batch()
   - Tests batch metadata retrieval (N+1 fix)
   - Tests permission filtering across multiple documents
   - Tests that only readable documents are included

5. MetadataService.get_metadata_completion_status()
   - Tests completion percentage calculation
   - Tests required field detection

6. MetadataService.check_metadata_mutation_permission()
   - Tests UPDATE/DELETE permission checks
   - Tests corpus-primary model: Corpus UPDATE + Doc READ = can edit
   - NOTE: Metadata differs from annotations - corpus permission controls
     write access, not MIN(doc, corpus) logic

7. MetadataService.validate_metadata_column()
   - Tests column validation for corpus schema
   - Tests manual entry requirement
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.extracts.services import MetadataService
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


class MetadataServiceTestCase(TestCase):
    """
    Tests for MetadataService permission handling.
    """

    def setUp(self):
        """Set up test scenario with documents, corpus, and metadata schema."""
        logger.info("\n" + "=" * 80)
        logger.info("SETTING UP METADATA QUERY OPTIMIZER TEST")
        logger.info("=" * 80)

        # Create users
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="test123"
        )
        self.stranger = User.objects.create_user(
            username="stranger", password="test123"
        )
        self.superuser = User.objects.create_superuser(
            username="superuser", password="admin"
        )
        self.anonymous = AnonymousUser()

        # Create documents
        self.doc1 = self._create_document("Doc 1", self.owner)
        self.doc2 = self._create_document("Doc 2", self.owner)
        self.public_doc = self._create_document(
            "Public Doc", self.owner, is_public=True
        )

        # Create corpus (private by default)
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.corpus.add_document(document=self.doc1, user=self.owner)
        self.corpus.add_document(document=self.doc2, user=self.owner)
        # Owner needs explicit permissions on corpus
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Create public corpus
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.public_corpus.add_document(document=self.public_doc, user=self.owner)
        # Owner needs explicit permissions on public corpus too
        set_permissions_for_obj_to_user(
            self.owner, self.public_corpus, [PermissionTypes.CRUD]
        )

        # Set up permissions for collaborator on doc1 and corpus
        set_permissions_for_obj_to_user(
            self.collaborator, self.doc1, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.corpus, [PermissionTypes.READ]
        )

        # Create metadata schema (fieldset + columns)
        self.fieldset = Fieldset.objects.create(
            name="Test Metadata Schema",
            description="Metadata for test corpus",
            corpus=self.corpus,
            creator=self.owner,
        )

        self.column1 = Column.objects.create(
            name="Contract Type",
            fieldset=self.fieldset,
            data_type="STRING",
            output_type="string",
            is_manual_entry=True,
            display_order=0,
            validation_config={"required": True},
            creator=self.owner,
        )
        self.column2 = Column.objects.create(
            name="Effective Date",
            fieldset=self.fieldset,
            data_type="DATE",
            output_type="date",
            is_manual_entry=True,
            display_order=1,
            creator=self.owner,
        )
        self.column3 = Column.objects.create(
            name="Extracted Field",
            fieldset=self.fieldset,
            data_type="STRING",
            output_type="string",
            is_manual_entry=False,  # Not manual entry
            display_order=2,
            creator=self.owner,
        )

        # Create public corpus metadata schema
        self.public_fieldset = Fieldset.objects.create(
            name="Public Metadata Schema",
            description="Public metadata schema",
            corpus=self.public_corpus,
            creator=self.owner,
        )
        self.public_column = Column.objects.create(
            name="Public Field",
            fieldset=self.public_fieldset,
            data_type="STRING",
            output_type="string",
            is_manual_entry=True,
            creator=self.owner,
        )

        # Create datacells (metadata values)
        self.datacell1 = Datacell.objects.create(
            document=self.doc1,
            column=self.column1,
            data={"value": "NDA"},
            data_definition="string",
            creator=self.owner,
        )
        self.datacell2 = Datacell.objects.create(
            document=self.doc1,
            column=self.column2,
            data={"value": "2024-01-15"},
            data_definition="date",
            creator=self.owner,
        )
        # doc2 only has one field filled
        self.datacell3 = Datacell.objects.create(
            document=self.doc2,
            column=self.column1,
            data={"value": "MSA"},
            data_definition="string",
            creator=self.owner,
        )

        logger.info("Test setup complete")

    def _create_document(self, title, creator, is_public=False):
        """Helper to create a document with a PDF file."""
        with open(SAMPLE_PDF_FILE_ONE_PATH, "rb") as f:
            pdf_content = f.read()

        doc = Document.objects.create(
            title=title,
            creator=creator,
            is_public=is_public,
            pdf_file=ContentFile(pdf_content, name=f"{title}.pdf"),
        )
        set_permissions_for_obj_to_user(creator, doc, [PermissionTypes.CRUD])
        return doc

    # =========================================================================
    # Tests for _compute_effective_permissions
    # =========================================================================

    def test_compute_permissions_superuser_has_all(self):
        """Superuser should have all permissions."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.superuser, self.doc1.id, self.corpus.id
            )
        )
        self.assertTrue(can_read)
        self.assertTrue(can_create)
        self.assertTrue(can_update)
        self.assertTrue(can_delete)

    def test_compute_permissions_anonymous_no_access_private(self):
        """Anonymous user should not access private document/corpus."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.anonymous, self.doc1.id, self.corpus.id
            )
        )
        self.assertFalse(can_read)
        self.assertFalse(can_create)
        self.assertFalse(can_update)
        self.assertFalse(can_delete)

    def test_compute_permissions_anonymous_read_public(self):
        """Anonymous user should have read access to public document/corpus."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.anonymous, self.public_doc.id, self.public_corpus.id
            )
        )
        self.assertTrue(can_read)
        self.assertFalse(can_create)
        self.assertFalse(can_update)
        self.assertFalse(can_delete)

    def test_compute_permissions_owner_has_all(self):
        """Owner should have all permissions on their document/corpus."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.owner, self.doc1.id, self.corpus.id
            )
        )
        self.assertTrue(can_read)
        self.assertTrue(can_create)
        self.assertTrue(can_update)
        self.assertTrue(can_delete)

    def test_compute_permissions_collaborator_read_only(self):
        """Collaborator with READ permission should only have read access."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.collaborator, self.doc1.id, self.corpus.id
            )
        )
        self.assertTrue(can_read)
        self.assertFalse(can_create)
        self.assertFalse(can_update)
        self.assertFalse(can_delete)

    def test_compute_permissions_stranger_no_access(self):
        """Stranger should have no access to private document/corpus."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.stranger, self.doc1.id, self.corpus.id
            )
        )
        self.assertFalse(can_read)
        self.assertFalse(can_create)
        self.assertFalse(can_update)
        self.assertFalse(can_delete)

    def test_compute_permissions_min_logic_doc_yes_corpus_no(self):
        """
        MIN logic: If user has doc permission but not corpus permission,
        effective permission should be denied.
        """
        # Give stranger READ on doc1 but not corpus
        set_permissions_for_obj_to_user(
            self.stranger, self.doc1, [PermissionTypes.READ]
        )

        can_read, _, _, _ = MetadataService._compute_effective_permissions(
            self.stranger, self.doc1.id, self.corpus.id
        )
        # Should be False because stranger doesn't have corpus permission
        self.assertFalse(can_read)

    def test_compute_permissions_nonexistent_document(self):
        """Should return no permissions for nonexistent document."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.owner, 99999, self.corpus.id
            )
        )
        self.assertFalse(can_read)

    def test_compute_permissions_nonexistent_corpus(self):
        """Should return no permissions for nonexistent corpus."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.owner, self.doc1.id, 99999
            )
        )
        self.assertFalse(can_read)

    def test_compute_permissions_query_count_superuser_is_zero(self):
        """Superuser short-circuit must not touch the database (issue #1690)."""
        with self.assertNumQueries(0):
            MetadataService._compute_effective_permissions(
                self.superuser, self.doc1.id, self.corpus.id
            )

    def test_compute_permissions_query_count_collaborator_is_bounded(self):
        """
        Regression for issue #1690: the legacy implementation issued 4
        ``user_can`` calls per object (8 total). Each call could enter
        the guardian fetch path independently. The new implementation
        collapses this to at most one ``get_users_permissions_for_obj``
        per object, plus the two ``Model.objects.get`` lookups. Lock the
        budget here so any future reintroduction of per-permission
        fan-out fails CI.

        Observed warm-path cost is 14 queries: 1 ``Model.objects.get``
        + 6 ``get_users_permissions_for_obj`` queries (ContentType +
        auth_permission codenames + user object perms + user groups +
        group object perms x2) per object, x2 objects. Tier-2 batching
        in sister issue #1691 will collapse the duplicated ContentType /
        auth_group lookups by threading a ``request`` through this code
        path.
        """
        # Warm any process-level caches (content type lookups, etc.)
        # that aren't part of the per-invocation work we want to bound.
        MetadataService._compute_effective_permissions(
            self.collaborator, self.doc1.id, self.corpus.id
        )

        with self.assertNumQueries(14):
            can_read, _, _, _ = MetadataService._compute_effective_permissions(
                self.collaborator, self.doc1.id, self.corpus.id
            )
        self.assertTrue(can_read)

    # =========================================================================
    # Tests for get_corpus_metadata_columns
    # =========================================================================

    def test_get_columns_owner_sees_manual_only(self):
        """Owner should see manual entry columns only by default."""
        columns = MetadataService.get_corpus_metadata_columns(
            self.owner, self.corpus.id, manual_only=True
        )
        self.assertEqual(columns.count(), 2)  # column1 and column2
        column_names = list(columns.values_list("name", flat=True))
        self.assertIn("Contract Type", column_names)
        self.assertIn("Effective Date", column_names)
        self.assertNotIn("Extracted Field", column_names)

    def test_get_columns_owner_sees_all(self):
        """Owner should see all columns when manual_only=False."""
        columns = MetadataService.get_corpus_metadata_columns(
            self.owner, self.corpus.id, manual_only=False
        )
        self.assertEqual(columns.count(), 3)

    def test_get_columns_collaborator_sees_columns(self):
        """Collaborator with READ permission should see columns."""
        columns = MetadataService.get_corpus_metadata_columns(
            self.collaborator, self.corpus.id
        )
        self.assertEqual(columns.count(), 2)

    def test_get_columns_stranger_no_access(self):
        """Stranger should not see any columns for private corpus."""
        columns = MetadataService.get_corpus_metadata_columns(
            self.stranger, self.corpus.id
        )
        self.assertEqual(columns.count(), 0)

    def test_get_columns_anonymous_public_corpus(self):
        """Anonymous user should see columns for public corpus."""
        columns = MetadataService.get_corpus_metadata_columns(
            self.anonymous, self.public_corpus.id
        )
        self.assertEqual(columns.count(), 1)

    def test_get_columns_ordered_by_display_order(self):
        """Columns should be ordered by display_order."""
        columns = list(
            MetadataService.get_corpus_metadata_columns(self.owner, self.corpus.id)
        )
        self.assertEqual(columns[0].display_order, 0)
        self.assertEqual(columns[1].display_order, 1)

    def test_get_columns_no_schema(self):
        """Should return empty for corpus without metadata schema."""
        corpus_no_schema = Corpus.objects.create(title="No Schema", creator=self.owner)
        # Grant permissions so we hit the "no schema" branch, not the "no permission" branch
        set_permissions_for_obj_to_user(
            self.owner, corpus_no_schema, [PermissionTypes.READ]
        )
        columns = MetadataService.get_corpus_metadata_columns(
            self.owner, corpus_no_schema.id
        )
        self.assertEqual(columns.count(), 0)

    # =========================================================================
    # Tests for get_document_metadata
    # =========================================================================

    def test_get_document_metadata_owner(self):
        """Owner should see all metadata for their document."""
        datacells = MetadataService.get_document_metadata(
            self.owner, self.doc1.id, self.corpus.id
        )
        self.assertEqual(datacells.count(), 2)

    def test_get_document_metadata_collaborator(self):
        """Collaborator with READ should see metadata."""
        datacells = MetadataService.get_document_metadata(
            self.collaborator, self.doc1.id, self.corpus.id
        )
        self.assertEqual(datacells.count(), 2)

    def test_get_document_metadata_stranger_no_access(self):
        """Stranger should not see metadata."""
        datacells = MetadataService.get_document_metadata(
            self.stranger, self.doc1.id, self.corpus.id
        )
        self.assertEqual(datacells.count(), 0)

    def test_get_document_metadata_includes_column_relation(self):
        """Datacells should have column relation loaded."""
        datacells = MetadataService.get_document_metadata(
            self.owner, self.doc1.id, self.corpus.id
        )
        for dc in datacells:
            # Should not cause additional query (select_related)
            self.assertIsNotNone(dc.column)
            self.assertIsNotNone(dc.column.name)

    # =========================================================================
    # Tests for get_documents_metadata_batch
    # =========================================================================

    def test_batch_owner_gets_all_documents(self):
        """Owner should get metadata for all requested documents."""
        result = MetadataService.get_documents_metadata_batch(
            self.owner, [self.doc1.id, self.doc2.id], self.corpus.id
        )
        self.assertIn(self.doc1.id, result)
        self.assertIn(self.doc2.id, result)
        self.assertEqual(len(result[self.doc1.id]), 2)  # 2 datacells
        self.assertEqual(len(result[self.doc2.id]), 1)  # 1 datacell

    def test_batch_collaborator_sees_only_permitted_docs(self):
        """Collaborator should only see docs they have permission for."""
        result = MetadataService.get_documents_metadata_batch(
            self.collaborator, [self.doc1.id, self.doc2.id], self.corpus.id
        )
        # Collaborator has permission on doc1 only
        self.assertIn(self.doc1.id, result)
        self.assertNotIn(self.doc2.id, result)

    def test_batch_stranger_no_access(self):
        """Stranger should not see any documents."""
        result = MetadataService.get_documents_metadata_batch(
            self.stranger, [self.doc1.id, self.doc2.id], self.corpus.id
        )
        self.assertEqual(len(result), 0)

    def test_batch_superuser_sees_all(self):
        """Superuser should see all documents."""
        result = MetadataService.get_documents_metadata_batch(
            self.superuser, [self.doc1.id, self.doc2.id], self.corpus.id
        )
        self.assertEqual(len(result), 2)

    def test_batch_empty_list(self):
        """Empty document list should return empty result."""
        result = MetadataService.get_documents_metadata_batch(
            self.owner, [], self.corpus.id
        )
        self.assertEqual(len(result), 0)

    def test_batch_no_corpus_permission(self):
        """Should return empty if user lacks corpus permission."""
        # Create user with doc permission but no corpus permission
        user = User.objects.create_user(username="doconly", password="test")
        set_permissions_for_obj_to_user(user, self.doc1, [PermissionTypes.READ])

        result = MetadataService.get_documents_metadata_batch(
            user, [self.doc1.id], self.corpus.id
        )
        self.assertEqual(len(result), 0)

    def test_batch_includes_docs_with_no_metadata(self):
        """
        Documents with permission but no metadata should still be in result
        (with empty datacells list).
        """
        # Create a new document with no metadata
        doc3 = self._create_document("Doc 3", self.owner)
        self.corpus.add_document(document=doc3, user=self.owner)

        result = MetadataService.get_documents_metadata_batch(
            self.owner, [self.doc1.id, doc3.id], self.corpus.id
        )
        self.assertIn(doc3.id, result)
        self.assertEqual(len(result[doc3.id]), 0)

    # =========================================================================
    # Tests for get_metadata_completion_status
    # =========================================================================

    def test_completion_status_fully_filled(self):
        """Document with all fields filled should show 100%."""
        status = MetadataService.get_metadata_completion_status(
            self.owner, self.doc1.id, self.corpus.id
        )
        assert status is not None
        self.assertEqual(status["total_fields"], 2)
        self.assertEqual(status["filled_fields"], 2)
        self.assertEqual(status["missing_fields"], 0)
        self.assertEqual(status["percentage"], 100.0)
        self.assertEqual(status["missing_required"], [])

    def test_completion_status_partially_filled(self):
        """Document with some fields filled should show correct percentage."""
        status = MetadataService.get_metadata_completion_status(
            self.owner, self.doc2.id, self.corpus.id
        )
        assert status is not None
        self.assertEqual(status["total_fields"], 2)
        self.assertEqual(status["filled_fields"], 1)
        self.assertEqual(status["missing_fields"], 1)
        self.assertEqual(status["percentage"], 50.0)

    def test_completion_status_missing_required(self):
        """Should report missing required fields."""
        # Create a document with no metadata
        doc3 = self._create_document("Doc 3", self.owner)
        self.corpus.add_document(document=doc3, user=self.owner)

        status = MetadataService.get_metadata_completion_status(
            self.owner, doc3.id, self.corpus.id
        )
        assert status is not None
        self.assertIn("Contract Type", status["missing_required"])

    def test_completion_status_no_permission(self):
        """Stranger should get None for completion status."""
        status = MetadataService.get_metadata_completion_status(
            self.stranger, self.doc1.id, self.corpus.id
        )
        self.assertIsNone(status)

    def test_completion_status_no_schema(self):
        """Corpus without schema should return 100% completion."""
        corpus_no_schema = Corpus.objects.create(title="No Schema", creator=self.owner)
        doc = self._create_document("Test", self.owner)
        corpus_no_schema.add_document(document=doc, user=self.owner)
        set_permissions_for_obj_to_user(
            self.owner, corpus_no_schema, [PermissionTypes.CRUD]
        )

        status = MetadataService.get_metadata_completion_status(
            self.owner, doc.id, corpus_no_schema.id
        )
        assert status is not None
        self.assertEqual(status["total_fields"], 0)
        self.assertEqual(status["percentage"], 100.0)

    # =========================================================================
    # Tests for check_metadata_mutation_permission
    # =========================================================================

    def test_mutation_permission_superuser(self):
        """Superuser should always have mutation permission."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.superuser, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertTrue(has_perm)
        self.assertEqual(msg, "")

    def test_mutation_permission_anonymous(self):
        """Anonymous user should be denied mutation permission."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.anonymous, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertFalse(has_perm)
        self.assertEqual(msg, "Authentication required")

    def test_mutation_permission_owner_update(self):
        """Owner should have UPDATE permission."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.owner, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertTrue(has_perm)

    def test_mutation_permission_owner_delete(self):
        """Owner should have DELETE permission."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.owner, self.doc1.id, self.corpus.id, "DELETE"
        )
        self.assertTrue(has_perm)

    def test_mutation_permission_collaborator_read_only(self):
        """Collaborator with only READ should be denied mutation."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.collaborator, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertFalse(has_perm)
        self.assertIn("UPDATE", msg)

    def test_mutation_permission_doc_read_only_no_corpus_update(self):
        """User with doc READ but no corpus UPDATE permission should be denied."""
        user = User.objects.create_user(username="docperm", password="test")
        # Give READ on doc (required) but only READ on corpus (not UPDATE)
        set_permissions_for_obj_to_user(user, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(user, self.corpus, [PermissionTypes.READ])

        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            user, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertFalse(has_perm)
        self.assertIn("corpus", msg.lower())

    def test_mutation_permission_no_doc_visibility(self):
        """User without document visibility should be denied."""
        user = User.objects.create_user(username="nodocread", password="test")
        # Give corpus UPDATE but no doc visibility (user can't see the document)
        set_permissions_for_obj_to_user(user, self.corpus, [PermissionTypes.UPDATE])

        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            user, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertFalse(has_perm)
        # Error message is now "Document not found or not accessible" (IDOR-safe)
        self.assertIn("not found or not accessible", msg.lower())

    def test_mutation_permission_corpus_update_doc_read_succeeds(self):
        """
        User with corpus UPDATE + doc READ should be able to edit metadata.

        This is the key test for the corpus-primary permission model:
        - Metadata is a corpus-level feature
        - Corpus UPDATE permission controls write access
        - Only need doc READ (not UPDATE) to edit metadata
        """
        user = User.objects.create_user(username="corpuseditor", password="test")
        # Give READ on doc and UPDATE on corpus
        set_permissions_for_obj_to_user(user, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(user, self.corpus, [PermissionTypes.UPDATE])

        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            user, self.doc1.id, self.corpus.id, "UPDATE"
        )
        self.assertTrue(has_perm)
        self.assertEqual(msg, "")

    def test_mutation_permission_nonexistent_document(self):
        """Should return error for nonexistent document."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.owner, 99999, self.corpus.id, "UPDATE"
        )
        self.assertFalse(has_perm)
        self.assertIn("Document", msg)

    def test_mutation_permission_nonexistent_corpus(self):
        """Should return error for nonexistent corpus."""
        has_perm, msg = MetadataService.check_metadata_mutation_permission(
            self.owner, self.doc1.id, 99999, "UPDATE"
        )
        self.assertFalse(has_perm)
        self.assertIn("Corpus", msg)

    # =========================================================================
    # Tests for validate_metadata_column
    # =========================================================================

    def test_validate_column_valid(self):
        """Valid column should pass validation."""
        is_valid, msg, column = MetadataService.validate_metadata_column(
            self.column1.id, self.corpus.id
        )
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")
        assert column is not None
        self.assertEqual(column.id, self.column1.id)

    def test_validate_column_not_manual_entry(self):
        """Non-manual entry column should fail validation."""
        is_valid, msg, column = MetadataService.validate_metadata_column(
            self.column3.id, self.corpus.id  # column3 is not manual entry
        )
        self.assertFalse(is_valid)
        self.assertIn("manual entry", msg.lower())
        self.assertIsNone(column)

    def test_validate_column_wrong_corpus(self):
        """Column from different corpus should fail validation."""
        is_valid, msg, column = MetadataService.validate_metadata_column(
            self.column1.id, self.public_corpus.id
        )
        self.assertFalse(is_valid)
        self.assertIn("does not belong", msg.lower())
        self.assertIsNone(column)

    def test_validate_column_nonexistent(self):
        """Nonexistent column should fail validation."""
        is_valid, msg, column = MetadataService.validate_metadata_column(
            99999, self.corpus.id
        )
        self.assertFalse(is_valid)
        self.assertIn("Column not found", msg)
        self.assertIsNone(column)

    def test_validate_column_nonexistent_corpus(self):
        """Nonexistent corpus should fail validation."""
        is_valid, msg, column = MetadataService.validate_metadata_column(
            self.column1.id, 99999
        )
        self.assertFalse(is_valid)
        self.assertIn("Corpus not found", msg)
        self.assertIsNone(column)

    # =========================================================================
    # Additional coverage tests for edge cases
    # =========================================================================

    def test_compute_permissions_anonymous_nonexistent_document(self):
        """Anonymous user with nonexistent document should get no permissions."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.anonymous, 99999, self.public_corpus.id
            )
        )
        self.assertFalse(can_read)
        self.assertFalse(can_create)
        self.assertFalse(can_update)
        self.assertFalse(can_delete)

    def test_compute_permissions_anonymous_nonexistent_corpus(self):
        """Anonymous user with nonexistent corpus should get no permissions."""
        can_read, can_create, can_update, can_delete = (
            MetadataService._compute_effective_permissions(
                self.anonymous, self.public_doc.id, 99999
            )
        )
        self.assertFalse(can_read)
        self.assertFalse(can_create)
        self.assertFalse(can_update)
        self.assertFalse(can_delete)

    def test_get_columns_anonymous_private_corpus(self):
        """Anonymous user should not see columns for private corpus."""
        columns = MetadataService.get_corpus_metadata_columns(
            self.anonymous, self.corpus.id
        )
        self.assertEqual(columns.count(), 0)

    def test_get_columns_nonexistent_corpus(self):
        """Should return empty queryset for nonexistent corpus."""
        columns = MetadataService.get_corpus_metadata_columns(self.owner, 99999)
        self.assertEqual(columns.count(), 0)

    def test_get_document_metadata_no_schema(self):
        """Should return empty for corpus without metadata schema."""
        corpus_no_schema = Corpus.objects.create(
            title="No Schema Corpus", creator=self.owner
        )
        set_permissions_for_obj_to_user(
            self.owner, corpus_no_schema, [PermissionTypes.CRUD]
        )

        datacells = MetadataService.get_document_metadata(
            self.owner, self.doc1.id, corpus_no_schema.id
        )
        self.assertEqual(datacells.count(), 0)

    def test_get_document_metadata_nonexistent_corpus(self):
        """Should return empty for nonexistent corpus."""
        datacells = MetadataService.get_document_metadata(
            self.owner, self.doc1.id, 99999
        )
        self.assertEqual(datacells.count(), 0)

    def test_batch_nonexistent_corpus(self):
        """Should return empty for nonexistent corpus."""
        result = MetadataService.get_documents_metadata_batch(
            self.owner, [self.doc1.id], 99999
        )
        self.assertEqual(len(result), 0)

    def test_batch_anonymous_private_corpus(self):
        """Anonymous user should not see documents for private corpus."""
        result = MetadataService.get_documents_metadata_batch(
            self.anonymous, [self.doc1.id], self.corpus.id
        )
        self.assertEqual(len(result), 0)

    def test_batch_no_metadata_schema(self):
        """Should return empty for corpus without metadata schema."""
        corpus_no_schema = Corpus.objects.create(
            title="Batch No Schema", creator=self.owner
        )
        set_permissions_for_obj_to_user(
            self.owner, corpus_no_schema, [PermissionTypes.CRUD]
        )

        result = MetadataService.get_documents_metadata_batch(
            self.owner, [self.doc1.id], corpus_no_schema.id
        )
        self.assertEqual(len(result), 0)

    def test_batch_anonymous_public_documents(self):
        """Anonymous user should see public documents in public corpus."""
        # Create datacell for public document
        Datacell.objects.create(
            document=self.public_doc,
            column=self.public_column,
            data={"value": "Public Value"},
            data_definition="string",
            creator=self.owner,
        )

        result = MetadataService.get_documents_metadata_batch(
            self.anonymous, [self.public_doc.id], self.public_corpus.id
        )
        self.assertIn(self.public_doc.id, result)
        self.assertEqual(len(result[self.public_doc.id]), 1)

    def test_batch_anonymous_public_corpus_private_documents(self):
        """Anonymous user should not see private documents even in public corpus."""
        # Add a private document to the public corpus
        private_doc = self._create_document("Private in Public", self.owner)
        self.public_corpus.add_document(document=private_doc, user=self.owner)

        result = MetadataService.get_documents_metadata_batch(
            self.anonymous, [private_doc.id], self.public_corpus.id
        )
        # Private document should not be in result for anonymous user
        self.assertNotIn(private_doc.id, result)

    def test_completion_status_nonexistent_corpus(self):
        """Should return None for nonexistent corpus."""
        status = MetadataService.get_metadata_completion_status(
            self.owner, self.doc1.id, 99999
        )
        self.assertIsNone(status)

    def test_completion_status_zero_manual_columns(self):
        """Corpus with only non-manual columns should return 100%."""
        # Create a corpus with only non-manual entry columns
        corpus_auto = Corpus.objects.create(title="Auto Only", creator=self.owner)
        set_permissions_for_obj_to_user(self.owner, corpus_auto, [PermissionTypes.CRUD])

        fieldset_auto = Fieldset.objects.create(
            name="Auto Fieldset",
            corpus=corpus_auto,
            creator=self.owner,
        )
        Column.objects.create(
            name="Auto Column",
            fieldset=fieldset_auto,
            data_type="STRING",
            output_type="string",
            is_manual_entry=False,  # Not manual entry
            creator=self.owner,
        )

        doc = self._create_document("Auto Doc", self.owner)
        corpus_auto.add_document(document=doc, user=self.owner)

        status = MetadataService.get_metadata_completion_status(
            self.owner, doc.id, corpus_auto.id
        )
        assert status is not None
        self.assertEqual(status["total_fields"], 0)
        self.assertEqual(status["percentage"], 100.0)

    def test_batch_user_with_no_groups(self):
        """User with no group memberships should still work via direct permissions."""
        # Create a user and remove from all groups to test the no-groups code path
        solo_user = User.objects.create_user(username="solo", password="test123")
        # Remove from auto-assigned groups to test the no-groups branch (line 162)
        solo_user.groups.clear()
        self.assertEqual(solo_user.groups.count(), 0)

        # Grant direct permissions
        set_permissions_for_obj_to_user(solo_user, self.doc1, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(solo_user, self.corpus, [PermissionTypes.READ])

        result = MetadataService.get_documents_metadata_batch(
            solo_user, [self.doc1.id], self.corpus.id
        )
        self.assertIn(self.doc1.id, result)


class MetadataServiceDefensiveCodeTestCase(TestCase):
    """
    Tests for defensive code paths in MetadataService.

    These tests use mocking to hit code paths that are normally unreachable
    due to prior permission checks, but exist for defensive purposes
    (e.g., race conditions where corpus is deleted between checks).
    """

    def setUp(self):
        """Set up minimal test data."""
        self.user = User.objects.create_user(username="testuser", password="test123")
        self.superuser = User.objects.create_superuser(
            username="superadmin", password="admin"
        )

        # Create a document
        with open(SAMPLE_PDF_FILE_ONE_PATH, "rb") as f:
            pdf_content = f.read()
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file=ContentFile(pdf_content, name="test.pdf"),
        )

    def test_get_document_metadata_corpus_deleted_after_permission_check(self):
        """
        Test defensive code path when corpus is deleted after permission check.

        This simulates a race condition where corpus exists during permission
        check but is deleted before the subsequent get().
        """
        from unittest.mock import patch

        # Mock _compute_effective_permissions to return True for can_read
        with patch.object(
            MetadataService,
            "_compute_effective_permissions",
            return_value=(True, False, False, False),
        ):
            # Call with non-existent corpus ID - this should hit lines 264-265
            datacells = MetadataService.get_document_metadata(
                self.user, self.doc.id, 99999
            )
            self.assertEqual(datacells.count(), 0)

    def test_completion_status_corpus_deleted_after_permission_check(self):
        """
        Test defensive code path when corpus is deleted after permission check.

        This simulates a race condition where corpus exists during permission
        check but is deleted before the subsequent get().
        """
        from unittest.mock import patch

        # Mock _compute_effective_permissions to return True for can_read
        with patch.object(
            MetadataService,
            "_compute_effective_permissions",
            return_value=(True, False, False, False),
        ):
            # Call with non-existent corpus ID - this should hit lines 397-398
            status = MetadataService.get_metadata_completion_status(
                self.user, self.doc.id, 99999
            )
            self.assertIsNone(status)

    def test_readable_document_ids_bulk_missing_permission(self):
        """
        Test defensive code path when read_document permission doesn't exist.

        This is an edge case that could occur if migrations haven't been run.
        """
        from unittest.mock import MagicMock, patch

        from opencontractserver.documents.models import Document

        # Create corpus for testing
        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.READ])

        # Mock Permission.objects.filter().first() to return None (no permission found)
        # The Permission is imported locally inside the method from django.contrib.auth.models
        with patch(
            "django.contrib.auth.models.Permission.objects"
        ) as mock_perm_objects:
            mock_filter = MagicMock()
            mock_filter.first.return_value = None
            mock_perm_objects.filter.return_value = mock_filter

            # Call _get_readable_document_ids_bulk directly - should return empty set
            documents = Document.objects.filter(pk=self.doc.id)
            result = MetadataService._get_readable_document_ids_bulk(
                self.user, [self.doc.id], documents
            )
            self.assertEqual(result, set())
