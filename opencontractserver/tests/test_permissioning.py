import logging
import pathlib
from random import randrange

from django.contrib.auth import get_user_model
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
from opencontractserver.documents.signals import process_doc_on_create_atomic
from opencontractserver.tasks.permissioning_tasks import (
    make_analysis_public_task,
    make_corpus_public_task,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_users_permissions_for_obj,
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class PermissioningTestCase(TestCase):
    """
    Tests that permissioning system works and those who should be able to see things, can, and those
    who whould not, cannot. TODO - improve the granularity of test cases.
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
            dispatch_uid="Signal.disconnect.install_gremlin_on_creation",
        )

        Signal.disconnect(
            post_save,
            receiver=process_doc_on_create_atomic,
            sender=Document,
            dispatch_uid="Signal.disconnect.process_doc_on_create_atomic",
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
            # with SAMPLE_PDF_FILE_ONE_PATH.open("rb") as test_pdf:
            #     pdf_contents = ContentFile(test_pdf.read())

            with transaction.atomic():
                document = Document.objects.create(
                    title=f"TestDoc{index}",
                    description="Manually created",
                    creator=self.user,
                )
                logger.info(f"Created document with id: {document.id}")

                # document.pdf_file.save("dummy_file.pdf", pdf_contents)
                # logger.info(f"Saved document file for id: {document.id}")

                set_permissions_for_obj_to_user(
                    self.user, document, [PermissionTypes.READ]
                )
                logger.info(f"Set permissions for document with id: {document.id}")

            self.doc_ids.append(document.id)
            logger.info(f"Finished creating document with id: {document.id}")

        # Link docs to corpus
        with transaction.atomic():
            self.corpus.documents.add(*self.doc_ids)

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

        # User one created the corpus... so it can see the corpus
        self.assertEqual(user_one_corpus_response["data"]["corpuses"]["totalCount"], 1)

        # User one should have PermissionType.READ for corpus
        self.assertTrue(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user,
                permission=PermissionTypes.READ,
                include_group_permissions=True,
            )
        )
        # User twp should NOT have PermissionType.READ for corpus
        self.assertFalse(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user_2,
                permission=PermissionTypes.READ,
                include_group_permissions=True,
            )
        )

        # User one should have PermissionType.UPDATE for corpus
        self.assertTrue(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user,
                permission=PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )
        # User twp should NOT have PermissionType.UPDATE for corpus
        self.assertFalse(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user_2,
                permission=PermissionTypes.UPDATE,
                include_group_permissions=True,
            )
        )

        # User one should have PermissionType.DELETE for corpus
        self.assertTrue(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user,
                permission=PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )
        # User two should NOT have PermissionType.DELETE for corpus
        self.assertFalse(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user_2,
                permission=PermissionTypes.DELETE,
                include_group_permissions=True,
            )
        )

        # User one should have PermissionType.PERMISSION for corpus
        self.assertTrue(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user,
                permission=PermissionTypes.PERMISSION,
                include_group_permissions=True,
            )
        )
        # User two should NOT have PermissionType.PERMISSION for corpus
        self.assertFalse(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user_2,
                permission=PermissionTypes.PERMISSION,
                include_group_permissions=True,
            )
        )

        # User one should have PermissionType.PUBLISH for corpus
        self.assertTrue(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user,
                permission=PermissionTypes.PUBLISH,
                include_group_permissions=True,
            )
        )
        # User twp should NOT have PermissionType.PUBLISH for corpus
        self.assertFalse(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user_2,
                permission=PermissionTypes.PUBLISH,
                include_group_permissions=True,
            )
        )

        # User one should have PermissionType.ALL for corpus
        self.assertTrue(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user,
                permission=PermissionTypes.ALL,
                include_group_permissions=True,
            )
        )

        # User two should NOT have PermissionType.ALL for corpus
        self.assertFalse(
            user_has_permission_for_obj(
                instance=self.corpus,
                user_val=self.user_2,
                permission=PermissionTypes.ALL,
                include_group_permissions=True,
            )
        )
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
            },
        )
        for doc in user_one_corpus_response["data"]["corpuses"]["edges"][0]["node"][
            "documents"
        ]["edges"]:
            self.assertEqual(doc["node"]["myPermissions"], ["read_document"])

        user_two_corpus_response = self.graphene_client_2.execute(request_corpuses)
        logger.info(f"user_two_corpus_response: {user_two_corpus_response}")

        # User two did not create the corpus and it's not public, so user one sees nothing
        self.assertEqual(user_two_corpus_response["data"]["corpuses"]["totalCount"], 0)

    def __test_make_corpus_public_mutation(self):

        logger.info(
            "----- TEST MAKE CORPUS PUBLIC MUTATION ----------------------------------------------------------"
        )

        make_public_mutation_request = """
            mutation ($corpusId: String!) {
              makeCorpusPublic(corpusId: $corpusId) {
                ok
                message
              }
            }
        """
        variables = {"corpusId": self.global_corpus_id}

        # This should fail (only superuser can do this)
        prohibited_graphql_response = self.graphene_client.execute(
            make_public_mutation_request,
            variable_values=variables,
        )
        logger.info(f"Improper permission response: {prohibited_graphql_response}")
        self.assertEqual(prohibited_graphql_response["data"]["makeCorpusPublic"], None)
        self.assertEqual(
            prohibited_graphql_response["errors"][0]["message"],
            "You do not have permission to " "perform this action",
        )

        # THIS should work - request make public with superuser
        permissioned_graphql_response = self.elevated_graphene_client.execute(
            make_public_mutation_request,
            variable_values=variables,
        )

        # Now anonymous requests should work to request the corpus.
        logger.info(f"Make public call return value: {permissioned_graphql_response}")

        self.assertEqual(
            permissioned_graphql_response["data"]["makeCorpusPublic"]["ok"], True
        )
        self.assertEqual(
            permissioned_graphql_response["data"]["makeCorpusPublic"]["message"],
            "Starting an OpenContracts worker to make your corpus public!",
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
        self.assertEqual(prohibited_graphql_response["data"]["deleteCorpus"], None)
        self.assertEqual(
            prohibited_graphql_response["errors"][0]["message"],
            "User does not have delete permission for this object.",
        )

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
            user_val=self.user_2, instance=self.corpus, include_group_permissions=True
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

            # Feedback with public annotation
            public_annotation = Annotation.objects.create(
                creator=self.superuser,
                document=self.corpus.documents.first(),
                is_public=True,
            )
            feedback3 = UserFeedback.objects.create(
                creator=self.superuser,
                comment="Feedback 3",
                is_public=False,
                commented_annotation=public_annotation,
            )

            # Feedback with private annotation
            private_annotation = Annotation.objects.create(
                creator=self.superuser,
                document=self.corpus.documents.first(),
                is_public=False,
            )
            feedback4 = UserFeedback.objects.create(
                creator=self.superuser,
                comment="Feedback 4",
                is_public=False,
                commented_annotation=private_annotation,
            )

        # Test visibility for user1
        visible_feedback_user1 = UserFeedback.objects.visible_to_user(self.user)
        self.assertIn(feedback1, visible_feedback_user1)
        self.assertIn(feedback2, visible_feedback_user1)

        # Before we apply per obj permission... these should not be visible
        self.assertNotIn(feedback3, visible_feedback_user1)
        self.assertNotIn(feedback4, visible_feedback_user1)
        logger.info(
            f"User1 can NOT see {visible_feedback_user1.count()} feedback items"
        )

        # Now apply per-obj permissions
        set_permissions_for_obj_to_user(self.user, feedback3, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.user, feedback4, [PermissionTypes.READ])

        # Refetch queryset
        visible_feedback_user1 = UserFeedback.objects.visible_to_user(self.user)

        # Now feedback3 and feedback4 should be visible
        self.assertIn(feedback3, visible_feedback_user1)
        self.assertIn(feedback4, visible_feedback_user1)
        logger.info(f"User1 CAN see {visible_feedback_user1.count()} feedback items")

        # Test visibility for user2 prior to applying per obj permissions
        visible_feedback_user2 = UserFeedback.objects.visible_to_user(self.user_2)
        self.assertNotIn(feedback1, visible_feedback_user2)
        self.assertIn(feedback2, visible_feedback_user2)
        self.assertNotIn(feedback3, visible_feedback_user2)
        self.assertNotIn(feedback4, visible_feedback_user2)
        logger.info(f"User2 can see {visible_feedback_user2.count()} feedback items")

        # Apply per obj permissions to user 2
        set_permissions_for_obj_to_user(self.user_2, feedback3, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(self.user_2, feedback4, [PermissionTypes.READ])

        # Refetch queryset
        visible_feedback_user2 = UserFeedback.objects.visible_to_user(self.user_2)

        # Test visibility for user2
        visible_feedback_user2 = UserFeedback.objects.visible_to_user(self.user_2)
        self.assertNotIn(feedback1, visible_feedback_user2)
        self.assertIn(feedback2, visible_feedback_user2)
        self.assertIn(feedback3, visible_feedback_user2)
        self.assertIn(feedback4, visible_feedback_user2)
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
