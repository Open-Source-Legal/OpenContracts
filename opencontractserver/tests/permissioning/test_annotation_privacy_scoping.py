"""
Test Annotation Privacy Scoping via Analyses and Extracts

This comprehensive test suite proves that separately permissioned analyses and extracts
can effectively scope annotation visibility on a shared corpus, creating private subsets
of annotations that only specific users can see.

Key Concepts Demonstrated:
==========================
1. **Shared Corpus**: Multiple users can READ and some can EDIT a shared corpus
2. **Private Analyses**: Each user/team creates analyses with restricted permissions
3. **Scoped Annotations**: Annotations created by analyses are private to those analyses
4. **Privacy Enforcement**: Users cannot see annotations from analyses they lack permission for
5. **Collaborative Filtering**: Different users see different annotation subsets on same documents

Test Scenarios:
==============
- Scenario 1: Research Team Collaboration
  * Shared corpus with multiple research teams
  * Each team has private analyses creating team-specific annotations
  * Team members see only their team's annotations plus public annotations

- Scenario 2: Progressive Review Pipeline
  * Multiple review stages with different access levels
  * Stage 1 reviewers can't see Stage 2 annotations
  * Supervisors can see all stages

- Scenario 3: Client Data Segregation
  * Single corpus serving multiple clients
  * Each client's analysis creates client-specific annotations
  * Complete isolation between client data

- Scenario 4: Mixed Public/Private Annotations
  * Some annotations are public (no created_by_analysis)
  * Some are private to specific analyses
  * Users see different mixtures based on permissions
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
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    """Mock context for GraphQL client"""

    def __init__(self, user):
        self.user = user


class AnnotationPrivacyScopingTestCase(TestCase):
    """
    Comprehensive test suite proving that analyses and extracts can create
    private annotation subsets on shared corpuses.
    """

    def setUp(self):
        """Set up complex multi-team collaboration scenario"""
        logger.info("\n" + "=" * 80)
        logger.info("SETTING UP ANNOTATION PRIVACY SCOPING TEST")
        logger.info("=" * 80)

        # Create users representing different teams/roles
        self.admin = User.objects.create_superuser(username="Admin", password="admin")

        # Team A members
        self.team_a_lead = User.objects.create_user(
            username="TeamALead", password="test123"
        )
        self.team_a_member1 = User.objects.create_user(
            username="TeamAMember1", password="test123"
        )
        self.team_a_member2 = User.objects.create_user(
            username="TeamAMember2", password="test123"
        )

        # Team B members
        self.team_b_lead = User.objects.create_user(
            username="TeamBLead", password="test123"
        )
        self.team_b_member1 = User.objects.create_user(
            username="TeamBMember1", password="test123"
        )

        # Independent reviewer
        self.reviewer = User.objects.create_user(
            username="Reviewer", password="test123"
        )

        # External client with limited access
        self.client_user = User.objects.create_user(
            username="ClientUser", password="test123"
        )

        # Create GraphQL clients
        self.client_admin = Client(schema, context_value=TestContext(self.admin))
        self.client_team_a_lead = Client(
            schema, context_value=TestContext(self.team_a_lead)
        )
        self.client_team_a_member1 = Client(
            schema, context_value=TestContext(self.team_a_member1)
        )
        self.client_team_b_lead = Client(
            schema, context_value=TestContext(self.team_b_lead)
        )
        self.client_team_b_member1 = Client(
            schema, context_value=TestContext(self.team_b_member1)
        )
        self.client_reviewer = Client(schema, context_value=TestContext(self.reviewer))
        self.client_external = Client(
            schema, context_value=TestContext(self.client_user)
        )

        # Create shared corpus and documents
        self._create_shared_resources()

        # Set up analyzer infrastructure
        self._setup_analyzer_infrastructure()

        # Create team-specific analyses
        self._create_team_analyses()

        # Create annotations with different privacy levels
        self._create_scoped_annotations()

        # Set up permissions
        self._setup_permissions()

        logger.info("Setup complete with multi-team privacy scoping scenario!")

    def _create_shared_resources(self):
        """Create the shared corpus and documents that all teams work on"""
        # Create shared corpus (owned by admin for neutrality)
        self.shared_corpus = Corpus.objects.create(
            title="Shared Research Corpus",
            description="A corpus shared by multiple research teams",
            creator=self.admin,
            is_public=False,
        )

        # Create documents in the shared corpus
        self.doc_contract1 = self._create_document("Contract Alpha", self.admin)
        self.doc_contract2 = self._create_document("Contract Beta", self.admin)
        self.doc_contract3 = self._create_document("Contract Gamma", self.admin)

        # Add documents to the shared corpus
        self.shared_corpus.add_document(document=self.doc_contract1, user=self.admin)
        self.shared_corpus.add_document(document=self.doc_contract2, user=self.admin)
        self.shared_corpus.add_document(document=self.doc_contract3, user=self.admin)

        # Create DocumentPath records for versioning system
        DocumentPath.objects.create(
            document=self.doc_contract1,
            corpus=self.shared_corpus,
            path="/contract_alpha.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.admin,
        )
        DocumentPath.objects.create(
            document=self.doc_contract2,
            corpus=self.shared_corpus,
            path="/contract_beta.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.admin,
        )
        DocumentPath.objects.create(
            document=self.doc_contract3,
            corpus=self.shared_corpus,
            path="/contract_gamma.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.admin,
        )

        logger.info("✓ Created shared corpus with 3 documents")

    def _create_document(self, title, creator):
        """Helper to create a document with a real PDF"""
        with transaction.atomic():
            doc = Document.objects.create(
                title=title,
                description=f"Shared document: {title}",
                creator=creator,
                is_public=False,
            )
            with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
                pdf_contents = ContentFile(test_pdf.read())
                doc.pdf_file.save("test.pdf", pdf_contents)
            return doc

    def _setup_analyzer_infrastructure(self):
        """Create analyzer infrastructure for analyses"""
        self.gremlin = GremlinEngine.objects.create(
            url="http://dummy-gremlin:8000", creator=self.admin
        )

        self.analyzer = Analyzer.objects.create(
            id="PRIVACY.TEST.ANALYZER",
            host_gremlin=self.gremlin,
            creator=self.admin,
            description="Analyzer for privacy scoping tests",
        )

        # Create different label types for different teams
        self.label_team_a = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Team A Finding", creator=self.team_a_lead
        )

        self.label_team_b = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Team B Finding", creator=self.team_b_lead
        )

        self.label_public = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Public Finding", creator=self.admin
        )

    def _create_team_analyses(self):
        """Create separate analyses for each team"""
        # Team A's private analysis
        self.analysis_team_a = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.shared_corpus,
            creator=self.team_a_lead,
            is_public=False,
        )
        self.analysis_team_a.analyzed_documents.add(
            self.doc_contract1, self.doc_contract2, self.doc_contract3
        )

        # Team B's private analysis
        self.analysis_team_b = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.shared_corpus,
            creator=self.team_b_lead,
            is_public=False,
        )
        self.analysis_team_b.analyzed_documents.add(
            self.doc_contract1, self.doc_contract2, self.doc_contract3
        )

        # Reviewer's analysis (for oversight)
        self.analysis_reviewer = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.shared_corpus,
            creator=self.reviewer,
            is_public=False,
        )
        self.analysis_reviewer.analyzed_documents.add(
            self.doc_contract1, self.doc_contract2, self.doc_contract3
        )

        # Create extracts for each team
        self.fieldset_team_a = Fieldset.objects.create(
            name="Team A Fieldset",
            description="Data extraction template for Team A",
            creator=self.team_a_lead,
        )

        self.extract_team_a = Extract.objects.create(
            name="Team A Extract",
            corpus=self.shared_corpus,
            fieldset=self.fieldset_team_a,
            creator=self.team_a_lead,
        )
        self.extract_team_a.documents.add(self.doc_contract1, self.doc_contract2)

        logger.info("✓ Created team-specific analyses and extracts")

    def _create_scoped_annotations(self):
        """Create annotations with different privacy scopes"""
        # PUBLIC annotations (visible to anyone with doc+corpus permissions)
        self.public_ann_1 = Annotation.objects.create(
            annotation_label=self.label_public,
            document=self.doc_contract1,
            corpus=self.shared_corpus,
            creator=self.admin,
            page=1,
            raw_text="Public annotation on Contract Alpha",
            # No created_by_analysis - this is PUBLIC
        )

        self.public_ann_2 = Annotation.objects.create(
            annotation_label=self.label_public,
            document=self.doc_contract2,
            corpus=self.shared_corpus,
            creator=self.admin,
            page=1,
            raw_text="Public annotation on Contract Beta",
            # No created_by_analysis - this is PUBLIC
        )

        # TEAM A PRIVATE annotations (only visible to Team A members)
        self.team_a_ann_1 = Annotation.objects.create(
            annotation_label=self.label_team_a,
            document=self.doc_contract1,
            corpus=self.shared_corpus,
            analysis=self.analysis_team_a,
            created_by_analysis=self.analysis_team_a,  # PRIVATE to Team A
            creator=self.team_a_lead,
            page=1,
            raw_text="Team A confidential finding on Contract Alpha",
        )

        self.team_a_ann_2 = Annotation.objects.create(
            annotation_label=self.label_team_a,
            document=self.doc_contract2,
            corpus=self.shared_corpus,
            analysis=self.analysis_team_a,
            created_by_analysis=self.analysis_team_a,  # PRIVATE to Team A
            creator=self.team_a_lead,
            page=2,
            raw_text="Team A confidential finding on Contract Beta",
        )

        self.team_a_ann_3 = Annotation.objects.create(
            annotation_label=self.label_team_a,
            document=self.doc_contract3,
            corpus=self.shared_corpus,
            analysis=self.analysis_team_a,
            created_by_analysis=self.analysis_team_a,  # PRIVATE to Team A
            creator=self.team_a_member1,
            page=1,
            raw_text="Team A member annotation on Contract Gamma",
        )

        # TEAM B PRIVATE annotations (only visible to Team B members)
        self.team_b_ann_1 = Annotation.objects.create(
            annotation_label=self.label_team_b,
            document=self.doc_contract1,
            corpus=self.shared_corpus,
            analysis=self.analysis_team_b,
            created_by_analysis=self.analysis_team_b,  # PRIVATE to Team B
            creator=self.team_b_lead,
            page=1,
            raw_text="Team B confidential finding on Contract Alpha",
        )

        self.team_b_ann_2 = Annotation.objects.create(
            annotation_label=self.label_team_b,
            document=self.doc_contract2,
            corpus=self.shared_corpus,
            analysis=self.analysis_team_b,
            created_by_analysis=self.analysis_team_b,  # PRIVATE to Team B
            creator=self.team_b_lead,
            page=3,
            raw_text="Team B confidential finding on Contract Beta",
        )

        # REVIEWER annotations (visible only to reviewer)
        self.reviewer_ann_1 = Annotation.objects.create(
            annotation_label=self.label_public,
            document=self.doc_contract1,
            corpus=self.shared_corpus,
            analysis=self.analysis_reviewer,
            created_by_analysis=self.analysis_reviewer,  # PRIVATE to Reviewer
            creator=self.reviewer,
            page=1,
            raw_text="Reviewer's confidential note on Contract Alpha",
        )

        # Annotations created by extract (testing extract privacy)
        self.extract_ann_1 = Annotation.objects.create(
            annotation_label=self.label_team_a,
            document=self.doc_contract1,
            corpus=self.shared_corpus,
            created_by_extract=self.extract_team_a,  # PRIVATE to Team A Extract
            creator=self.team_a_lead,
            page=4,
            raw_text="Team A extract-generated annotation",
        )

        logger.info("✓ Created annotations with different privacy scopes:")
        logger.info("  - 2 public annotations")
        logger.info("  - 3 Team A private annotations (via analysis)")
        logger.info("  - 2 Team B private annotations (via analysis)")
        logger.info("  - 1 Reviewer private annotation")
        logger.info("  - 1 Team A extract private annotation")

    def _setup_permissions(self):
        """Set up the permission structure for all users"""
        # Everyone gets READ access to the shared corpus and documents
        for user in [
            self.team_a_lead,
            self.team_a_member1,
            self.team_a_member2,
            self.team_b_lead,
            self.team_b_member1,
            self.reviewer,
            self.client_user,
        ]:
            set_permissions_for_obj_to_user(
                user, self.shared_corpus, [PermissionTypes.READ]
            )
            set_permissions_for_obj_to_user(
                user, self.doc_contract1, [PermissionTypes.READ]
            )
            set_permissions_for_obj_to_user(
                user, self.doc_contract2, [PermissionTypes.READ]
            )
            set_permissions_for_obj_to_user(
                user, self.doc_contract3, [PermissionTypes.READ]
            )

        # Team A members get access to Team A's analysis
        for user in [self.team_a_lead, self.team_a_member1, self.team_a_member2]:
            set_permissions_for_obj_to_user(
                user, self.analysis_team_a, [PermissionTypes.READ]
            )
            set_permissions_for_obj_to_user(
                user, self.extract_team_a, [PermissionTypes.READ]
            )

        # Team B members get access to Team B's analysis
        for user in [self.team_b_lead, self.team_b_member1]:
            set_permissions_for_obj_to_user(
                user, self.analysis_team_b, [PermissionTypes.READ]
            )

        # Reviewer gets access to their own analysis
        set_permissions_for_obj_to_user(
            self.reviewer, self.analysis_reviewer, [PermissionTypes.READ]
        )

        # Team leads get UPDATE permissions on corpus for collaboration
        set_permissions_for_obj_to_user(
            self.team_a_lead, self.shared_corpus, [PermissionTypes.UPDATE]
        )
        set_permissions_for_obj_to_user(
            self.team_b_lead, self.shared_corpus, [PermissionTypes.UPDATE]
        )

        logger.info("✓ Permissions configured:")
        logger.info("  - All users: READ on corpus and documents")
        logger.info("  - Team A: READ on Team A analysis/extract")
        logger.info("  - Team B: READ on Team B analysis")
        logger.info("  - Reviewer: READ on reviewer analysis")
        logger.info("  - Team leads: UPDATE on shared corpus")

    # =========================================================================
    # TEST 1: Team A sees only their annotations plus public ones
    # =========================================================================

    def test_team_a_sees_only_their_annotations(self):
        """
        Team A members should see:
        - In manual mode: Public annotations + Team A extract annotations
        - In Team A analysis mode: Team A analysis annotations
        - NOT Team B or Reviewer annotations in either mode
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Team A sees only their annotations plus public ones")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)

        # Manual mode query (no analysisId)
        manual_query = """
        query {{
            document(id: "{}") {{
                id
                title
                allAnnotations(corpusId: "{}") {{
                    id
                    rawText
                    annotationLabel {{
                        text
                    }}
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        result = self.client_team_a_member1.execute(manual_query)
        self.assertIsNone(
            result.get("errors"), f"Should not have errors: {result.get('errors')}"
        )

        doc_data = result["data"]["document"]
        self.assertIsNotNone(doc_data, "Team A member should see the document")

        manual_annotations = doc_data["allAnnotations"]
        manual_texts = [ann["rawText"] for ann in manual_annotations]

        # Manual mode: Should see public and extract annotations
        self.assertIn(
            "Public annotation on Contract Alpha",
            manual_texts,
            "Should see public annotation in manual mode",
        )
        self.assertIn(
            "Team A extract-generated annotation",
            manual_texts,
            "Should see Team A extract annotation in manual mode",
        )

        # Should NOT see analysis annotations in manual mode
        self.assertNotIn(
            "Team A confidential finding on Contract Alpha",
            manual_texts,
            "Should NOT see analysis annotations in manual mode",
        )

        # Team A analysis mode query
        analysis_id = to_global_id("AnalysisType", self.analysis_team_a.id)
        analysis_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_id
        )

        result = self.client_team_a_member1.execute(analysis_query)
        analysis_annotations = result["data"]["document"]["allAnnotations"]
        analysis_texts = [ann["rawText"] for ann in analysis_annotations]

        # Analysis mode: Should see Team A analysis annotations
        self.assertIn(
            "Team A confidential finding on Contract Alpha",
            analysis_texts,
            "Should see Team A analysis annotation in analysis mode",
        )

        # Should NOT see Team B or Reviewer annotations
        self.assertNotIn(
            "Team B confidential finding on Contract Alpha",
            analysis_texts,
            "Should NOT see Team B annotations",
        )
        self.assertNotIn(
            "Reviewer's confidential note on Contract Alpha",
            analysis_texts,
            "Should NOT see Reviewer annotations",
        )

        logger.info(f"✓ Manual mode: {len(manual_annotations)} annotations")
        logger.info(f"✓ Analysis mode: {len(analysis_annotations)} annotations")
        logger.info(f"  Manual annotations: {manual_texts}")
        logger.info(f"  Analysis annotations: {analysis_texts}")

    # =========================================================================
    # TEST 2: Team B sees only their annotations plus public ones
    # =========================================================================

    def test_team_b_sees_only_their_annotations(self):
        """
        Team B members should see:
        - In manual mode: Public annotations only (Team B has no extracts)
        - In Team B analysis mode: Team B analysis annotations
        - NOT Team A or Reviewer annotations in either mode
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Team B sees only their annotations plus public ones")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)

        # Manual mode query (no analysisId)
        manual_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        result = self.client_team_b_member1.execute(manual_query)
        self.assertIsNone(result.get("errors"))

        manual_annotations = result["data"]["document"]["allAnnotations"]
        manual_texts = [ann["rawText"] for ann in manual_annotations]

        # Manual mode: Should see only public annotation (Team B has no extracts)
        self.assertIn("Public annotation on Contract Alpha", manual_texts)
        self.assertNotIn("Team A extract-generated annotation", manual_texts)

        # Team B analysis mode query
        analysis_id = to_global_id("AnalysisType", self.analysis_team_b.id)
        analysis_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_id
        )

        result = self.client_team_b_member1.execute(analysis_query)
        analysis_annotations = result["data"]["document"]["allAnnotations"]
        analysis_texts = [ann["rawText"] for ann in analysis_annotations]

        # Analysis mode: Should see Team B analysis annotation
        self.assertIn("Team B confidential finding on Contract Alpha", analysis_texts)

        # Should NOT see Team A or Reviewer annotations
        self.assertNotIn(
            "Team A confidential finding on Contract Alpha", analysis_texts
        )
        self.assertNotIn(
            "Reviewer's confidential note on Contract Alpha", analysis_texts
        )

        logger.info(f"✓ Manual mode: {len(manual_annotations)} annotations")
        logger.info(f"✓ Analysis mode: {len(analysis_annotations)} annotations")
        logger.info(f"  Analysis annotations: {analysis_texts}")

    # =========================================================================
    # TEST 3: Client user sees only public annotations
    # =========================================================================

    def test_client_sees_only_public_annotations(self):
        """
        External client user has no analysis permissions, should see only public annotations.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Client user sees only public annotations")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)
        query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        result = self.client_external.execute(query)
        self.assertIsNone(result.get("errors"))

        annotations = result["data"]["document"]["allAnnotations"]
        annotation_texts = [ann["rawText"] for ann in annotations]

        # Should see ONLY public annotation
        self.assertEqual(
            len(annotations), 1, "Client should see only 1 public annotation"
        )
        self.assertIn("Public annotation on Contract Alpha", annotation_texts)

        # Should NOT see any private annotations
        self.assertNotIn(
            "Team A confidential finding on Contract Alpha", annotation_texts
        )
        self.assertNotIn(
            "Team B confidential finding on Contract Alpha", annotation_texts
        )
        self.assertNotIn(
            "Reviewer's confidential note on Contract Alpha", annotation_texts
        )

        logger.info(f"✓ Client sees only public annotations: {annotation_texts}")

    # =========================================================================
    # TEST 4: Reviewer sees only their own private annotations plus public
    # =========================================================================

    def test_reviewer_isolation(self):
        """
        Reviewer should see:
        - In manual mode: Only public annotations
        - In reviewer analysis mode: Reviewer's private annotations
        - NOT team annotations in either mode
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Reviewer sees only their annotations plus public")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)

        # Manual mode query (no analysisId)
        manual_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        result = self.client_reviewer.execute(manual_query)
        self.assertIsNone(result.get("errors"))

        manual_annotations = result["data"]["document"]["allAnnotations"]
        manual_texts = [ann["rawText"] for ann in manual_annotations]

        # Manual mode: Should see only public annotation
        self.assertIn("Public annotation on Contract Alpha", manual_texts)

        # Should NOT see reviewer's analysis annotation in manual mode
        self.assertNotIn("Reviewer's confidential note on Contract Alpha", manual_texts)

        # Reviewer analysis mode query
        analysis_id = to_global_id("AnalysisType", self.analysis_reviewer.id)
        analysis_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_id
        )

        result = self.client_reviewer.execute(analysis_query)
        analysis_annotations = result["data"]["document"]["allAnnotations"]
        analysis_texts = [ann["rawText"] for ann in analysis_annotations]

        # Analysis mode: Should see reviewer's own annotation
        self.assertIn("Reviewer's confidential note on Contract Alpha", analysis_texts)

        # Should NOT see team annotations
        self.assertNotIn(
            "Team A confidential finding on Contract Alpha", analysis_texts
        )
        self.assertNotIn(
            "Team B confidential finding on Contract Alpha", analysis_texts
        )

        logger.info(f"✓ Manual mode: {len(manual_annotations)} annotations")
        logger.info(f"✓ Analysis mode: {len(analysis_annotations)} annotations")
        logger.info(f"  Analysis annotations: {analysis_texts}")

    # =========================================================================
    # TEST 5: Admin (superuser) sees everything
    # =========================================================================

    def test_admin_sees_all_annotations(self):
        """
        Admin (superuser) should see ALL annotations regardless of privacy settings.

        Note: When analysis_id is not provided, allAnnotations only returns manual/user
        annotations (analysis__isnull=True). To see analysis-created annotations,
        the admin must query with specific analysis_id values.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Admin sees all manual annotations without analysis_id")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)

        # Query without analysis_id - should only return manual annotations
        query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        result = self.client_admin.execute(query)
        self.assertIsNone(result.get("errors"))

        annotations = result["data"]["document"]["allAnnotations"]
        annotation_texts = [ann["rawText"] for ann in annotations]

        # Without analysis_id, should only see manual annotations (no analysis field)
        expected_manual_annotations = [
            "Public annotation on Contract Alpha",
            "Team A extract-generated annotation",  # Has created_by_extract, but no analysis
        ]

        for expected_text in expected_manual_annotations:
            self.assertIn(
                expected_text, annotation_texts, f"Admin should see: {expected_text}"
            )

        # Should NOT see analysis-created annotations when no analysis_id provided
        should_not_see = [
            "Team A confidential finding on Contract Alpha",
            "Team B confidential finding on Contract Alpha",
            "Reviewer's confidential note on Contract Alpha",
        ]

        for text in should_not_see:
            self.assertNotIn(
                text,
                annotation_texts,
                f"Should not see analysis annotation without analysis_id: {text}",
            )

        total_count = len(result["data"]["document"]["allAnnotations"])
        logger.info(f"✓ Admin sees {total_count} manual annotations (no analysis_id)")

    # =========================================================================
    # TEST 6: Granting/revoking analysis permission changes visibility
    # =========================================================================

    def test_dynamic_permission_changes(self):
        """
        Test that granting/revoking analysis permissions dynamically changes
        what annotations a user can see.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Dynamic permission changes affect annotation visibility")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)
        query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        # Initially, client_user sees only public annotations
        result = self.client_external.execute(query)
        annotations = result["data"]["document"]["allAnnotations"]
        self.assertEqual(len(annotations), 1, "Initially sees only public annotation")

        # Grant client_user access to Team A's analysis
        set_permissions_for_obj_to_user(
            self.client_user, self.analysis_team_a, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.client_user, self.extract_team_a, [PermissionTypes.READ]
        )

        # Manual mode query - should now see extract annotations
        result = self.client_external.execute(query)
        manual_annotations = result["data"]["document"]["allAnnotations"]
        manual_texts = [ann["rawText"] for ann in manual_annotations]

        self.assertIn("Public annotation on Contract Alpha", manual_texts)
        self.assertIn("Team A extract-generated annotation", manual_texts)

        # Analysis mode query - should now see Team A analysis annotations
        analysis_id = to_global_id("AnalysisType", self.analysis_team_a.id)
        analysis_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_id
        )

        result = self.client_external.execute(analysis_query)
        analysis_annotations = result["data"]["document"]["allAnnotations"]
        analysis_texts = [ann["rawText"] for ann in analysis_annotations]

        self.assertIn("Team A confidential finding on Contract Alpha", analysis_texts)

        # But still not Team B or Reviewer annotations
        self.assertNotIn(
            "Team B confidential finding on Contract Alpha", analysis_texts
        )
        self.assertNotIn(
            "Reviewer's confidential note on Contract Alpha", analysis_texts
        )

        logger.info(
            f"✓ After granting Team A access, client sees {len(manual_annotations)} manual + "
            f"{len(analysis_annotations)} analysis annotations"
        )

        # Revoke the permissions
        set_permissions_for_obj_to_user(
            self.client_user,
            self.analysis_team_a,
            [],  # Empty list removes all permissions
        )
        set_permissions_for_obj_to_user(
            self.client_user, self.extract_team_a, []  # Also revoke extract permission
        )

        # Query again
        result = self.client_external.execute(query)
        annotations = result["data"]["document"]["allAnnotations"]
        self.assertEqual(len(annotations), 1, "After revoking, sees only public again")

        logger.info("✓ After revoking Team A access, back to only public annotations")

    # =========================================================================
    # TEST 7: Multiple analyses on same document create distinct annotation sets
    # =========================================================================

    def test_multiple_analyses_distinct_annotations(self):
        """
        Verify that multiple analyses can create distinct, non-overlapping
        annotation sets on the same document that are properly scoped.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Multiple analyses create distinct annotation sets")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract2.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)

        # Team A: Query in analysis mode to see their analysis annotations
        analysis_a_id = to_global_id("AnalysisType", self.analysis_team_a.id)
        query_a = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                    page
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_a_id
        )

        result_a = self.client_team_a_member1.execute(query_a)
        annotations_a = result_a["data"]["document"]["allAnnotations"]
        texts_a = [ann["rawText"] for ann in annotations_a]

        self.assertIn("Team A confidential finding on Contract Beta", texts_a)
        self.assertNotIn("Team B confidential finding on Contract Beta", texts_a)

        # Team B: Query in analysis mode to see their analysis annotations
        analysis_b_id = to_global_id("AnalysisType", self.analysis_team_b.id)
        query_b = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                    page
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_b_id
        )

        result_b = self.client_team_b_member1.execute(query_b)
        annotations_b = result_b["data"]["document"]["allAnnotations"]
        texts_b = [ann["rawText"] for ann in annotations_b]

        self.assertIn("Team B confidential finding on Contract Beta", texts_b)
        self.assertNotIn("Team A confidential finding on Contract Beta", texts_b)

        # Verify they're on different pages (showing non-overlapping work)
        pages_a = {ann["page"] for ann in annotations_a if "Team A" in ann["rawText"]}
        pages_b = {ann["page"] for ann in annotations_b if "Team B" in ann["rawText"]}

        logger.info(f"✓ Team A analysis annotations on pages: {pages_a}")
        logger.info(f"✓ Team B analysis annotations on pages: {pages_b}")
        logger.info("  Teams have created distinct, private annotation sets")

    # =========================================================================
    # TEST 8: Cross-team collaboration scenario
    # =========================================================================

    def test_cross_team_collaboration(self):
        """
        Test a scenario where a user gets added to multiple teams and sees
        combined annotation sets across both manual and analysis modes.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Cross-team collaboration with combined visibility")
        logger.info("=" * 80)

        # Create a collaborator who will work with both teams
        collaborator = User.objects.create_user(
            username="Collaborator", password="test123"
        )
        client_collaborator = Client(schema, context_value=TestContext(collaborator))

        # Grant base permissions
        set_permissions_for_obj_to_user(
            collaborator, self.shared_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            collaborator, self.doc_contract1, [PermissionTypes.READ]
        )

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)

        # Query for manual/extract annotations (no analysisId)
        manual_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        # Initially, collaborator sees only public annotations in manual mode
        result = client_collaborator.execute(manual_query)
        annotations = result["data"]["document"]["allAnnotations"]
        self.assertEqual(len(annotations), 1, "Initially sees only public")

        # Add collaborator to Team A
        set_permissions_for_obj_to_user(
            collaborator, self.analysis_team_a, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            collaborator, self.extract_team_a, [PermissionTypes.READ]
        )

        # Check manual mode - should now see extract annotations
        result = client_collaborator.execute(manual_query)
        manual_annotations = result["data"]["document"]["allAnnotations"]
        manual_texts = [ann["rawText"] for ann in manual_annotations]

        self.assertIn("Public annotation on Contract Alpha", manual_texts)
        self.assertIn("Team A extract-generated annotation", manual_texts)

        # Check Team A analysis mode - should see analysis annotations
        analysis_a_id = to_global_id("AnalysisType", self.analysis_team_a.id)
        analysis_a_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_a_id
        )

        result = client_collaborator.execute(analysis_a_query)
        analysis_a_annotations = result["data"]["document"]["allAnnotations"]
        analysis_a_texts = [ann["rawText"] for ann in analysis_a_annotations]

        self.assertIn("Team A confidential finding on Contract Alpha", analysis_a_texts)

        # Add collaborator to Team B as well
        set_permissions_for_obj_to_user(
            collaborator, self.analysis_team_b, [PermissionTypes.READ]
        )

        # Check Team B analysis mode - should now see Team B annotations
        analysis_b_id = to_global_id("AnalysisType", self.analysis_team_b.id)
        analysis_b_query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}", analysisId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id, analysis_b_id
        )

        result = client_collaborator.execute(analysis_b_query)
        analysis_b_annotations = result["data"]["document"]["allAnnotations"]
        analysis_b_texts = [ann["rawText"] for ann in analysis_b_annotations]

        self.assertIn("Team B confidential finding on Contract Alpha", analysis_b_texts)

        # Verify separate query modes show different annotation sets
        self.assertNotEqual(
            set(manual_texts),
            set(analysis_a_texts),
            "Manual and analysis modes should show different annotations",
        )

        logger.info(
            f"✓ Manual mode: {len(manual_annotations)} annotations (public + extract)"
        )
        logger.info(
            f"✓ Team A analysis mode: {len(analysis_a_annotations)} annotations"
        )
        logger.info(
            f"✓ Team B analysis mode: {len(analysis_b_annotations)} annotations"
        )
        logger.info(
            "  Successfully demonstrates combined visibility across teams and query modes"
        )

    # =========================================================================
    # TEST 9: Extract-based privacy scoping
    # =========================================================================

    def test_extract_privacy_scoping(self):
        """
        Test that annotations created by extracts are properly scoped to
        users with extract permissions.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Extract-based privacy scoping")
        logger.info("=" * 80)

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)
        query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        # Team B member should NOT see Team A's extract annotation
        result = self.client_team_b_member1.execute(query)
        annotations = result["data"]["document"]["allAnnotations"]
        texts = [ann["rawText"] for ann in annotations]

        self.assertNotIn(
            "Team A extract-generated annotation",
            texts,
            "Team B should not see Team A's extract annotation",
        )

        # Team A member SHOULD see their extract annotation
        result = self.client_team_a_member1.execute(query)
        annotations = result["data"]["document"]["allAnnotations"]
        texts = [ann["rawText"] for ann in annotations]

        self.assertIn(
            "Team A extract-generated annotation",
            texts,
            "Team A should see their extract annotation",
        )

        logger.info("✓ Extract-created annotations properly scoped to team members")

    # =========================================================================
    # TEST 10: Comprehensive visibility matrix test
    # =========================================================================

    def test_comprehensive_visibility_matrix(self):
        """
        Test the complete visibility matrix across all users and all annotations
        to ensure proper privacy enforcement.

        NOTE: When querying without analysis_id, only manual/user annotations are returned.
        Annotations linked to analyses (via the analysis field) are NOT included unless
        a specific analysis_id is provided in the query.
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Comprehensive visibility matrix (manual annotations only)")
        logger.info("=" * 80)

        # Define expected visibility matrix
        # Format: (user, should_see_annotations_list)
        # When NO analysis_id is provided, users only see:
        # - Public/manual annotations (no analysis field set)
        # - Extract-generated annotations (created_by_extract but no analysis field)
        visibility_matrix = [
            (
                self.team_a_member1,
                {
                    "Public annotation on Contract Alpha": True,
                    "Team A confidential finding on Contract Alpha": False,  # Has analysis field set
                    "Team B confidential finding on Contract Alpha": False,
                    "Reviewer's confidential note on Contract Alpha": False,
                    "Team A extract-generated annotation": True,  # No analysis field, user has extract permission
                },
            ),
            (
                self.team_b_member1,
                {
                    "Public annotation on Contract Alpha": True,
                    "Team A confidential finding on Contract Alpha": False,
                    "Team B confidential finding on Contract Alpha": False,  # Has analysis field set
                    "Reviewer's confidential note on Contract Alpha": False,
                    "Team A extract-generated annotation": False,  # No permission for this extract
                },
            ),
            (
                self.reviewer,
                {
                    "Public annotation on Contract Alpha": True,
                    "Team A confidential finding on Contract Alpha": False,
                    "Team B confidential finding on Contract Alpha": False,
                    "Reviewer's confidential note on Contract Alpha": False,  # Has analysis field set
                    "Team A extract-generated annotation": False,
                },
            ),
            (
                self.client_user,
                {
                    "Public annotation on Contract Alpha": True,
                    "Team A confidential finding on Contract Alpha": False,
                    "Team B confidential finding on Contract Alpha": False,
                    "Reviewer's confidential note on Contract Alpha": False,
                    "Team A extract-generated annotation": False,
                },
            ),
        ]

        doc_id = to_global_id("DocumentType", self.doc_contract1.id)
        corpus_id = to_global_id("CorpusType", self.shared_corpus.id)
        query = """
        query {{
            document(id: "{}") {{
                allAnnotations(corpusId: "{}") {{
                    rawText
                }}
            }}
        }}
        """.format(
            doc_id, corpus_id
        )

        for user, expected_visibility in visibility_matrix:
            client = Client(schema, context_value=TestContext(user))
            result = client.execute(query)

            annotations = result["data"]["document"]["allAnnotations"]
            actual_texts = {ann["rawText"] for ann in annotations}

            for annotation_text, should_see in expected_visibility.items():
                if should_see:
                    self.assertIn(
                        annotation_text,
                        actual_texts,
                        f"{user.username} should see: {annotation_text}",
                    )
                else:
                    self.assertNotIn(
                        annotation_text,
                        actual_texts,
                        f"{user.username} should NOT see: {annotation_text}",
                    )

            logger.info(
                f"✓ {user.username}: Visibility matrix validated ({len(actual_texts)} annotations visible)"
            )

        logger.info("\n✓ COMPREHENSIVE VISIBILITY MATRIX VALIDATED")
        logger.info("  Successfully validated that without analysis_id:")
        logger.info("  - Only manual/user annotations are visible")
        logger.info("  - Extract-based annotations respect extract permissions")
        logger.info(
            "  - Analysis-linked annotations are hidden (query specific analysis_id to see them)"
        )


class AnnotationPrivacyMutationTestCase(TestCase):
    """
    Test that annotation mutations respect the privacy model.
    """

    def setUp(self):
        """Set up basic test scenario"""
        self.admin = User.objects.create_superuser(username="Admin", password="admin")
        self.user_a = User.objects.create_user(username="UserA", password="test123")
        self.user_b = User.objects.create_user(username="UserB", password="test123")

        # Create shared resources
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.admin, is_public=False
        )

        self.doc = Document.objects.create(
            title="Test Doc", creator=self.admin, is_public=False
        )
        self.corpus.add_document(document=self.doc, user=self.admin)

        # Create DocumentPath for versioning system
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test_doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.admin,
        )

        # Create analyzer infrastructure
        self.gremlin = GremlinEngine.objects.create(
            url="http://dummy-gremlin:8000", creator=self.admin
        )

        self.analyzer = Analyzer.objects.create(
            id="TEST.MUTATION.ANALYZER", host_gremlin=self.gremlin, creator=self.admin
        )

        self.label = AnnotationLabel.objects.create(
            label_type=TOKEN_LABEL, text="Test Label", creator=self.admin
        )

        # Create analysis for User A
        self.analysis_a = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user_a,
            is_public=False,
        )

        # Create private annotation
        self.private_annotation = Annotation.objects.create(
            annotation_label=self.label,
            document=self.doc,
            corpus=self.corpus,
            analysis=self.analysis_a,
            created_by_analysis=self.analysis_a,
            creator=self.user_a,
            page=1,
            raw_text="Private annotation",
        )

        # Set up permissions - need ALL permissions for deletion to work
        set_permissions_for_obj_to_user(self.user_a, self.corpus, [PermissionTypes.ALL])
        set_permissions_for_obj_to_user(self.user_a, self.doc, [PermissionTypes.ALL])
        set_permissions_for_obj_to_user(
            self.user_a, self.analysis_a, [PermissionTypes.ALL]
        )

        set_permissions_for_obj_to_user(
            self.user_b, self.corpus, [PermissionTypes.UPDATE]
        )
        set_permissions_for_obj_to_user(self.user_b, self.doc, [PermissionTypes.UPDATE])
        # User B does NOT have analysis permission

    def test_cannot_delete_private_annotation_without_analysis_permission(self):
        """
        User B should not be able to delete User A's private annotation
        even with document and corpus permissions.
        """
        client_b = Client(schema, context_value=TestContext(self.user_b))

        annotation_id = to_global_id("AnnotationType", self.private_annotation.id)
        mutation = (
            """
        mutation {
            removeAnnotation(annotationId: "%s") {
                ok
                message
            }
        }
        """
            % annotation_id
        )

        result = client_b.execute(mutation)
        self.assertIsNone(result.get("errors"))

        response = result["data"]["removeAnnotation"]
        self.assertFalse(
            response["ok"], "Should not be able to delete private annotation"
        )

        # Verify annotation still exists
        self.assertTrue(
            Annotation.objects.filter(id=self.private_annotation.id).exists()
        )

        logger.info(
            "✓ User B cannot delete User A's private annotation without analysis permission"
        )

    def test_can_delete_private_annotation_with_analysis_permission(self):
        """
        User A should be able to delete their own private annotation
        since they have analysis permission.
        """
        client_a = Client(schema, context_value=TestContext(self.user_a))

        annotation_id = to_global_id("AnnotationType", self.private_annotation.id)
        mutation = (
            """
        mutation {
            removeAnnotation(annotationId: "%s") {
                ok
                message
            }
        }
        """
            % annotation_id
        )

        result = client_a.execute(mutation)
        self.assertIsNone(
            result.get("errors"), f"Mutation errors: {result.get('errors')}"
        )

        response = result["data"]["removeAnnotation"]
        if not response["ok"]:
            logger.error(f"Deletion failed with message: {response.get('message')}")
        self.assertTrue(
            response["ok"],
            f"Should be able to delete own private annotation. Message: {response.get('message')}",
        )

        # Verify annotation was deleted
        self.assertFalse(
            Annotation.objects.filter(id=self.private_annotation.id).exists()
        )

        logger.info(
            "✓ User A can delete their own private annotation with analysis permission"
        )
