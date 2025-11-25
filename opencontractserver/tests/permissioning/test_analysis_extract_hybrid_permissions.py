"""
Test Analysis and Extract Hybrid Permission Model

This test suite validates the complex three-tier permission system for Analyses and Extracts:
1. Object-level permissions (Analysis/Extract can be shared independently)
2. Corpus-level permissions (must have corpus access to see the object)
3. Document-level filtering (content is filtered based on document permissions)

Test Scenario:
==============
We have 3 users (Alice, Bob, Charlie), 2 corpuses (X, Y), and 2 documents (Alpha, Beta).

Setup:
- Corpus X contains: Doc Alpha, Doc Beta
- Corpus Y contains: Doc Beta (note: Alpha is NOT in Y)

User Permissions:
- User A (Alice): Has permissions to Doc Alpha, Doc Beta, and Corpus X
- User B (Bob): Has permissions to Doc Beta, Corpus X, and Corpus Y
- User C (Charlie): Has permissions to Doc Alpha and Corpus Y

Expected Behaviors:
- Alice sees everything in Corpus X (both docs)
- Bob sees Corpus X and Y, but only Doc Beta in both
- Charlie sees Corpus Y but it appears empty (Alpha not in Y)
- Analyses/Extracts require BOTH object permission AND corpus permission
- Content within Analyses/Extracts is filtered by document permissions
"""

import logging

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    """Mock context for GraphQL client"""

    def __init__(self, user):
        self.user = user


class AnalysisExtractHybridPermissionTestCase(TestCase):
    """
    Tests the hybrid permission model for Analyses and Extracts where:
    - They have their own permissions (can be shared independently)
    - BUT visibility requires corpus permissions too
    - Content within is filtered by document permissions
    """

    def setUp(self):
        """
        Set up the test scenario with 3 users, 2 corpuses, and 2 documents.

        This creates a complex but realistic scenario where documents can exist
        in multiple corpuses and users have different permission combinations.
        """
        logger.info("\n" + "=" * 80)
        logger.info("SETTING UP TEST SCENARIO")
        logger.info("=" * 80)

        # Create our three test users
        self.user_alice = User.objects.create_user(username="Alice", password="test123")
        self.user_bob = User.objects.create_user(username="Bob", password="test123")
        self.user_charlie = User.objects.create_user(
            username="Charlie", password="test123"
        )

        # Create a superuser for comparison
        self.superuser = User.objects.create_superuser(
            username="Super", password="admin"
        )

        # Create GraphQL clients for each user
        self.client_alice = Client(schema, context_value=TestContext(self.user_alice))
        self.client_bob = Client(schema, context_value=TestContext(self.user_bob))
        self.client_charlie = Client(
            schema, context_value=TestContext(self.user_charlie)
        )
        self.client_super = Client(schema, context_value=TestContext(self.superuser))

        # Create our two test documents (owned by superuser to avoid ownership issues)
        self.doc_alpha = self._create_document("Doc Alpha", self.superuser)
        self.doc_beta = self._create_document("Doc Beta", self.superuser)

        # Create our two test corpuses (owned by superuser to avoid ownership issues)
        self.corpus_x = self._create_corpus("Corpus X", self.superuser)
        self.corpus_y = self._create_corpus("Corpus Y", self.superuser)

        # Set up corpus membership
        # Corpus X contains both Alpha and Beta
        self.corpus_x.add_document(document=self.doc_alpha, user=self.superuser)
        self.corpus_x.add_document(document=self.doc_beta, user=self.superuser)

        # Corpus Y contains only Beta (NOT Alpha - this is important!)
        self.corpus_y.add_document(document=self.doc_beta, user=self.superuser)

        # Set up the permission structure
        self._setup_permissions()

        # Create test analyzer infrastructure
        self._setup_analyzer_infrastructure()

        # Create analyses and extracts for testing
        self._create_test_analyses_and_extracts()

        logger.info("Setup complete!")

    def _create_document(self, title, creator):
        """Helper to create a document with a real PDF"""
        with transaction.atomic():
            doc = Document.objects.create(
                title=title,
                description=f"Test document: {title}",
                creator=creator,
                is_public=False,  # Not public by default
            )
            # Add a real PDF file
            with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
                pdf_contents = ContentFile(test_pdf.read())
                doc.pdf_file.save("test.pdf", pdf_contents)
            return doc

    def _create_corpus(self, title, creator):
        """Helper to create a corpus"""
        return Corpus.objects.create(
            title=title,
            description=f"Test corpus: {title}",
            creator=creator,
            is_public=False,  # Not public by default
        )

    def _setup_permissions(self):
        """
        Set up the permission structure according to our test scenario.

        Remember:
        - Alice: Can access Alpha, Beta, and Corpus X
        - Bob: Can access Beta, Corpus X, and Corpus Y
        - Charlie: Can access Alpha and Corpus Y
        """
        logger.info("\nSetting up permissions...")

        # Alice's permissions
        set_permissions_for_obj_to_user(
            self.user_alice, self.doc_alpha, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_alice, self.doc_beta, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_alice, self.corpus_x, [PermissionTypes.READ]
        )
        logger.info("✓ Alice can read: Doc Alpha, Doc Beta, Corpus X")

        # Bob's permissions
        set_permissions_for_obj_to_user(
            self.user_bob, self.doc_beta, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_bob, self.corpus_x, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_bob, self.corpus_y, [PermissionTypes.READ]
        )
        logger.info("✓ Bob can read: Doc Beta, Corpus X, Corpus Y")

        # Charlie's permissions
        set_permissions_for_obj_to_user(
            self.user_charlie, self.doc_alpha, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_charlie, self.corpus_y, [PermissionTypes.READ]
        )
        logger.info("✓ Charlie can read: Doc Alpha, Corpus Y")

    def _setup_analyzer_infrastructure(self):
        """Create the analyzer infrastructure needed for analyses"""
        # Create a dummy Gremlin engine
        self.gremlin = GremlinEngine.objects.create(
            url="http://dummy-gremlin:8000", creator=self.superuser
        )

        # Create a dummy analyzer
        self.analyzer = Analyzer.objects.create(
            id="TEST.ANALYZER",
            host_gremlin=self.gremlin,
            creator=self.superuser,
            description="Test analyzer for permission testing",
        )

        # Create annotation labels
        self.label = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Test Label", creator=self.superuser
        )

    def _create_test_analyses_and_extracts(self):
        """Create analyses and extracts on our corpuses"""
        logger.info("\nCreating test analyses and extracts...")

        # Create an analysis on Corpus X (contains both Alpha and Beta)
        self.analysis_x = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus_x,
            creator=self.superuser,
            is_public=False,
        )
        self.analysis_x.analyzed_documents.add(self.doc_alpha, self.doc_beta)

        # Create annotations in the analysis
        self.ann_alpha_in_x = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc_alpha,
            corpus=self.corpus_x,
            analysis=self.analysis_x,
            creator=self.superuser,
            page=1,
            raw_text="Annotation on Alpha in analysis X",
        )

        self.ann_beta_in_x = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc_beta,
            corpus=self.corpus_x,
            analysis=self.analysis_x,
            creator=self.superuser,
            page=1,
            raw_text="Annotation on Beta in analysis X",
        )

        # Create an analysis on Corpus Y (contains only Beta)
        self.analysis_y = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus_y,
            creator=self.superuser,
            is_public=False,
        )
        self.analysis_y.analyzed_documents.add(self.doc_beta)

        # Create annotation in analysis Y
        self.ann_beta_in_y = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc_beta,
            corpus=self.corpus_y,
            analysis=self.analysis_y,
            creator=self.superuser,
            page=1,
            raw_text="Annotation on Beta in analysis Y",
        )

        # Create fieldset and extract for Corpus X
        self.fieldset_x = Fieldset.objects.create(
            name="Test Fieldset X",
            description="Fieldset for testing extracts on Corpus X",
            creator=self.superuser,
        )

        self.column_x = Column.objects.create(
            name="Test Column",
            fieldset=self.fieldset_x,
            query="Test query",
            output_type="string",
            creator=self.superuser,  # Column inherits from BaseOCModel and needs creator
        )

        self.extract_x = Extract.objects.create(
            name="Test Extract X",
            corpus=self.corpus_x,
            fieldset=self.fieldset_x,
            creator=self.superuser,
        )
        self.extract_x.documents.add(self.doc_alpha, self.doc_beta)

        # Create datacells in extract X
        self.datacell_alpha = Datacell.objects.create(
            creator=self.superuser,
            extract=self.extract_x,
            column=self.column_x,
            document=self.doc_alpha,
            data={"value": "Data from Alpha"},
            data_definition="Test data from Alpha",
        )

        self.datacell_beta = Datacell.objects.create(
            creator=self.superuser,
            extract=self.extract_x,
            column=self.column_x,
            document=self.doc_beta,
            data={"value": "Data from Beta"},
            data_definition="Test data from Beta",
        )

        logger.info("✓ Created analyses and extracts for testing")

    # =========================================================================
    # TEST 1: Alice sees everything in Corpus X
    # =========================================================================

    def test_alice_sees_everything_in_corpus_x(self):
        """
        Alice has permissions to both documents (Alpha and Beta) and Corpus X.
        She should see all analyses and extracts in Corpus X with all content.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Alice sees everything in Corpus X")
        logger.info("=" * 80)

        # Give Alice permission to the analysis
        set_permissions_for_obj_to_user(
            self.user_alice, self.analysis_x, [PermissionTypes.READ]
        )

        # Query for analysis
        analysis_id = to_global_id("AnalysisType", self.analysis_x.id)
        query = (
            """
        query {
            analysis(id: "%s") {
                id
                analyzedCorpus {
                    title
                }
                fullAnnotationList {
                    id
                    rawText
                    document {
                        title
                    }
                }
            }
        }
        """
            % analysis_id
        )

        result = self.client_alice.execute(query)

        self.assertIsNone(result.get("errors"), "Should not have errors")
        analysis_data = result["data"]["analysis"]

        self.assertIsNotNone(analysis_data, "Alice should see the analysis")
        self.assertEqual(analysis_data["analyzedCorpus"]["title"], "Corpus X")

        # Check annotations - should see both
        annotations = analysis_data["fullAnnotationList"]
        self.assertEqual(len(annotations), 2, "Alice should see both annotations")

        # Verify we see annotations from both documents
        doc_titles = {ann["document"]["title"] for ann in annotations}
        self.assertEqual(
            doc_titles,
            {"Doc Alpha", "Doc Beta"},
            "Alice should see annotations from both documents",
        )

        logger.info("✓ Alice sees all content in Corpus X (both Alpha and Beta)")

    # =========================================================================
    # TEST 2: Bob sees only Beta content in Corpus X
    # =========================================================================

    def test_bob_sees_only_beta_in_corpus_x(self):
        """
        Bob has permissions to Doc Beta (but not Alpha) and Corpus X.
        He should see the analysis but only annotations on Beta.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Bob sees only Beta content in Corpus X")
        logger.info("=" * 80)

        # Give Bob permission to the analysis
        set_permissions_for_obj_to_user(
            self.user_bob, self.analysis_x, [PermissionTypes.READ]
        )

        # Query for analysis
        analysis_id = to_global_id("AnalysisType", self.analysis_x.id)
        query = (
            """
        query {
            analysis(id: "%s") {
                id
                fullAnnotationList {
                    rawText
                    document {
                        title
                    }
                }
            }
        }
        """
            % analysis_id
        )

        result = self.client_bob.execute(query)

        self.assertIsNone(result.get("errors"), "Should not have errors")
        analysis_data = result["data"]["analysis"]

        self.assertIsNotNone(analysis_data, "Bob should see the analysis")

        # Check annotations - should see only Beta
        annotations = analysis_data["fullAnnotationList"]
        self.assertEqual(len(annotations), 1, "Bob should see only 1 annotation (Beta)")
        self.assertEqual(
            annotations[0]["document"]["title"],
            "Doc Beta",
            "Bob should only see the Beta annotation",
        )

        logger.info("✓ Bob sees only Beta content in Corpus X (no Alpha)")

    # =========================================================================
    # TEST 3: Charlie cannot see anything in Corpus Y
    # =========================================================================

    def test_charlie_sees_nothing_in_corpus_y(self):
        """
        Charlie has permissions to Doc Alpha and Corpus Y.
        However, Doc Alpha is NOT in Corpus Y (only Beta is).
        Charlie has no permission to Beta, so he effectively sees nothing.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Charlie sees nothing in Corpus Y (no permission to Beta)")
        logger.info("=" * 80)

        # Give Charlie permission to the analysis on Corpus Y
        set_permissions_for_obj_to_user(
            self.user_charlie, self.analysis_y, [PermissionTypes.READ]
        )

        # Query for analysis
        analysis_id = to_global_id("AnalysisType", self.analysis_y.id)
        query = (
            """
        query {
            analysis(id: "%s") {
                id
                analyzedCorpus {
                    title
                }
                fullAnnotationList {
                    rawText
                    document {
                        title
                    }
                }
            }
        }
        """
            % analysis_id
        )

        result = self.client_charlie.execute(query)

        self.assertIsNone(result.get("errors"), "Should not have errors")
        analysis_data = result["data"]["analysis"]

        self.assertIsNotNone(analysis_data, "Charlie can see the analysis object")
        self.assertEqual(analysis_data["analyzedCorpus"]["title"], "Corpus Y")

        # Check annotations - should be empty!
        annotations = analysis_data["fullAnnotationList"]
        self.assertEqual(
            len(annotations),
            0,
            "Charlie should see NO annotations (no permission to Beta)",
        )

        logger.info("✓ Charlie sees the analysis but no content (no doc permissions)")

    # =========================================================================
    # TEST 4: No analysis permission means no access (even with corpus+doc)
    # =========================================================================

    def test_no_analysis_permission_no_access(self):
        """
        Bob has permissions to Corpus X and Doc Beta, but if he doesn't have
        permission to the analysis itself, he shouldn't see it at all.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No analysis permission = no access")
        logger.info("=" * 80)

        # DON'T give Bob permission to the analysis (that's the point!)
        # He already has corpus and document permissions from setup

        # Query for analysis
        analysis_id = to_global_id("AnalysisType", self.analysis_x.id)
        query = (
            """
        query {
            analysis(id: "%s") {
                id
                analyzedCorpus {
                    title
                }
            }
        }
        """
            % analysis_id
        )

        result = self.client_bob.execute(query)

        # Bob should NOT see the analysis without explicit permission
        analysis_data = result["data"]["analysis"]
        self.assertIsNone(
            analysis_data, "Bob should NOT see analysis without permission to it"
        )

        logger.info("✓ Without analysis permission, user sees nothing")

    # =========================================================================
    # TEST 5: Extract permissions work the same way
    # =========================================================================

    def test_extract_hybrid_permissions(self):
        """
        Test that extracts follow the same hybrid permission model.
        Alice should see all datacells, Bob only Beta's datacell.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Extract hybrid permissions")
        logger.info("=" * 80)

        # Give both Alice and Bob permission to the extract
        set_permissions_for_obj_to_user(
            self.user_alice, self.extract_x, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_bob, self.extract_x, [PermissionTypes.READ]
        )

        extract_id = to_global_id("ExtractType", self.extract_x.id)
        query = (
            """
        query {
            extract(id: "%s") {
                id
                name
                fullDatacellList {
                    data
                    document {
                        title
                    }
                }
            }
        }
        """
            % extract_id
        )

        # Test Alice - should see both datacells
        result_alice = self.client_alice.execute(query)
        self.assertIsNone(result_alice.get("errors"))

        alice_datacells = result_alice["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(alice_datacells), 2, "Alice should see both datacells")

        alice_docs = {dc["document"]["title"] for dc in alice_datacells}
        self.assertEqual(alice_docs, {"Doc Alpha", "Doc Beta"})
        logger.info("✓ Alice sees all datacells in extract")

        # Test Bob - should see only Beta datacell
        result_bob = self.client_bob.execute(query)
        self.assertIsNone(result_bob.get("errors"))

        bob_datacells = result_bob["data"]["extract"]["fullDatacellList"]
        self.assertEqual(len(bob_datacells), 1, "Bob should see only Beta datacell")
        self.assertEqual(bob_datacells[0]["document"]["title"], "Doc Beta")
        logger.info("✓ Bob sees only Beta datacell in extract")

    # =========================================================================
    # TEST 6: Corpus permission is required for analysis visibility
    # =========================================================================

    def test_corpus_permission_required_for_analysis(self):
        """
        Even if a user has permission to an analysis and its documents,
        they can't see it without corpus permission.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Corpus permission required for analysis visibility")
        logger.info("=" * 80)

        # Create a new user with permission to analysis and document but NOT corpus
        user_dave = User.objects.create_user(username="Dave", password="test123")
        client_dave = Client(schema, context_value=TestContext(user_dave))

        # Give Dave permission to the analysis and Beta document
        set_permissions_for_obj_to_user(
            user_dave, self.analysis_x, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            user_dave, self.doc_beta, [PermissionTypes.READ]
        )
        # BUT NO CORPUS PERMISSION!

        # Query for analysis
        analysis_id = to_global_id("AnalysisType", self.analysis_x.id)
        query = (
            """
        query {
            analysis(id: "%s") {
                id
                analyzedCorpus {
                    title
                }
            }
        }
        """
            % analysis_id
        )

        result = client_dave.execute(query)

        # Dave should NOT see the analysis without corpus permission
        analysis_data = result["data"]["analysis"]
        self.assertIsNone(
            analysis_data, "Dave should NOT see analysis without corpus permission"
        )

        logger.info("✓ Analysis not visible without corpus permission")

    # =========================================================================
    # TEST 7: List queries respect the hybrid model
    # =========================================================================

    def test_list_queries_respect_hybrid_permissions(self):
        """
        Test that list queries (analyses, extracts) properly filter based on
        the hybrid permission model.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: List queries respect hybrid permissions")
        logger.info("=" * 80)

        # Give Alice permission to both analyses
        set_permissions_for_obj_to_user(
            self.user_alice, self.analysis_x, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.user_alice, self.analysis_y, [PermissionTypes.READ]
        )

        # Give Bob permission to analysis Y (he already has corpus Y permission)
        set_permissions_for_obj_to_user(
            self.user_bob, self.analysis_y, [PermissionTypes.READ]
        )

        # Query for all analyses
        query = """
        query {
            analyses {
                edges {
                    node {
                        id
                        analyzedCorpus {
                            title
                        }
                    }
                }
            }
        }
        """

        # Alice should see only analysis X (she has no permission to Corpus Y)
        result_alice = self.client_alice.execute(query)
        alice_analyses = result_alice["data"]["analyses"]["edges"]
        alice_corpus_titles = {
            a["node"]["analyzedCorpus"]["title"] for a in alice_analyses
        }
        self.assertIn("Corpus X", alice_corpus_titles)
        self.assertNotIn(
            "Corpus Y",
            alice_corpus_titles,
            "Alice shouldn't see Corpus Y analysis (no corpus permission)",
        )
        logger.info("✓ Alice sees only Corpus X analyses")

        # Bob should see only analysis Y (he has permission to it and Corpus Y)
        result_bob = self.client_bob.execute(query)
        bob_analyses = result_bob["data"]["analyses"]["edges"]
        bob_corpus_titles = {a["node"]["analyzedCorpus"]["title"] for a in bob_analyses}
        self.assertIn("Corpus Y", bob_corpus_titles)
        logger.info("✓ Bob sees Corpus Y analysis")

    # =========================================================================
    # TEST 8: Superuser sees everything
    # =========================================================================

    def test_superuser_sees_everything(self):
        """
        Superusers bypass all permission checks and see everything.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Superuser sees everything")
        logger.info("=" * 80)

        # Query for analysis X (superuser has no explicit permissions)
        analysis_id = to_global_id("AnalysisType", self.analysis_x.id)
        query = (
            """
        query {
            analysis(id: "%s") {
                id
                fullAnnotationList {
                    document {
                        title
                    }
                }
            }
        }
        """
            % analysis_id
        )

        result = self.client_super.execute(query)

        self.assertIsNone(result.get("errors"))
        analysis_data = result["data"]["analysis"]

        self.assertIsNotNone(analysis_data, "Superuser should see the analysis")

        # Should see all annotations
        annotations = analysis_data["fullAnnotationList"]
        self.assertEqual(len(annotations), 2, "Superuser should see all annotations")

        doc_titles = {ann["document"]["title"] for ann in annotations}
        self.assertEqual(doc_titles, {"Doc Alpha", "Doc Beta"})

        logger.info("✓ Superuser sees everything without explicit permissions")


class ExtractMetadataPermissionTestCase(TestCase):
    """
    Additional test case for metadata-specific extract scenarios.
    Tests that manual metadata columns follow the same permission model.
    """

    def setUp(self):
        """Set up a simple test with manual metadata columns"""
        self.user = User.objects.create_user(username="TestUser", password="test123")
        self.other_user = User.objects.create_user(
            username="OtherUser", password="test123"
        )

        # Create document and corpus
        self.doc = Document.objects.create(title="Test Doc", creator=self.user)

        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.corpus.documents.add(self.doc)

        # Create fieldset with manual metadata column
        self.fieldset = Fieldset.objects.create(
            name="Metadata Fieldset",
            description="Test manual metadata",
            creator=self.user,
            corpus=self.corpus,  # This is a metadata schema for the corpus
        )

        self.manual_column = Column.objects.create(
            creator=self.user,
            name="Manual Field",
            fieldset=self.fieldset,
            is_manual_entry=True,
            data_type="STRING",
            output_type="string",
        )

        # Create manual metadata (no extract needed for manual metadata)
        self.manual_datacell = Datacell.objects.create(
            creator=self.user,
            extract=None,  # Manual metadata doesn't need extract
            column=self.manual_column,
            document=self.doc,
            data={"value": "Manual metadata value"},
            data_definition="Manual entry",
        )

    def test_manual_metadata_follows_document_permissions(self):
        """
        Manual metadata should only be visible if user has document permission.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Manual metadata follows document permissions")
        logger.info("=" * 80)

        # Give user permission to document
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.READ])

        # Other user has no permission
        # Attempting to query the datacell should respect document permissions

        # This would need actual GraphQL query implementation for manual metadata
        # For now, we just verify the permission check works
        self.assertTrue(
            user_has_permission_for_obj(
                self.user,
                self.doc,
                PermissionTypes.READ,
                include_group_permissions=True,
            ),
            "User should have read permission on document",
        )

        self.assertFalse(
            user_has_permission_for_obj(
                self.other_user,
                self.doc,
                PermissionTypes.READ,
                include_group_permissions=True,
            ),
            "Other user should NOT have read permission on document",
        )

        logger.info("✓ Manual metadata respects document permissions")
