import logging
import pathlib
from random import randrange

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import Signal
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.analyzer.signals import install_gremlin_on_creation
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tasks.permissioning_tasks import (
    make_analysis_public_task,
    make_corpus_public_task,
)
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import (
    get_users_permissions_for_obj,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class PermissioningTestCase(TestCase):
    """
    Tests that permissioning system works and those who should be able to see things, can, and those
    who should not, cannot.
    """

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def tearDown(self):

        # Reconnect the django signals for gremlinengine create
        post_save.connect(
            install_gremlin_on_creation,
            sender=GremlinEngine,
            dispatch_uid="install_gremlin_on_creation",
        )

    def setUp(self):

        # We're turning off signals so we can create a dummy gremlin and analyzer
        # without OC attempting to actually install it.
        Signal.disconnect(
            post_save,
            receiver=install_gremlin_on_creation,
            sender=GremlinEngine,
            dispatch_uid="Signal.disconnect",
        )

        # Create one regular user (and accompanying GraphQL client)
        with transaction.atomic():
            self.user = User.objects.create_user(username="Bob", password="12345678")
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        # Create another regular user (and accompanying GraphQL client), so we can test they can be walled off from
        # each other's work
        with transaction.atomic():
            self.user_2 = User.objects.create_user(
                username="Frodo", password="123456789"
            )
        self.graphene_client_2 = Client(schema, context_value=TestContext(self.user_2))

        # Create a superuser (and accompanying GraphQL client), so we can test things that require superuser permissions
        with transaction.atomic():
            self.superuser = User.objects.create_superuser(
                username="Super", password="duper"
            )
        self.elevated_graphene_client = Client(
            schema, context_value=TestContext(self.superuser)
        )

        # Create a test corpus
        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Analysis Corpus", creator=self.user, backend_lock=False
            )

        # Grant permission to user one
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        self.global_corpus_id = to_global_id("CorpusType", self.corpus.id)

        # Generate 10 docs for corpus:
        self.doc_ids = []
        for index in range(0, 10):
            with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
                pdf_contents = ContentFile(test_pdf.read())

            with transaction.atomic():
                document = Document.objects.create(
                    title=f"TestDoc{index}",
                    description="Manually created",
                    creator=self.user,
                )
                document.pdf_file.save("dummy_file.pdf", pdf_contents)
                # Note: Don't assign permission here - do it after add_document()
                # because corpus isolation creates a copy

            self.doc_ids.append(document.id)
            logger.info(f"Created document with id: {document.id}")

        # Link docs to corpus and assign permissions to corpus copies
        self.corpus_doc_ids = []
        with transaction.atomic():
            for doc_id in self.doc_ids:
                doc = Document.objects.get(id=doc_id)
                corpus_doc, status, path = self.corpus.add_document(
                    document=doc, user=self.user
                )
                self.corpus_doc_ids.append(corpus_doc.id)
                # Assign permission to the corpus copy (not the original)
                set_permissions_for_obj_to_user(
                    self.user, corpus_doc, [PermissionTypes.READ]
                )
        # Update doc_ids to point to corpus copies for annotation creation
        self.doc_ids = self.corpus_doc_ids

        #############################################################################################
        # Analysis-Related Dummy Objects to Test "Make Public" Logic                                #
        #############################################################################################

        # 1) Create a dummy gremlin
        self.gremlin_url = "http://localhost:8000"
        with transaction.atomic():
            self.gremlin = GremlinEngine.objects.create(
                url=self.gremlin_url, creator=self.user
            )

        # 2) Create dummy analyzer for that dummy Gremlin
        with transaction.atomic():
            self.analyzer = Analyzer.objects.create(
                id="DO.NOTHING.ANALYZER", host_gremlin=self.gremlin, creator=self.user
            )

        # 3) Create dummy analysis of our test corpus
        with transaction.atomic():
            self.analysis = Analysis.objects.create(
                analyzer_id=self.analyzer.id,
                analyzed_corpus_id=self.corpus.id,
                creator=self.user,
            )
        self.global_analysis_id = to_global_id("AnalysisType", self.analysis.id)

        # 4) Create dummy labels for the analyzer
        with transaction.atomic():
            self.dummy_label = AnnotationLabel.objects.create(
                label_type=TOKEN_LABEL,
                analyzer=self.analyzer,
                creator=self.user,
            )

        # 5) Create some annotations for analysis
        for i in range(0, 5):
            with transaction.atomic():
                Annotation.objects.create(
                    annotation_label=self.dummy_label,
                    document_id=self.doc_ids[randrange(len(self.doc_ids))],
                    corpus=self.corpus,
                    analysis=self.analysis,
                    creator=self.user,
                )

    def __test_user_retrieval_permissions(self):

        logger.info(
            "----- TEST USER OBJ RETRIEVAL PERMISSIONS WORK AS DESIGNED --------------------------------------"
        )

        request_corpuses = """
            {
              corpuses {
                totalCount
                edges {
                  node {
                    id
                    myPermissions
                    documents {
                      totalCount
                      edges {
                        node {
                          id
                          myPermissions
                        }
                      }
                    }
                    labelSet {
                      id
                      myPermissions
                    }
                    annotations {
                      totalCount
                      edges {
                        node {
                          id
                          myPermissions
                          structural
                        }
                      }
                    }
                  }
                }
              }
            }
        """

        user_one_corpus_response = self.graphene_client.execute(request_corpuses)
        logger.info(f"user_one_corpus_response: {user_one_corpus_response}")

        # User one can see 2 corpuses: their auto-created personal corpus + the test corpus
        self.assertEqual(user_one_corpus_response["data"]["corpuses"]["totalCount"], 2)

        # User one should have PermissionType.READ for corpus
        self.assertTrue(self.corpus.user_can(self.user, PermissionTypes.READ))
        # User twp should NOT have PermissionType.READ for corpus
        self.assertFalse(self.corpus.user_can(self.user_2, PermissionTypes.READ))

        # User one should have PermissionType.UPDATE for corpus
        self.assertTrue(self.corpus.user_can(self.user, PermissionTypes.UPDATE))
        # User twp should NOT have PermissionType.UPDATE for corpus
        self.assertFalse(self.corpus.user_can(self.user_2, PermissionTypes.UPDATE))

        # User one should have PermissionType.DELETE for corpus
        self.assertTrue(self.corpus.user_can(self.user, PermissionTypes.DELETE))
        # User two should NOT have PermissionType.DELETE for corpus
        self.assertFalse(self.corpus.user_can(self.user_2, PermissionTypes.DELETE))

        # User one should have PermissionType.PERMISSION for corpus
        self.assertTrue(self.corpus.user_can(self.user, PermissionTypes.PERMISSION))
        # User two should NOT have PermissionType.PERMISSION for corpus
        self.assertFalse(self.corpus.user_can(self.user_2, PermissionTypes.PERMISSION))

        # User one should have PermissionType.PUBLISH for corpus
        self.assertTrue(self.corpus.user_can(self.user, PermissionTypes.PUBLISH))
        # User twp should NOT have PermissionType.PUBLISH for corpus
        self.assertFalse(self.corpus.user_can(self.user_2, PermissionTypes.PUBLISH))

        # User one should have PermissionType.ALL for corpus
        self.assertTrue(self.corpus.user_can(self.user, PermissionTypes.ALL))

        # User two should NOT have PermissionType.ALL for corpus
        self.assertFalse(self.corpus.user_can(self.user_2, PermissionTypes.ALL))
        logger.info(
            f"Retrieved permissions: "
            f"{user_one_corpus_response['data']['corpuses']['edges'][0]['node']['myPermissions']}"
        )
        # Now check that we're seeing proper permission annotations
        self.assertEqual(
            set(
                user_one_corpus_response["data"]["corpuses"]["edges"][0]["node"][
                    "myPermissions"
                ]
            ),
            {
                "permission_corpus",
                "publish_corpus",
                "create_corpus",
                "read_corpus",
                "update_corpus",
                "remove_corpus",
                "comment_corpus",
            },
        )
        for doc in user_one_corpus_response["data"]["corpuses"]["edges"][0]["node"][
            "documents"
        ]["edges"]:
            self.assertEqual(doc["node"]["myPermissions"], ["read_document"])

        # Check annotation permissions - they should inherit from document and corpus
        # Since user has READ on documents and ALL on corpus, annotations get READ
        # (most restrictive permission wins)
        for ann in user_one_corpus_response["data"]["corpuses"]["edges"][0]["node"][
            "annotations"
        ]["edges"]:
            ann_permissions = ann["node"]["myPermissions"]
            # Annotations inherit minimum of document (READ) and corpus (ALL) = READ
            self.assertIn(
                "read_annotation",
                ann_permissions,
                "Annotations should have READ permission inherited from document",
            )
            # Should NOT have update even though corpus has ALL, because document only has READ
            self.assertNotIn(
                "update_annotation",
                ann_permissions,
                "Annotations should NOT have UPDATE (limited by document READ)",
            )

        user_two_corpus_response = self.graphene_client_2.execute(request_corpuses)
        logger.info(f"user_two_corpus_response: {user_two_corpus_response}")

        # User two can only see their auto-created personal corpus (not user_one's test corpus)
        self.assertEqual(user_two_corpus_response["data"]["corpuses"]["totalCount"], 1)

    def __test_make_corpus_public_mutation(self):
        """
        Test the SetCorpusVisibility mutation (replaced MakeCorpusPublic).

        SetCorpusVisibility allows:
        - Corpus creator (owner)
        - Users with PERMISSION permission
        - Superusers

        This test verifies:
        1. A non-creator user without PERMISSION cannot change visibility
        2. The creator can change visibility
        """
        logger.info(
            "----- TEST SET CORPUS VISIBILITY MUTATION -------------------------------------------------------"
        )

        set_visibility_mutation = """
            mutation ($corpusId: ID!, $isPublic: Boolean!) {
              setCorpusVisibility(corpusId: $corpusId, isPublic: $isPublic) {
                ok
                message
              }
            }
        """
        variables = {"corpusId": self.global_corpus_id, "isPublic": True}

        # This should fail - user_2 (Frodo) is NOT the creator and has no PERMISSION
        prohibited_graphql_response = self.graphene_client_2.execute(
            set_visibility_mutation,
            variable_values=variables,
        )
        logger.info(f"Improper permission response: {prohibited_graphql_response}")
        self.assertEqual(
            prohibited_graphql_response["data"]["setCorpusVisibility"]["ok"], False
        )
        self.assertEqual(
            prohibited_graphql_response["data"]["setCorpusVisibility"]["message"],
            "Corpus not found or you don't have permission",
        )

        # THIS should work - request from creator (Bob/self.user)
        permissioned_graphql_response = self.graphene_client.execute(
            set_visibility_mutation,
            variable_values=variables,
        )

        logger.info(
            f"Set visibility call return value: {permissioned_graphql_response}"
        )

        self.assertEqual(
            permissioned_graphql_response["data"]["setCorpusVisibility"]["ok"], True
        )
        self.assertEqual(
            permissioned_graphql_response["data"]["setCorpusVisibility"]["message"],
            "Making corpus public. This may take a moment for large corpuses.",
        )

    def __test_make_corpus_public_task(self):

        logger.info(
            "----- TEST MAKE CORPUS PUBLIC TASK --------------------------------------------------------------"
        )

        make_public_task_results = (
            make_corpus_public_task.si(corpus_id=self.corpus.id).apply().get()
        )
        self.assertEqual(True, make_public_task_results["ok"])
        self.assertEqual(
            "SUCCESS - Corpus and related objects are now public",
            make_public_task_results["message"],
        )

    def __test_make_analysis_public_mutation(self):
        make_public_mutation_request = """
                    mutation ($analysisId: String!) {
                      makeAnalysisPublic(analysisId: $analysisId) {
                        ok
                        message
                      }
                    }
                """
        variables = {"analysisId": self.global_analysis_id}

        # This should fail (only superuser can do this)
        prohibited_graphql_response = self.graphene_client.execute(
            make_public_mutation_request,
            variable_values=variables,
        )
        logger.info(f"Improper permission response: {prohibited_graphql_response}")
        self.assertEqual(
            prohibited_graphql_response["data"]["makeAnalysisPublic"], None
        )
        self.assertEqual(
            prohibited_graphql_response["errors"][0]["message"],
            "You do not have permission to perform this action",
        )

        # THIS should work - request make public with superuser
        permissioned_graphql_response = self.elevated_graphene_client.execute(
            make_public_mutation_request,
            variable_values=variables,
        )

        # Now anonymous requests should work to request the corpus.
        logger.info(f"Make public call return value: {permissioned_graphql_response}")

        self.assertEqual(
            permissioned_graphql_response["data"]["makeAnalysisPublic"]["ok"], True
        )
        self.assertEqual(
            permissioned_graphql_response["data"]["makeAnalysisPublic"]["message"],
            "Starting an OpenContracts worker to make your analysis public! Underlying corpus must be made public too!",
        )

    def __test_make_analysis_public_task(self):

        logger.info(
            "----- TEST MAKE ANALYSIS PUBLIC TASK ------------------------------------------------------------"
        )

        make_public_task_results = (
            make_analysis_public_task.si(analysis_id=self.analysis.id).apply().get()
        )
        self.assertEqual(True, make_public_task_results["ok"])
        self.assertEqual(
            "SUCCESS - Analysis is Public", make_public_task_results["message"]
        )

    def __test_only_permissioned_user_can_delete_public_corpus(self):

        logger.info(
            "----- TEST THAT ONLY PERMISSIONED USER CAN DELETE OBJECT ----------------------------------------"
        )

        delete_corpus_request = """
            mutation ($id: String!) {
                deleteCorpus(id: $id) {
                  ok
                  message
                }
            }
        """
        variables = {"id": self.global_corpus_id}

        prohibited_graphql_response = self.graphene_client_2.execute(
            delete_corpus_request,
            variable_values=variables,
        )
        logger.info(f"Improper permission response: {prohibited_graphql_response}")
        # IDOR prevention: Phase D's get_for_user_or_none renders a single
        # unified "<resource> not found or you don't have permission..."
        # response (ok=False) instead of leaking the existence/permission
        # distinction via a separate DoesNotExist error.
        delete_payload = prohibited_graphql_response["data"]["deleteCorpus"]
        self.assertIsNotNone(delete_payload)
        self.assertFalse(delete_payload["ok"])
        self.assertIn(
            "not found or you don't have permission", delete_payload["message"]
        )
        self.assertNotIn("errors", prohibited_graphql_response)

    def __test_permission_annotator(self):

        logger.info(
            "----- TEST PERMISSION ANNOTATIONS WORK PROPERLY ----------------------------------------------------------"
        )

        request_corpus_query = """
           query getCorpus($id: ID!) {
             corpus(id: $id) {
               id
               myPermissions
             }
           }
           """
        variables = {"id": self.global_corpus_id}

        full_permission_response = self.graphene_client.execute(
            request_corpus_query, variables=variables
        )
        logger.info(
            f"\tTest that fully permissioned user gets right annotations... {full_permission_response}"
        )

        self.assertEqual(
            {
                "permission_corpus",
                "publish_corpus",
                "create_corpus",
                "read_corpus",
                "update_corpus",
                "remove_corpus",
                "comment_corpus",
            },
            set(full_permission_response["data"]["corpus"]["myPermissions"]),
        )
        logger.info("\tSUCCESS!")

        # Test provisioning and de-provisioning permissions works properly by slowly adding
        # permissions (and then checking the annotated myPermissions field each time) and then slowly
        # removing permissions (again, checking each time that the annotated my Permissions field changes).
        logger.info(f"Fully-permissioned response: {full_permission_response}")

        # Add Read and check it shows up on annotator
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.corpus,
            permissions=[PermissionTypes.READ],
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )
        logger.info(f"Read-only response: {user_two_permission_response}")
        self.assertEqual(
            {"read_corpus"},
            set(user_two_permission_response["data"]["corpus"]["myPermissions"]),
        )

        # Add Delete and check it shows up on annotator
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.corpus,
            permissions=[PermissionTypes.READ, PermissionTypes.DELETE],
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )
        self.assertEqual(
            {"read_corpus", "remove_corpus"},
            set(user_two_permission_response["data"]["corpus"]["myPermissions"]),
        )

        # Add update permissions and check it shows up
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.corpus,
            permissions=[
                PermissionTypes.READ,
                PermissionTypes.DELETE,
                PermissionTypes.UPDATE,
            ],
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )
        self.assertEqual(
            {"read_corpus", "remove_corpus", "update_corpus"},
            set(user_two_permission_response["data"]["corpus"]["myPermissions"]),
        )

        # Add publish permissions and check it shows up
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.corpus,
            permissions=[
                PermissionTypes.READ,
                PermissionTypes.DELETE,
                PermissionTypes.UPDATE,
                PermissionTypes.PUBLISH,
            ],
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )
        self.assertEqual(
            {"read_corpus", "remove_corpus", "update_corpus", "publish_corpus"},
            set(user_two_permission_response["data"]["corpus"]["myPermissions"]),
        )

        # Add permission permissions and check it shows up
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.corpus,
            permissions=[
                PermissionTypes.READ,
                PermissionTypes.DELETE,
                PermissionTypes.UPDATE,
                PermissionTypes.PUBLISH,
                PermissionTypes.PERMISSION,
            ],
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )
        self.assertEqual(
            {
                "read_corpus",
                "remove_corpus",
                "update_corpus",
                "publish_corpus",
                "permission_corpus",
            },
            set(user_two_permission_response["data"]["corpus"]["myPermissions"]),
        )

        # Take user's permissions down to just READ and DELETE
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.corpus,
            permissions=[
                PermissionTypes.READ,
                PermissionTypes.DELETE,
            ],
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )
        self.assertEqual(
            {"read_corpus", "remove_corpus"},
            set(user_two_permission_response["data"]["corpus"]["myPermissions"]),
        )

        # Remove ALL permissions for user and make sure nothing shows up in annotation
        set_permissions_for_obj_to_user(
            user_val=self.user_2, instance=self.corpus, permissions=[]
        )
        user_two_permission_response = self.graphene_client_2.execute(
            request_corpus_query, variables=variables
        )

        raw_permission_list = get_users_permissions_for_obj(
            user=self.user_2, instance=self.corpus, include_group_permissions=True
        )
        logger.info(f"Is corpus public: {self.corpus.is_public}")
        logger.info(f"Raw permissions list: {raw_permission_list}")

        logger.info(
            f"Response when all permissions removed: {user_two_permission_response}"
        )
        self.assertEqual(None, user_two_permission_response["data"]["corpus"])

    def __test_actual_analysis_deletion(self):
        """
        This runs only AFTER user has been granted delete permission
        """

        logger.info(
            "----- TEST PROPERLY PROVISIONED USER CAN DELETE ANALYSIS ENTIRELY ----------------------------------------"
        )

        # First give user 2 permissions
        set_permissions_for_obj_to_user(
            user_val=self.user_2,
            instance=self.analysis,
            permissions=[PermissionTypes.DELETE],
        )

        delete_corpus_request = """
                    mutation ($id: String!) {
                        deleteAnalysis(id: $id) {
                          ok
                          message
                        }
                    }
                """
        variables = {"id": self.global_corpus_id}

        successful_deletion_response = self.graphene_client_2.execute(
            delete_corpus_request,
            variable_values=variables,
        )
        logger.info(
            f"Properly-permissioned deletion response: {successful_deletion_response}"
        )
        # self.assertEqual(prohibited_graphql_response["data"]["deleteCorpus"], None)
        # self.assertEqual(
        #     prohibited_graphql_response["errors"][0]["message"],
        #     "You do no have sufficient permissions to delete requested object",
        # )

    def test_permissions(self):
        """
        Test that a user can access the objects they have permission to see and cannot
        access objects they don't have permissions to see.
        """

        self.__test_user_retrieval_permissions()
        self.__test_only_permissioned_user_can_delete_public_corpus()
        self.__test_permission_annotator()
        self.__test_make_corpus_public_mutation()
        self.__test_make_corpus_public_task()
        self.__test_make_analysis_public_mutation()
        self.__test_make_analysis_public_task()
        self.__test_actual_analysis_deletion()

    def test_user_feedback_visibility(self):
        """Feedback visibility follows the commented annotation's
        visibility (per ``UserFeedbackQuerySet.visible_to_user``):
        creator OR ``is_public=True`` OR the user can see the
        commented annotation via ``Annotation.objects.visible_to_user``.

        In this fixture, ``self.user`` owns the corpus and documents,
        so they inherit READ on every annotation attached to them —
        whereas ``self.user_2`` has no grants and only sees
        ``is_public=True`` feedback rows.
        """
        logger.info("----- TEST USER FEEDBACK VISIBILITY -----")

        from opencontractserver.annotations.models import Annotation
        from opencontractserver.feedback.models import UserFeedback

        # Create UserFeedback objects with different visibility settings
        with transaction.atomic():
            # Feedback created by user1, not public
            feedback1 = UserFeedback.objects.create(
                creator=self.user, comment="Feedback 1", is_public=False
            )

            # Feedback created by user2, public
            feedback2 = UserFeedback.objects.create(
                creator=self.user_2, comment="Feedback 2", is_public=True
            )

            # Feedback whose commented annotation lives on user1's
            # document — visible to user1 via inherited annotation
            # visibility, NOT visible to user2 (no doc/corpus grants).
            annotation_on_user1_doc_public = Annotation.objects.create(
                creator=self.superuser,
                document=self.corpus._get_active_documents().first(),
                is_public=True,
            )
            feedback3 = UserFeedback.objects.create(
                creator=self.superuser,
                comment="Feedback 3",
                is_public=False,
                commented_annotation=annotation_on_user1_doc_public,
            )

            # Second feedback on a different annotation on the same
            # user1-owned document. user1 sees both annotations (doc
            # creator); user2 sees neither (no grants).
            annotation_on_user1_doc_private = Annotation.objects.create(
                creator=self.superuser,
                document=self.corpus._get_active_documents().first(),
                is_public=False,
            )
            feedback4 = UserFeedback.objects.create(
                creator=self.superuser,
                comment="Feedback 4",
                is_public=False,
                commented_annotation=annotation_on_user1_doc_private,
            )

        # Test visibility for user1 — owns the corpus and document, so
        # inherits READ on every annotation attached. The annotation's
        # ``is_public`` flag is no longer the deciding factor; ownership
        # of the parent doc/corpus is.
        visible_feedback_user1 = UserFeedback.objects.visible_to_user(self.user)
        self.assertIn(feedback1, visible_feedback_user1)
        self.assertIn(feedback2, visible_feedback_user1)
        self.assertIn(feedback3, visible_feedback_user1)
        self.assertIn(feedback4, visible_feedback_user1)
        logger.info(f"User1 can see {visible_feedback_user1.count()} feedback items")

        # Test visibility for user2 — no doc/corpus grants, so cannot
        # see either annotation. Only ``is_public=True`` feedback is
        # visible.
        visible_feedback_user2 = UserFeedback.objects.visible_to_user(self.user_2)
        self.assertNotIn(feedback1, visible_feedback_user2)
        self.assertIn(feedback2, visible_feedback_user2)
        self.assertNotIn(feedback3, visible_feedback_user2)
        self.assertNotIn(feedback4, visible_feedback_user2)
        logger.info(f"User2 can see {visible_feedback_user2.count()} feedback items")

        # Test visibility for superuser
        visible_feedback_superuser = UserFeedback.objects.visible_to_user(
            self.superuser
        )
        self.assertIn(feedback1, visible_feedback_superuser)
        self.assertIn(feedback2, visible_feedback_superuser)
        self.assertIn(feedback3, visible_feedback_superuser)
        self.assertIn(feedback4, visible_feedback_superuser)
        logger.info(
            f"Superuser can see {visible_feedback_superuser.count()} feedback items"
        )

        # Test that the filtered querysets are different for different users
        self.assertNotEqual(set(visible_feedback_user1), set(visible_feedback_user2))

        # Test performance
        import time

        # Measure time for the efficient filtering using 'visible_to_user' method
        start_time = time.time()
        UserFeedback.objects.visible_to_user(self.user)
        end_time = time.time()

        logger.info(
            f"Time taken for efficient filtering: {end_time - start_time} seconds"
        )

        # Compare with a naive approach matching the new model: a row
        # is visible when the user created it OR it's public OR the
        # user can see the commented annotation. Use
        # ``Annotation.objects.visible_to_user`` for the annotation
        # gate to exercise the same predicate the queryset uses.
        visible_annotation_pks = set(
            Annotation.objects.visible_to_user(self.user).values_list("pk", flat=True)
        )
        start_time = time.time()
        all_feedback = UserFeedback.objects.all()
        naive_filtered = [
            feedback
            for feedback in all_feedback
            if feedback.creator == self.user
            or feedback.is_public
            or (
                feedback.commented_annotation_id is not None
                and feedback.commented_annotation_id in visible_annotation_pks
            )
        ]
        end_time = time.time()

        logger.info(f"Time taken for naive filtering: {end_time - start_time} seconds")

        # Assert that both methods return the same results
        self.assertEqual(set(visible_feedback_user1), set(naive_filtered))

    def test_annotation_permission_types(self):
        """
        Test all annotation permission types including CREATE, CRUD, ALL, and unsupported types.
        This ensures full coverage of the annotation-specific permission checking logic.
        """
        logger.info("----- TEST ANNOTATION PERMISSION TYPES -----")

        # Get an annotation from the corpus
        annotation = Annotation.objects.filter(corpus=self.corpus).first()
        self.assertIsNotNone(annotation)

        # Give user full permissions on corpus and documents
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])
        for doc_id in self.doc_ids:
            doc = Document.objects.get(id=doc_id)
            set_permissions_for_obj_to_user(self.user, doc, [PermissionTypes.ALL])

        # Test CREATE permission
        logger.info("Testing CREATE permission for annotation")
        has_create = annotation.user_can(self.user, PermissionTypes.CREATE)
        self.assertTrue(has_create)

        # Test CRUD permission (requires all 4 base permissions)
        logger.info("Testing CRUD permission for annotation")
        has_crud = annotation.user_can(self.user, PermissionTypes.CRUD)
        self.assertTrue(has_crud)

        # Test ALL permission (includes COMMENT)
        logger.info("Testing ALL permission for annotation")
        has_all = annotation.user_can(self.user, PermissionTypes.ALL)
        self.assertTrue(has_all)

        # Test unsupported permissions (PUBLISH and PERMISSION should return False for annotations)
        logger.info("Testing PUBLISH permission (should be False for annotations)")
        has_publish = annotation.user_can(self.user, PermissionTypes.PUBLISH)
        self.assertFalse(has_publish)

        logger.info("Testing PERMISSION permission (should be False for annotations)")
        has_permission = annotation.user_can(self.user, PermissionTypes.PERMISSION)
        self.assertFalse(has_permission)

        # Test with user_2 who has no permissions - all should be False
        logger.info("Testing permissions for user without access")
        self.assertFalse(annotation.user_can(self.user_2, PermissionTypes.CREATE))
        self.assertFalse(annotation.user_can(self.user_2, PermissionTypes.CRUD))
        self.assertFalse(annotation.user_can(self.user_2, PermissionTypes.ALL))


class SetPermissionsIsNewTests(TestCase):
    """Tests for the ``is_new=True`` fast path on ``set_permissions_for_obj_to_user``.

    Freshly-created objects have no prior guardian permissions to clear,
    so the upfront ``remove_perm`` sweep (7 DB ops per call) is dead
    work. ``is_new=True`` lets ingest-style call sites skip it. The
    default behaviour (full replace) must remain unchanged for
    non-creation paths like sharing flows or permission updates.
    """

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="is_new_test_user", password="pw")

    def test_is_new_skips_remove_perm_calls(self):
        """When called with ``is_new=True`` on a fresh object, the function
        must NOT issue any ``remove_perm`` calls.
        """
        from unittest.mock import patch

        new_corpus = Corpus.objects.create(title="brand new", creator=self.user)

        with patch("opencontractserver.utils.permissioning.remove_perm") as mock_remove:
            set_permissions_for_obj_to_user(
                self.user, new_corpus, [PermissionTypes.ALL], is_new=True
            )

        self.assertEqual(
            mock_remove.call_count,
            0,
            "is_new=True must skip the remove_perm sweep entirely",
        )

    def test_is_new_still_grants_requested_perms(self):
        """``is_new=True`` must grant the requested perms identically to
        the default path — only the upfront removal is skipped.
        """
        new_corpus = Corpus.objects.create(title="brand new 2", creator=self.user)
        set_permissions_for_obj_to_user(
            self.user, new_corpus, [PermissionTypes.ALL], is_new=True
        )

        for perm in [
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.PERMISSION,
        ]:
            self.assertTrue(
                new_corpus.user_can(self.user, perm),
                f"User must have {perm} after is_new grant",
            )

    def test_default_path_still_removes_existing_perms(self):
        """Without ``is_new``, the function must continue to do the full
        replace — clearing prior perms before assigning new ones.

        Load-bearing semantic for sharing flows where a user is being
        downgraded from CRUD to READ-only: old UPDATE/DELETE perms
        must be removed.

        Uses a non-creator ``shared_user`` because the
        ``user_can`` method routes through
        ``Manager.user_can``, which applies the creator short-circuit —
        if we tested the corpus creator, UPDATE/DELETE would remain
        True even after explicit guardian perms are cleared, masking
        the behaviour this test pins (the actual guardian clearance).
        """
        shared_user = User.objects.create_user(
            username="downgrade_test_user", password="pw"
        )
        existing_corpus = Corpus.objects.create(
            title="will be downgraded", creator=self.user
        )
        # Grant ALL first.
        set_permissions_for_obj_to_user(
            shared_user, existing_corpus, [PermissionTypes.ALL]
        )
        self.assertTrue(existing_corpus.user_can(shared_user, PermissionTypes.UPDATE))

        # Downgrade to READ-only via the default (replace) path.
        set_permissions_for_obj_to_user(
            shared_user, existing_corpus, [PermissionTypes.READ]
        )

        self.assertTrue(existing_corpus.user_can(shared_user, PermissionTypes.READ))
        self.assertFalse(
            existing_corpus.user_can(shared_user, PermissionTypes.UPDATE),
            "Default path must clear UPDATE when downgrading to READ-only",
        )
        self.assertFalse(existing_corpus.user_can(shared_user, PermissionTypes.DELETE))

    def test_is_new_resolves_int_user_id(self):
        """``is_new`` must still accept an int user_id (for symmetry with
        the default call signature used by ``import_annotations``).
        """
        new_corpus = Corpus.objects.create(title="int id test", creator=self.user)
        set_permissions_for_obj_to_user(
            self.user.id, new_corpus, [PermissionTypes.ALL], is_new=True
        )
        self.assertTrue(new_corpus.user_can(self.user, PermissionTypes.READ))
