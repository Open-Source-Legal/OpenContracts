"""
Tests for security hardening changes from the auth/permissioning audit.

Covers:
- AnalysisCallbackView: DoS prevention, timing-safe token comparison, unified error messages
- home_redirect: open redirect prevention via ALLOWED_HOSTS validation
- DRFDeletion/DRFMutation: visible_to_user() IDOR prevention, user lock inversion fix,
  ValidationError formatting
- Document summary resolvers: corpus permission checks
- Mutation IDOR fixes: CreateColumn, CreateExtract, CreateNote, CreateCorpusAction, etc.
- Conversation/voting/badge mutation IDOR fixes
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from graphene.test import Client
from graphql_relay import to_global_id
from rest_framework.test import APIClient

from config.graphql.schema import schema
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockRequest:
    """Minimal request-like object for graphene test client."""

    def __init__(self, user):
        self.user = user
        self.META = {}


def _gql(client, query, user, variables=None):
    """Shortcut to execute a GraphQL query as a specific user."""
    return client.execute(query, variables=variables, context_value=MockRequest(user))


# ===========================================================================
# 1. AnalysisCallbackView security tests
# ===========================================================================


class TestAnalysisCallbackSecurity(TestCase):
    """Tests for the hardened AnalysisCallbackView."""

    def setUp(self):
        self.user = User.objects.create_user(username="cb_user", password="test")
        self.gremlin = GremlinEngine.objects.create(
            url="http://localhost:8000", creator=self.user
        )
        self.analyzer = Analyzer.objects.create(
            id="test-analyzer",
            description="Test analyzer",
            creator=self.user,
            host_gremlin=self.gremlin,
        )
        self.corpus = Corpus.objects.create(title="CB Corpus", creator=self.user)
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
        )
        self.api_client = APIClient()

    def test_nonexistent_analysis_returns_403(self):
        """Nonexistent analysis_id returns 403 with generic message (no enumeration)."""
        response = self.api_client.post(
            "/analysis/999999/complete",
            data={},
            format="json",
            HTTP_CALLBACK_TOKEN="anything",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["message"], "Invalid analysis_id or callback token."
        )

    def test_missing_token_returns_403(self):
        """Request without CALLBACK_TOKEN header returns 403 with generic message."""
        response = self.api_client.post(
            f"/analysis/{self.analysis.id}/complete",
            data={},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["message"], "Invalid analysis_id or callback token."
        )

    def test_wrong_token_returns_403_without_failing_analysis(self):
        """
        Wrong token returns 403 with generic message AND does NOT mark the
        analysis as FAILED (DoS prevention).
        """
        from opencontractserver.types.enums import JobStatus

        response = self.api_client.post(
            f"/analysis/{self.analysis.id}/complete",
            data={},
            format="json",
            HTTP_CALLBACK_TOKEN="wrong-token",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["message"], "Invalid analysis_id or callback token."
        )

        # Verify the analysis was NOT marked as failed
        self.analysis.refresh_from_db()
        self.assertNotEqual(self.analysis.status, JobStatus.FAILED)

    def test_same_error_for_missing_vs_wrong_token(self):
        """Error messages for missing analysis, missing token, and wrong token are identical."""
        # Missing analysis
        r1 = self.api_client.post(
            "/analysis/999999/complete",
            data={},
            format="json",
            HTTP_CALLBACK_TOKEN="tok",
        )
        # Missing token
        r2 = self.api_client.post(
            f"/analysis/{self.analysis.id}/complete",
            data={},
            format="json",
        )
        # Wrong token
        r3 = self.api_client.post(
            f"/analysis/{self.analysis.id}/complete",
            data={},
            format="json",
            HTTP_CALLBACK_TOKEN="wrong",
        )

        self.assertEqual(r1.data["message"], r2.data["message"])
        self.assertEqual(r2.data["message"], r3.data["message"])
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r2.status_code, r3.status_code)

    def test_correct_token_accepted(self):
        """Issued plaintext token verifies against the stored SHA-256 hash."""
        # Mint a fresh plaintext token; the DB stores only its hash.
        # rotate_callback_token() auto-saves because self.analysis has a pk.
        plaintext = self.analysis.rotate_callback_token()

        response = self.api_client.post(
            f"/analysis/{self.analysis.id}/complete",
            data={},
            format="json",
            HTTP_CALLBACK_TOKEN=plaintext,
        )
        # Should not be 403 (it may be 400 because of invalid JSON body, but not 403)
        self.assertNotEqual(response.status_code, 403)


class TestAnalysisCallbackTokenHelpers(TestCase):
    """Unit tests for ``Analysis.rotate_callback_token`` / ``verify_callback_token``.

    These exercise the model helpers directly (without going through the
    HTTP callback view) to lock in their behaviour on the edges the
    callback view depends on: empty-hash fresh rows, constant-time
    verification, plaintext-not-stored, and rotation invalidating prior
    plaintexts.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="cb_helper_user", password="test")
        gremlin = GremlinEngine.objects.create(
            url="http://localhost:8000", creator=self.user
        )
        analyzer = Analyzer.objects.create(
            id="cb-helper-analyzer",
            description="Helper test analyzer",
            creator=self.user,
            host_gremlin=gremlin,
        )
        corpus = Corpus.objects.create(title="Helper Corpus", creator=self.user)
        self.analysis = Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=corpus,
            creator=self.user,
        )

    def test_fresh_analysis_has_empty_hash(self):
        """Newly-created Analysis has an empty callback_token_hash."""
        self.assertEqual(self.analysis.callback_token_hash, "")

    def test_verify_empty_hash_always_false(self):
        """Empty stored hash rejects every candidate, including the empty string."""
        self.assertFalse(self.analysis.verify_callback_token(None))
        self.assertFalse(self.analysis.verify_callback_token(""))
        self.assertFalse(self.analysis.verify_callback_token("anything"))

    def test_rotate_returns_plaintext_and_stores_hash(self):
        """rotate_callback_token returns plaintext; DB stores only the SHA-256 hash."""
        import hashlib

        plaintext = self.analysis.rotate_callback_token()
        self.assertIsInstance(plaintext, str)
        self.assertGreaterEqual(
            len(plaintext), 32
        )  # secrets.token_urlsafe(32) yields ~43 chars
        # Hash matches; plaintext is not in the model's hash field.
        expected_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        self.assertEqual(self.analysis.callback_token_hash, expected_hash)
        self.assertNotIn(plaintext, self.analysis.callback_token_hash)

    def test_verify_accepts_correct_plaintext_only(self):
        """verify_callback_token accepts only the issued plaintext."""
        plaintext = self.analysis.rotate_callback_token()
        self.assertTrue(self.analysis.verify_callback_token(plaintext))
        self.assertFalse(self.analysis.verify_callback_token(plaintext + "x"))
        self.assertFalse(self.analysis.verify_callback_token("not-the-token"))

    def test_verify_handles_none_and_empty_candidate(self):
        """None/empty candidate is rejected even when a hash is set."""
        self.analysis.rotate_callback_token()
        self.assertFalse(self.analysis.verify_callback_token(None))
        self.assertFalse(self.analysis.verify_callback_token(""))

    def test_rotation_invalidates_prior_plaintext(self):
        """Re-rotating the token invalidates the previously-issued plaintext."""
        first = self.analysis.rotate_callback_token()
        self.assertTrue(self.analysis.verify_callback_token(first))
        second = self.analysis.rotate_callback_token()
        # New plaintext verifies; old one is rejected.
        self.assertNotEqual(first, second)
        self.assertTrue(self.analysis.verify_callback_token(second))
        self.assertFalse(self.analysis.verify_callback_token(first))

    def test_rotate_autopersists_for_saved_instance(self):
        """Calling rotate on an instance with a pk persists the hash so a
        subsequent ``refresh_from_db`` sees the new value without an
        explicit ``save`` call by the caller."""
        plaintext = self.analysis.rotate_callback_token()
        # Read back from DB — auto-save means the new hash is durable.
        self.analysis.refresh_from_db()
        self.assertTrue(self.analysis.verify_callback_token(plaintext))

    def test_rotate_does_not_save_unsaved_instance(self):
        """For an unsaved instance (no pk yet), rotate sets the hash in
        memory but does NOT auto-save — the caller still owns the first
        save. This avoids a surprise ``IntegrityError`` from auto-saving
        an Analysis missing required FKs."""
        unsaved = Analysis(analyzer=self.analysis.analyzer, creator=self.user)
        self.assertIsNone(unsaved.pk)
        plaintext = unsaved.rotate_callback_token()
        # In-memory hash is set; pk is still None (nothing was saved).
        self.assertIsNone(unsaved.pk)
        self.assertTrue(unsaved.verify_callback_token(plaintext))


# ===========================================================================
# 2. home_redirect open redirect prevention tests
# ===========================================================================


class TestHomeRedirectSecurity(TestCase):
    """Tests for the open redirect prevention in home_redirect."""

    @override_settings(ALLOWED_HOSTS=["example.com"])
    def test_valid_host_redirects_to_port_3000(self):
        """Valid host in ALLOWED_HOSTS redirects to host:3000."""
        response = self.client.get("/", HTTP_HOST="example.com")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://example.com:3000")

    @override_settings(ALLOWED_HOSTS=["example.com"])
    def test_invalid_host_rejected(self):
        """Invalid host NOT in ALLOWED_HOSTS is rejected by Django middleware (400)."""
        # Django's CommonMiddleware validates the Host header BEFORE our view
        # runs, returning a 400 DisallowedHost response. This is the first
        # line of defense; our view adds a second layer for edge cases.
        response = self.client.get("/", HTTP_HOST="evil.com", SERVER_NAME="evil.com")
        self.assertEqual(response.status_code, 400)

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_wildcard_allows_any_host(self):
        """Wildcard '*' in ALLOWED_HOSTS allows any host."""
        response = self.client.get("/", HTTP_HOST="anything.com")
        self.assertEqual(response.status_code, 302)
        self.assertIn("anything.com:3000", response.url)

    @override_settings(ALLOWED_HOSTS=[".example.com"])
    def test_suffix_match_allows_subdomain(self):
        """Dot-prefix pattern '.example.com' allows subdomains."""
        response = self.client.get("/", HTTP_HOST="sub.example.com")
        self.assertEqual(response.status_code, 302)
        self.assertIn("sub.example.com:3000", response.url)

    @override_settings(ALLOWED_HOSTS=[".example.com"])
    def test_suffix_match_allows_bare_domain(self):
        """Dot-prefix pattern '.example.com' allows the bare domain too."""
        response = self.client.get("/", HTTP_HOST="example.com")
        self.assertEqual(response.status_code, 302)
        self.assertIn("example.com:3000", response.url)

    @override_settings(ALLOWED_HOSTS=[".example.com"])
    def test_suffix_match_rejects_non_matching_domain(self):
        """Dot-prefix pattern '.example.com' rejects non-matching domains (400)."""
        # Django's CommonMiddleware rejects before our view runs.
        response = self.client.get("/", HTTP_HOST="evil.com", SERVER_NAME="evil.com")
        self.assertEqual(response.status_code, 400)


# ===========================================================================
# 3. GraphQL mutation IDOR prevention tests
# ===========================================================================


class TestMutationIDORPrevention(TestCase):
    """
    Tests that mutations using visible_to_user() properly prevent
    unauthorized users from accessing objects by ID.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="idor_owner", password="test")
        self.outsider = User.objects.create_user(
            username="idor_outsider", password="test"
        )

        # Create private corpus owned by 'owner' -- outsider has no permissions
        self.corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Create a document owned by 'owner'
        self.document = Document.objects.create(
            title="Private Doc", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        self.gql_client = Client(schema)

    def test_create_note_on_inaccessible_document(self):
        """Outsider cannot create a note on a document they cannot see."""
        mutation = """
            mutation CreateNote(
                $documentId: ID!,
                $title: String!,
                $content: String!,
                $corpusId: ID
            ) {
                createNote(
                    documentId: $documentId,
                    title: $title,
                    content: $content,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                }
            }
        """
        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "title": "Sneaky Note",
            "content": "Should not be created",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["createNote"]
        self.assertFalse(data["ok"])
        # Should get a generic "not found" (IDOR-safe, no existence leakage)
        self.assertIn("not found", data["message"].lower())

    def test_create_note_with_inaccessible_corpus(self):
        """Outsider cannot attach a note to a corpus they cannot see."""
        # Create a doc the outsider CAN see
        public_doc = Document.objects.create(
            title="Public Doc", creator=self.owner, is_public=True
        )

        mutation = """
            mutation CreateNote(
                $documentId: ID!,
                $title: String!,
                $content: String!,
                $corpusId: ID
            ) {
                createNote(
                    documentId: $documentId,
                    title: $title,
                    content: $content,
                    corpusId: $corpusId
                ) {
                    ok
                    message
                }
            }
        """
        variables = {
            "documentId": to_global_id("DocumentType", public_doc.id),
            "title": "Sneaky Note",
            "content": "Should not be created",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["createNote"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_owner_can_create_note(self):
        """Owner CAN create a note on their own document."""
        mutation = """
            mutation CreateNote(
                $documentId: ID!,
                $title: String!,
                $content: String!
            ) {
                createNote(
                    documentId: $documentId,
                    title: $title,
                    content: $content
                ) {
                    ok
                    message
                }
            }
        """
        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "title": "My Note",
            "content": "This should work",
        }

        result = _gql(self.gql_client, mutation, self.owner, variables)
        data = result["data"]["createNote"]
        self.assertTrue(data["ok"])


# ===========================================================================
# 3b. AddRelationship document-visibility IDOR test
# ===========================================================================


class TestAddRelationshipDocumentIDOR(TestCase):
    """
    Pin the document-visibility check on ``AddRelationship``.

    A caller with CREATE on a corpus they own must not be able to bind a
    new relationship to a `document_id` belonging to a corpus they cannot
    see. Without the explicit check, the IDOR surface would expose
    document existence by allowing relationship rows to land on arbitrary
    document_ids.
    """

    def setUp(self):
        from opencontractserver.annotations.models import (
            Annotation,
            AnnotationLabel,
        )

        self.attacker = User.objects.create_user(
            username="rel_attacker", password="test"
        )
        self.victim = User.objects.create_user(username="rel_victim", password="test")

        # Attacker's own corpus (CREATE allowed) and a single document/
        # annotation pair to act as legitimate relationship endpoints.
        self.attacker_corpus = Corpus.objects.create(
            title="Attacker Corpus",
            creator=self.attacker,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.attacker, self.attacker_corpus, [PermissionTypes.CRUD]
        )

        self.attacker_doc = Document.objects.create(
            title="Attacker Doc",
            creator=self.attacker,
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.attacker, self.attacker_doc, [PermissionTypes.CRUD]
        )

        # Victim's private document — attacker has zero visibility on it.
        self.victim_doc = Document.objects.create(
            title="Victim Private Doc",
            creator=self.victim,
            is_public=False,
        )

        self.label = AnnotationLabel.objects.create(
            text="rel_label", creator=self.attacker
        )

        self.source_annot = Annotation.objects.create(
            document=self.attacker_doc,
            corpus=self.attacker_corpus,
            annotation_label=self.label,
            creator=self.attacker,
            raw_text="src",
        )
        self.target_annot = Annotation.objects.create(
            document=self.attacker_doc,
            corpus=self.attacker_corpus,
            annotation_label=self.label,
            creator=self.attacker,
            raw_text="tgt",
        )

        self.mutation = """
            mutation AddRel(
                $sourceIds: [String]!,
                $targetIds: [String]!,
                $relationshipLabelId: String!,
                $corpusId: String!,
                $documentId: String!
            ) {
                addRelationship(
                    sourceIds: $sourceIds,
                    targetIds: $targetIds,
                    relationshipLabelId: $relationshipLabelId,
                    corpusId: $corpusId,
                    documentId: $documentId
                ) {
                    ok
                    message
                }
            }
        """
        self.gql_client = Client(schema)

    def _base_variables(self, document_global_id: str) -> dict:
        return {
            "sourceIds": [to_global_id("AnnotationType", self.source_annot.id)],
            "targetIds": [to_global_id("AnnotationType", self.target_annot.id)],
            "relationshipLabelId": to_global_id("AnnotationLabelType", self.label.id),
            "corpusId": to_global_id("CorpusType", self.attacker_corpus.id),
            "documentId": document_global_id,
        }

    def test_blocks_relationship_with_inaccessible_document(self):
        """Outsider with CREATE on a corpus cannot land a relationship on a
        document they cannot see."""
        from opencontractserver.annotations.models import Relationship

        variables = self._base_variables(
            to_global_id("DocumentType", self.victim_doc.id)
        )
        result = _gql(self.gql_client, self.mutation, self.attacker, variables)
        data = result["data"]["addRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())
        self.assertFalse(
            Relationship.objects.filter(document_id=self.victim_doc.id).exists()
        )

    def test_allows_relationship_on_visible_document(self):
        """Sanity: when document_id is visible to the caller, the mutation
        succeeds. Pins that the new visibility check does not also break
        the happy path."""
        variables = self._base_variables(
            to_global_id("DocumentType", self.attacker_doc.id)
        )
        result = _gql(self.gql_client, self.mutation, self.attacker, variables)
        data = result["data"]["addRelationship"]
        self.assertTrue(data["ok"], f"expected ok, got message={data.get('message')!r}")

    def test_garbage_global_ids_yield_not_found_message(self):
        """Unparseable global IDs collapse into the same IDOR-safe message
        rather than echoing a parse error to the caller.

        A b64-decodable but non-numeric pk now fails inside the outer
        try/except via the ``int()`` cast, returning the unified
        not-found response shape.
        """
        # b64("BogusType:not-an-int") = "Qm9ndXNUeXBlOm5vdC1hbi1pbnQ="
        bad_gid = "Qm9ndXNUeXBlOm5vdC1hbi1pbnQ="
        variables = {
            "sourceIds": [bad_gid],
            "targetIds": [to_global_id("AnnotationType", self.target_annot.id)],
            "relationshipLabelId": to_global_id("AnnotationLabelType", self.label.id),
            "corpusId": to_global_id("CorpusType", self.attacker_corpus.id),
            "documentId": to_global_id("DocumentType", self.attacker_doc.id),
        }
        result = _gql(self.gql_client, self.mutation, self.attacker, variables)
        data = result["data"]["addRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_unknown_source_annotation_id_yields_not_found(self):
        """A valid-format but unknown source annotation id collapses into
        the unified not-found message — count comparison catches it."""
        variables = {
            "sourceIds": [to_global_id("AnnotationType", 999_999)],
            "targetIds": [to_global_id("AnnotationType", self.target_annot.id)],
            "relationshipLabelId": to_global_id("AnnotationLabelType", self.label.id),
            "corpusId": to_global_id("CorpusType", self.attacker_corpus.id),
            "documentId": to_global_id("DocumentType", self.attacker_doc.id),
        }
        result = _gql(self.gql_client, self.mutation, self.attacker, variables)
        data = result["data"]["addRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_inaccessible_relationship_label_yields_not_found(self):
        """A relationship_label owned by another user must collapse into the
        same not-found message — closes the residual oracle where an
        attacker could probe private AnnotationLabel IDs."""
        from opencontractserver.annotations.models import (
            AnnotationLabel,
            Relationship,
        )

        # A label owned by the victim, with no permission shared to attacker.
        victim_label = AnnotationLabel.objects.create(
            text="victim_label",
            creator=self.victim,
            is_public=False,
        )
        variables = {
            "sourceIds": [to_global_id("AnnotationType", self.source_annot.id)],
            "targetIds": [to_global_id("AnnotationType", self.target_annot.id)],
            "relationshipLabelId": to_global_id("AnnotationLabelType", victim_label.id),
            "corpusId": to_global_id("CorpusType", self.attacker_corpus.id),
            "documentId": to_global_id("DocumentType", self.attacker_doc.id),
        }
        result = _gql(self.gql_client, self.mutation, self.attacker, variables)
        data = result["data"]["addRelationship"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())
        # And no Relationship row got created.
        self.assertFalse(
            Relationship.objects.filter(relationship_label_id=victim_label.id).exists()
        )


# ===========================================================================
# 4. Conversation mutation IDOR tests
# ===========================================================================


class TestConversationMutationIDOR(TestCase):
    """Tests that conversation mutations use visible_to_user() for IDOR prevention."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="conv_idor_owner", password="test"
        )
        self.outsider = User.objects.create_user(
            username="conv_idor_outsider", password="test"
        )

        self.corpus = Corpus.objects.create(
            title="Conv Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        self.document = Document.objects.create(
            title="Conv Doc", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        self.gql_client = Client(schema)

    def test_create_thread_on_inaccessible_corpus(self):
        """Outsider cannot create a thread in a corpus they cannot see."""
        mutation = """
            mutation CreateThread($corpusId: String!, $title: String!, $initialMessage: String!) {
                createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                }
            }
        """
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "title": "Sneaky Thread",
            "initialMessage": "Hello",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["createThread"]
        self.assertFalse(data["ok"])
        # IDOR-safe: same error whether missing or no permission
        msg = data["message"].lower()
        self.assertTrue(
            "not found" in msg or "permission" in msg or "not have" in msg,
            f"Unexpected error message: {data['message']}",
        )

    def test_create_thread_on_inaccessible_document(self):
        """Outsider cannot create a thread on a document they cannot see."""
        mutation = """
            mutation CreateThread(
                $documentId: String!,
                $title: String!,
                $initialMessage: String!
            ) {
                createThread(
                    documentId: $documentId,
                    title: $title,
                    initialMessage: $initialMessage
                ) {
                    ok
                    message
                }
            }
        """
        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "title": "Sneaky Thread",
            "initialMessage": "Hello",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["createThread"]
        self.assertFalse(data["ok"])
        msg = data["message"].lower()
        self.assertTrue(
            "not found" in msg or "permission" in msg or "not have" in msg,
            f"Unexpected error message: {data['message']}",
        )

    def test_owner_can_create_thread(self):
        """Owner CAN create a thread in their own corpus."""
        mutation = """
            mutation CreateThread($corpusId: String!, $title: String!, $initialMessage: String!) {
                createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                }
            }
        """
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "title": "My Thread",
            "initialMessage": "Hello world",
        }

        result = _gql(self.gql_client, mutation, self.owner, variables)
        data = result["data"]["createThread"]
        self.assertTrue(data["ok"])


# ===========================================================================
# 5. Voting mutation IDOR tests
# ===========================================================================


class TestVotingMutationIDOR(TestCase):
    """Tests that voting mutations use visible_to_user() for IDOR prevention."""

    def setUp(self):
        from opencontractserver.conversations.models import ChatMessage, Conversation

        self.owner = User.objects.create_user(
            username="vote_idor_owner", password="test"
        )
        self.outsider = User.objects.create_user(
            username="vote_idor_outsider", password="test"
        )

        self.corpus = Corpus.objects.create(
            title="Vote Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        self.conversation = Conversation.objects.create(
            title="Vote Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.conversation, [PermissionTypes.CRUD]
        )

        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Test message",
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.message, [PermissionTypes.CRUD]
        )

        self.gql_client = Client(schema)

    def test_vote_on_inaccessible_message(self):
        """Outsider cannot vote on a message in a conversation they cannot see."""
        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                }
            }
        """
        variables = {
            "messageId": to_global_id("MessageType", self.message.id),
            "voteType": "upvote",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["voteMessage"]
        self.assertFalse(data["ok"])
        msg = data["message"].lower()
        self.assertTrue("not found" in msg or "permission" in msg)

    def test_remove_vote_on_inaccessible_message(self):
        """Outsider cannot remove a vote on a message they cannot see."""
        mutation = """
            mutation RemoveVote($messageId: String!) {
                removeVote(messageId: $messageId) {
                    ok
                    message
                }
            }
        """
        variables = {
            "messageId": to_global_id("MessageType", self.message.id),
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["removeVote"]
        self.assertFalse(data["ok"])
        msg = data["message"].lower()
        self.assertTrue("not found" in msg or "permission" in msg)


# ===========================================================================
# 6. Corpus folder mutation IDOR tests
# ===========================================================================


class TestCorpusFolderMutationIDOR(TestCase):
    """Tests that folder mutations use visible_to_user() for corpus/folder lookups."""

    def setUp(self):
        from opencontractserver.corpuses.models import CorpusFolder

        self.owner = User.objects.create_user(
            username="folder_idor_owner", password="test"
        )
        self.outsider = User.objects.create_user(
            username="folder_idor_outsider", password="test"
        )

        self.corpus = Corpus.objects.create(
            title="Folder Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        self.folder = CorpusFolder.objects.create(
            name="Test Folder", corpus=self.corpus, creator=self.owner
        )

        self.gql_client = Client(schema)

    def test_create_folder_in_inaccessible_corpus(self):
        """Outsider cannot create a folder in a corpus they cannot see."""
        mutation = """
            mutation CreateFolder($corpusId: ID!, $name: String!) {
                createCorpusFolder(corpusId: $corpusId, name: $name) {
                    ok
                    message
                }
            }
        """
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "Sneaky Folder",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["createCorpusFolder"]
        self.assertFalse(data["ok"])
        msg = data["message"].lower()
        self.assertTrue("not found" in msg or "permission" in msg)

    def test_update_folder_in_inaccessible_corpus(self):
        """Outsider cannot update a folder in a corpus they cannot see."""
        mutation = """
            mutation UpdateFolder($folderId: ID!, $name: String) {
                updateCorpusFolder(folderId: $folderId, name: $name) {
                    ok
                    message
                }
            }
        """
        variables = {
            "folderId": to_global_id("CorpusFolderType", self.folder.id),
            "name": "Renamed",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["updateCorpusFolder"]
        self.assertFalse(data["ok"])
        msg = data["message"].lower()
        self.assertTrue("not found" in msg or "permission" in msg)

    def test_delete_folder_in_inaccessible_corpus(self):
        """Outsider cannot delete a folder in a corpus they cannot see."""
        mutation = """
            mutation DeleteFolder($folderId: ID!) {
                deleteCorpusFolder(folderId: $folderId) {
                    ok
                    message
                }
            }
        """
        variables = {
            "folderId": to_global_id("CorpusFolderType", self.folder.id),
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        data = result["data"]["deleteCorpusFolder"]
        self.assertFalse(data["ok"])
        msg = data["message"].lower()
        self.assertTrue("not found" in msg or "permission" in msg)

    def test_owner_can_create_folder(self):
        """Owner CAN create a folder in their own corpus."""
        mutation = """
            mutation CreateFolder($corpusId: ID!, $name: String!) {
                createCorpusFolder(corpusId: $corpusId, name: $name) {
                    ok
                    message
                }
            }
        """
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "My Folder",
        }

        result = _gql(self.gql_client, mutation, self.owner, variables)
        data = result["data"]["createCorpusFolder"]
        self.assertTrue(data["ok"])


# ===========================================================================
# 7. Document summary resolver corpus permission tests
# ===========================================================================


class TestDocumentSummaryResolverPermissions(TestCase):
    """Tests that document summary resolvers check corpus visibility."""

    def setUp(self):
        self.owner = User.objects.create_user(username="summary_owner", password="test")
        self.outsider = User.objects.create_user(
            username="summary_outsider", password="test"
        )

        # Private corpus
        self.corpus = Corpus.objects.create(
            title="Summary Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # Public document (outsider can see it, but not the corpus)
        self.document = Document.objects.create(
            title="Summary Doc", creator=self.owner, is_public=True
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        self.gql_client = Client(schema)

    def test_outsider_cannot_read_summary_version_for_inaccessible_corpus(self):
        """Outsider gets version=0 for a corpus they cannot see."""
        query = """
            query DocSummaryVersion($id: ID!, $corpusId: ID!) {
                document(id: $id) {
                    currentSummaryVersion(corpusId: $corpusId)
                }
            }
        """
        variables = {
            "id": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = _gql(self.gql_client, query, self.outsider, variables)
        # Should not error, but should return 0 (no access to corpus)
        if result.get("errors"):
            # Some query patterns may raise errors; that's also acceptable
            pass
        else:
            self.assertEqual(result["data"]["document"]["currentSummaryVersion"], 0)

    def test_outsider_cannot_read_summary_content_for_inaccessible_corpus(self):
        """Outsider gets empty string for summary content in inaccessible corpus."""
        query = """
            query DocSummaryContent($id: ID!, $corpusId: ID!) {
                document(id: $id) {
                    summaryContent(corpusId: $corpusId)
                }
            }
        """
        variables = {
            "id": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = _gql(self.gql_client, query, self.outsider, variables)
        if result.get("errors"):
            pass
        else:
            self.assertEqual(result["data"]["document"]["summaryContent"], "")

    def test_owner_can_read_summary_version(self):
        """Owner can read summary version for their own corpus."""
        query = """
            query DocSummaryVersion($id: ID!, $corpusId: ID!) {
                document(id: $id) {
                    currentSummaryVersion(corpusId: $corpusId)
                }
            }
        """
        variables = {
            "id": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = _gql(self.gql_client, query, self.owner, variables)
        # Should succeed (returns 0 because no revisions, but no error)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["document"]["currentSummaryVersion"], 0)


# ===========================================================================
# 8. Extract / Column IDOR tests
# ===========================================================================


class TestExtractColumnIDOR(TestCase):
    """Tests that extract/column mutations use visible_to_user()."""

    def setUp(self):
        from opencontractserver.extracts.models import Fieldset

        self.owner = User.objects.create_user(username="extract_owner", password="test")
        self.outsider = User.objects.create_user(
            username="extract_outsider", password="test"
        )

        self.corpus = Corpus.objects.create(
            title="Extract Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.fieldset, [PermissionTypes.CRUD]
        )

        self.gql_client = Client(schema)

    def test_create_column_with_inaccessible_fieldset(self):
        """Outsider cannot create a column on a fieldset they cannot see."""
        mutation = """
            mutation CreateColumn(
                $fieldsetId: ID!,
                $name: String!,
                $query: String,
                $outputType: String!
            ) {
                createColumn(
                    fieldsetId: $fieldsetId,
                    name: $name,
                    query: $query,
                    outputType: $outputType
                ) {
                    ok
                    message
                }
            }
        """
        variables = {
            "fieldsetId": to_global_id("FieldsetType", self.fieldset.id),
            "name": "Sneaky Column",
            "query": "test query",
            "outputType": "str",
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        # Should fail: outsider can't see the fieldset
        if result.get("errors"):
            # DoesNotExist propagated as error -- acceptable IDOR prevention
            pass
        else:
            data = result["data"]["createColumn"]
            self.assertFalse(data["ok"])

    def test_create_extract_with_inaccessible_corpus(self):
        """Outsider cannot create an extract for a corpus they cannot see."""
        mutation = """
            mutation CreateExtract($name: String!, $corpusId: ID) {
                createExtract(name: $name, corpusId: $corpusId) {
                    ok
                    msg
                }
            }
        """
        variables = {
            "name": "Sneaky Extract",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = _gql(self.gql_client, mutation, self.outsider, variables)
        if result.get("errors"):
            pass
        else:
            data = result["data"]["createExtract"]
            self.assertFalse(data["ok"])

    def test_owner_can_create_extract(self):
        """Owner CAN create an extract for their own corpus."""
        mutation = """
            mutation CreateExtract($name: String!, $corpusId: ID) {
                createExtract(name: $name, corpusId: $corpusId) {
                    ok
                    msg
                }
            }
        """
        variables = {
            "name": "My Extract",
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = _gql(self.gql_client, mutation, self.owner, variables)
        if result.get("errors"):
            self.fail(f"Unexpected errors: {result['errors']}")
        data = result["data"]["createExtract"]
        self.assertTrue(data["ok"])


# ===========================================================================
# 9. Analyzer is_public default test
# ===========================================================================


class TestAnalyzerIsPublicDefault(TestCase):
    """Tests that Analyzer and GremlinEngine default to is_public=False."""

    def test_analyzer_defaults_to_not_public(self):
        user = User.objects.create_user(username="analyzer_user", password="test")
        gremlin = GremlinEngine.objects.create(
            url="http://localhost:8000", creator=user
        )
        # Analyzer requires either host_gremlin or task_name (DB constraint).
        analyzer = Analyzer.objects.create(
            id="default-test-analyzer",
            description="Test",
            creator=user,
            host_gremlin=gremlin,
        )
        self.assertFalse(analyzer.is_public)

    def test_gremlin_engine_defaults_to_not_public(self):
        user = User.objects.create_user(username="gremlin_user", password="test")
        gremlin = GremlinEngine.objects.create(
            url="http://localhost:8000",
            creator=user,
        )
        self.assertFalse(gremlin.is_public)


# ===========================================================================
# 10. GraphQL security utility tests
# ===========================================================================


class TestDepthLimitValidationRule(TestCase):
    """Tests for the DepthLimitValidationRule GraphQL validation rule.

    Uses graphql-core's validate() directly because the graphene test Client
    does not pass validation_rules (those are applied by GraphQLView in urls.py).
    """

    def _validate_query(self, query_str, max_depth):
        """Validate a query against the real schema with a given depth limit."""
        from graphql import parse, validate

        import config.graphql.security as security_module

        original_depth = security_module.GRAPHQL_MAX_QUERY_DEPTH
        security_module.GRAPHQL_MAX_QUERY_DEPTH = max_depth
        try:
            document = parse(query_str)
            from config.graphql.security import DepthLimitValidationRule

            errors = validate(
                schema.graphql_schema, document, [DepthLimitValidationRule]
            )
            return errors
        finally:
            security_module.GRAPHQL_MAX_QUERY_DEPTH = original_depth

    def test_shallow_query_passes(self):
        """A query within the depth limit should succeed."""
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
        """
        errors = self._validate_query(query, max_depth=15)
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        self.assertEqual(len(depth_errors), 0)

    def test_deep_query_rejected(self):
        """A query exceeding the depth limit should be rejected."""
        # This query has depth ~7: query(0) -> corpuses(1) -> edges(2) ->
        # node(3) -> documents(4) -> edges(5) -> node(6) -> id(7)
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            documents {
                                edges {
                                    node {
                                        id
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """
        errors = self._validate_query(query, max_depth=3)
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        self.assertGreater(
            len(depth_errors), 0, "Expected a depth limit error but got none"
        )

    def test_query_at_exact_limit_passes(self):
        """A query exactly at the depth limit should pass."""
        # This query has depth 4 (corpuses -> edges -> node -> id)
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """
        errors = self._validate_query(query, max_depth=4)
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        self.assertEqual(len(depth_errors), 0)

    def test_query_one_over_limit_rejected(self):
        """A query one level over the limit should be rejected."""
        # Same query as above, but with limit=3 (one less than actual depth 4)
        query = """
            query {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """
        errors = self._validate_query(query, max_depth=3)
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        self.assertGreater(
            len(depth_errors), 0, "Expected a depth limit error but got none"
        )

    def test_fragment_spread_does_not_bypass_limit(self):
        """Fragment spreads should not allow attackers to hide depth."""
        # This uses a fragment to add depth that must be counted
        query = """
            fragment CorpusFields on CorpusType {
                documents {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }

            query {
                corpuses {
                    edges {
                        node {
                            ...CorpusFields
                        }
                    }
                }
            }
        """
        errors = self._validate_query(query, max_depth=3)
        depth_errors = [e for e in errors if "depth" in str(e).lower()]
        self.assertGreater(
            len(depth_errors),
            0,
            "Fragment spread should not bypass depth limit",
        )


class TestDisableIntrospection(TestCase):
    """Tests for the DisableIntrospection validation rule."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="introspection_user", password="test"
        )
        self.gql_client = Client(schema)

    def test_introspection_allowed_without_rule(self):
        """Without DisableIntrospection in validation rules, introspection works.

        This validates that introspection is permitted when the rule is absent
        (the production condition when DEBUG=True in schema.py). We use
        graphql-core's validate() directly because graphene's test Client
        does not apply validation rules.
        """
        from graphql import build_ast_schema, parse, validate

        schema_ast = parse("""
            type Query {
                hello: String
            }
        """)
        test_schema = build_ast_schema(schema_ast)

        introspection_query = parse("{ __schema { types { name } } }")
        # Validate with an empty rules list (no DisableIntrospection)
        errors = validate(test_schema, introspection_query, [])
        introspection_errors = [
            e for e in errors if "introspection" in e.message.lower()
        ]
        self.assertEqual(len(introspection_errors), 0)

    def test_introspection_blocked_with_rule(self):
        """DisableIntrospection rule should block __schema queries."""
        from graphql import build_ast_schema, parse, validate

        from config.graphql.security import DisableIntrospection

        # Use graphql-core's validate directly with the rule
        schema_ast = parse("""
            type Query {
                hello: String
            }
        """)
        test_schema = build_ast_schema(schema_ast)

        introspection_query = parse("{ __schema { types { name } } }")
        errors = validate(test_schema, introspection_query, [DisableIntrospection])
        self.assertGreater(len(errors), 0)
        self.assertIn("introspection", errors[0].message.lower())

    def test_type_introspection_blocked_with_rule(self):
        """DisableIntrospection rule should block __type queries."""
        from graphql import build_ast_schema, parse, validate

        from config.graphql.security import DisableIntrospection

        schema_ast = parse("""
            type Query {
                hello: String
            }
        """)
        test_schema = build_ast_schema(schema_ast)

        type_query = parse('{ __type(name: "Query") { fields { name } } }')
        errors = validate(test_schema, type_query, [DisableIntrospection])
        self.assertGreater(len(errors), 0)
        self.assertIn("introspection", errors[0].message.lower())


class TestConditionalCsrfExempt(TestCase):
    """Tests for the conditional_csrf_exempt decorator."""

    def test_token_auth_bypasses_csrf(self):
        """Requests with Authorization header should bypass CSRF checks."""
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        # Request with Authorization header — should bypass CSRF
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_session_auth_without_csrf_rejected(self):
        """Session-cookie requests with an authenticated session must
        present a CSRF token. Empty/anonymous sessions are covered by
        ``test_anonymous_session_cookie_bypasses_csrf`` below.
        """
        from django.conf import settings
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        # Request carries a session cookie (so CSRF is meaningful) but no
        # CSRF token / Authorization header — should be rejected.
        session_cookie = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
        )
        request.COOKIES[session_cookie] = "fake-session-id"
        request.session = {"_auth_user_id": "1"}
        response = dummy_view(request)
        # CsrfViewMiddleware returns 403 for missing CSRF token
        self.assertEqual(response.status_code, 403)

    def test_anonymous_session_cookie_bypasses_csrf(self):
        """An empty/anonymous session cookie must NOT trigger CSRF.

        Regression for the post-#1789 production 403 storm: the corpus
        voting flow forces a Django session row into existence for
        anonymous voters so it can dedupe votes by ``session_key``.  The
        subsequent ``Set-Cookie`` makes every following anonymous POST
        carry a ``sessionid`` — but there is no authenticated identity in
        that session for a CSRF attacker to ride on. Treating the bare
        cookie as evidence of session auth (pre-fix behaviour) 403'd the
        next vote / refetch / GET_ME and cascaded into a "session
        expired" toast loop.
        """
        from django.conf import settings
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        session_cookie = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
        )
        request.COOKIES[session_cookie] = "anon-vote-session"
        # Empty session — no ``_auth_user_id`` ever set. This is exactly
        # the shape ``_ensure_session_key`` leaves behind after an
        # anonymous vote.
        request.session = {}
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_session_without_session_attr_bypasses_csrf(self):
        """A session cookie on a request that never went through
        ``SessionMiddleware`` (no ``request.session``) must bypass CSRF.

        Defensive belt-and-braces for misconfigured deployments / test
        harnesses: with no session attached we cannot tell whether the
        cookie maps to an authenticated user, but we also cannot tell
        whether it maps to anything at all — and the request has no
        Bearer token to fall back to. Treating the unknown as "anonymous"
        keeps legitimate traffic flowing; the underlying auth resolver
        still rejects privileged operations on its own merits.
        """
        from django.conf import settings
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        session_cookie = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
        )
        request.COOKIES[session_cookie] = "stale-cookie"
        # Deliberately do NOT attach request.session — RequestFactory
        # does not run middleware.
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_anonymous_no_session_bypasses_csrf(self):
        """A POST with neither Authorization nor session cookie should pass.

        Bearer-only API clients (e.g. the React frontend) momentarily have
        no token during startup / refresh and must not be 403'd by CSRF
        when they carry no cookie an attacker could ride.
        """
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
        )
        # No Authorization header, no session cookie.
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_empty_authorization_header_treated_as_missing(self):
        # Regression for the production 403 storm where the frontend sent
        # ``Authorization: ""`` whenever the Auth0 token was momentarily
        # empty.  A non-credential is not a credential: we must not let an
        # empty header switch us to the token-auth bypass *or* leave a
        # legitimate cookie-less request blocked.
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        # Empty header, no session cookie → anonymous bypass.
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="",
        )
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

        # Whitespace-only header is also not a credential.
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="   ",
        )
        response = dummy_view(request)
        self.assertEqual(response.status_code, 200)

    def test_empty_authorization_with_authed_session_still_enforces_csrf(self):
        """Empty Authorization + authenticated session must NOT bypass CSRF.

        Defense-in-depth: an empty ``Authorization`` header must not trick
        the decorator into treating the request as token-authenticated.
        With an authenticated session present we still need CSRF.
        """
        from django.conf import settings
        from django.test import RequestFactory

        from config.graphql.security import conditional_csrf_exempt

        factory = RequestFactory()

        @conditional_csrf_exempt
        def dummy_view(request):
            from django.http import HttpResponse

            return HttpResponse("ok")

        session_cookie = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
        request = factory.post(
            "/graphql/",
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="",
        )
        request.COOKIES[session_cookie] = "fake-session-id"
        request.session = {"_auth_user_id": "1"}
        response = dummy_view(request)
        self.assertEqual(response.status_code, 403)

    def test_csrf_exempt_attribute_set(self):
        """The wrapped view should have csrf_exempt=True attribute."""
        from config.graphql.security import conditional_csrf_exempt

        @conditional_csrf_exempt
        def dummy_view(request):
            pass

        self.assertTrue(getattr(dummy_view, "csrf_exempt", False))

    # -------------------------------------------------------------------
    # Issue #1432 — strict scheme validation for Authorization headers
    # -------------------------------------------------------------------

    def _decorate_dummy(self):
        """Build a wrapped view that returns 200 when CSRF check passes."""
        from django.http import HttpResponse

        from config.graphql.security import conditional_csrf_exempt

        @conditional_csrf_exempt
        def dummy_view(request):
            return HttpResponse("ok")

        return dummy_view

    def _post(self, **headers):
        from django.test import RequestFactory

        return RequestFactory().post(
            "/graphql/", data="{}", content_type="application/json", **headers
        )

    def _post_with_session(self, **headers):
        """Build a POST with an **authenticated** session attached.

        The CSRF gate only fires when a session cookie *and* an
        authenticated identity in the session are both present (issue
        #1789 follow-up). The scheme-validation tests below want the
        "session-authenticated, no Bearer" path, so we attach a minimal
        session dict with ``_auth_user_id`` populated alongside the
        cookie. The cookie itself just needs to be non-empty for the
        decorator's ``has_session_cookie`` short-circuit.
        """
        from django.conf import settings

        request = self._post(**headers)
        request.COOKIES[getattr(settings, "SESSION_COOKIE_NAME", "sessionid")] = (
            "fake-session"
        )
        request.session = {"_auth_user_id": "1"}
        return request

    def test_unrecognized_scheme_with_session_enforces_csrf(self):
        """
        ``Authorization: Basic <creds>`` is *not* a token-auth scheme this app
        recognises. With a session cookie present the request must still be
        treated as session-authenticated, so CSRF protection has to fire.

        The pre-#1432 implementation accepted *any* non-empty Authorization
        header as evidence of token auth, which would have bypassed CSRF
        here. This is the regression test for that hardening.
        """
        view = self._decorate_dummy()
        request = self._post_with_session(HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_unrecognized_scheme_without_session_bypasses_csrf(self):
        """No session cookie means there is nothing for CSRF to defend.

        A bogus ``Authorization`` value must not promote the request out of
        the no-cookie bypass into a CSRF-enforced session path. The request
        is fully anonymous and falls through to the resolver where it will
        fail authentication on its own merits.
        """
        view = self._decorate_dummy()
        request = self._post(HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_bearer_without_credential_with_session_enforces_csrf(self):
        """``Authorization: Bearer `` with no credential is not a token.

        A scheme keyword by itself is not a credential. Combined with a
        session cookie, the request must still go through CSRF.
        """
        view = self._decorate_dummy()
        for value in ("Bearer", "Bearer ", "Bearer    "):
            with self.subTest(value=repr(value)):
                request = self._post_with_session(HTTP_AUTHORIZATION=value)
                response = view(request)
                self.assertEqual(response.status_code, 403)

    def test_bearer_with_credential_bypasses_csrf(self):
        """A well-formed Bearer credential bypasses CSRF as before."""
        view = self._decorate_dummy()
        request = self._post_with_session(HTTP_AUTHORIZATION="Bearer abc.def.ghi")
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_bearer_scheme_is_case_insensitive(self):
        """RFC 7235: auth-scheme is case-insensitive.

        We recognise ``Bearer``, ``BEARER`` and ``bearer`` identically so a
        client that lower-cases the scheme isn't dropped into the session
        path by accident.
        """
        view = self._decorate_dummy()
        for value in ("BEARER abc.def.ghi", "bearer abc.def.ghi"):
            with self.subTest(value=value):
                request = self._post_with_session(HTTP_AUTHORIZATION=value)
                response = view(request)
                self.assertEqual(response.status_code, 200)

    def test_api_key_scheme_bypasses_csrf(self):
        """The configured API_TOKEN_PREFIX is recognised.

        OpenContracts' optional API-key auth uses ``Authorization: <prefix>
        <token>``; cross-origin browsers can't attach this header, so it's
        safe to bypass CSRF when the prefix is well-formed. The prefix is
        only registered when ``ALLOW_API_KEYS`` is on, so override the
        setting to keep the test independent of the deployment toggle.
        """
        from django.test import override_settings

        view = self._decorate_dummy()
        with override_settings(API_TOKEN_PREFIX="KEY"):
            request = self._post_with_session(HTTP_AUTHORIZATION="KEY abc123")
            response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_authed_session_with_csrf_token_passes(self):
        """Positive session+CSRF path: request with a matching CSRF token passes.

        Closes the gap in the test matrix called out in #1432: the existing
        suite covered the *reject* leg of session+CSRF but never the
        *accept* leg.  An authenticated session is required to actually
        exercise the CSRF middleware (anonymous sessions bypass per
        issue #1789 follow-up — see ``test_anonymous_session_cookie_bypasses_csrf``).
        """
        from django.middleware.csrf import get_token
        from django.test import RequestFactory, override_settings

        view = self._decorate_dummy()

        with override_settings(CSRF_USE_SESSIONS=False):
            factory = RequestFactory()
            request = factory.post(
                "/graphql/",
                data="{}",
                content_type="application/json",
            )
            # `get_token` is the public API: it stashes the unmasked secret in
            # META["CSRF_COOKIE"] (where the middleware reads it under
            # CSRF_USE_SESSIONS=False) and returns the masked token to send
            # in the cookie / X-CSRFToken header.
            token = get_token(request)
            request.META["HTTP_X_CSRFTOKEN"] = token
            request.COOKIES["csrftoken"] = token
            request.COOKIES["sessionid"] = "fake-session"
            request.session = {"_auth_user_id": "1"}
            response = view(request)

        self.assertEqual(response.status_code, 200)


class TestCsrfRejectLogVolume(TestCase):
    """Issue #1432 item 2 — keep production logs quiet for the *expected*
    'session-only POST without CSRF' rejection pattern.

    The Django default logs every CSRF reject at WARNING via
    ``django.security.csrf``. In production that one path drowns out real
    anomalies because Bearer-only SPAs trip it on every cold start. The
    hardening adds a ``logging.Filter`` that demotes the WARNING to INFO
    *only* when the rejection reason is the benign 'CSRF token missing'
    case — anything else (bad referer, origin mismatch, malformed token)
    still surfaces at WARNING.
    """

    def test_filter_demotes_csrf_token_missing_warning_to_info(self):
        import logging

        from config.graphql.security import CsrfRejectLogFilter

        filt = CsrfRejectLogFilter()
        record = logging.LogRecord(
            name="django.security.csrf",
            level=logging.WARNING,
            pathname=__file__,
            lineno=0,
            msg="Forbidden (%s): %s",
            args=("CSRF token missing.", "/graphql/"),
            exc_info=None,
        )

        # The filter must mutate the record in place and keep emitting it
        # (return True), so the message is preserved at the lower level.
        self.assertTrue(filt.filter(record))
        self.assertEqual(record.levelno, logging.INFO)
        self.assertEqual(record.levelname, "INFO")

    def test_filter_does_not_demote_other_csrf_reasons(self):
        """Genuine anomalies (origin mismatch, bad referer) stay at WARNING."""
        import logging

        from config.graphql.security import CsrfRejectLogFilter

        filt = CsrfRejectLogFilter()
        for reason in (
            "Origin checking failed - https://evil.example does not match any trusted origins.",
            "Referer checking failed - no Referer.",
            "CSRF token incorrect.",
        ):
            with self.subTest(reason=reason):
                record = logging.LogRecord(
                    name="django.security.csrf",
                    level=logging.WARNING,
                    pathname=__file__,
                    lineno=0,
                    msg="Forbidden (%s): %s",
                    args=(reason, "/graphql/"),
                    exc_info=None,
                )
                self.assertTrue(filt.filter(record))
                self.assertEqual(record.levelno, logging.WARNING)

    def test_filter_passes_unrelated_records_unchanged(self):
        """Records without the standard CSRF reject shape are untouched."""
        import logging

        from config.graphql.security import CsrfRejectLogFilter

        filt = CsrfRejectLogFilter()
        record = logging.LogRecord(
            name="django.security.csrf",
            level=logging.WARNING,
            pathname=__file__,
            lineno=0,
            msg="Some other CSRF-related warning",
            args=None,
            exc_info=None,
        )
        self.assertTrue(filt.filter(record))
        self.assertEqual(record.levelno, logging.WARNING)


# ---------------------------------------------------------------------------
# DRFMutation ValidationError formatting
# ---------------------------------------------------------------------------


class TestDRFMutationValidationError(TestCase):
    """Test that DRFMutation properly formats validation errors."""

    def test_validation_error_dict_format(self):
        """Dict-form ValidationError should be formatted with field names."""
        from rest_framework import serializers

        from config.graphql.base import DRFMutation

        detail = {"name": ["This field is required."], "email": ["Invalid format."]}
        exc = serializers.ValidationError(detail)

        message = DRFMutation.format_validation_error(exc)
        self.assertIn("name:", message)
        self.assertIn("email:", message)
        self.assertIn("This field is required.", message)

    def test_validation_error_list_format(self):
        """List-form ValidationError should be joined with semicolons."""
        from rest_framework import serializers

        from config.graphql.base import DRFMutation

        detail = ["Error one.", "Error two."]
        exc = serializers.ValidationError(detail)

        message = DRFMutation.format_validation_error(exc)
        self.assertIn("Error one.", message)
        self.assertIn("Error two.", message)


# ---------------------------------------------------------------------------
# DRFMutation / DRFDeletion IOSettings misconfiguration guard
# ---------------------------------------------------------------------------


class TestIOSettingsRequiredFieldsGuard(TestCase):
    """Misconfigured IOSettings must raise ``NotImplementedError`` at mutation time."""

    def test_require_io_setting_raises_when_io_settings_missing(self):
        from config.graphql.base import _require_io_setting

        class MisconfiguredMutation:
            pass

        with self.assertRaises(NotImplementedError) as ctx:
            _require_io_setting(MisconfiguredMutation, "model")
        self.assertIn("MisconfiguredMutation", str(ctx.exception))
        # Distinct message for the missing-class case (vs. missing-field).
        self.assertIn("IOSettings", str(ctx.exception))

    def test_require_io_setting_raises_when_attribute_none(self):
        """Each of model/serializer/graphene_model must independently fail when ``None``."""
        from config.graphql.base import _require_io_setting

        class MisconfiguredMutation:
            class IOSettings:
                model = None
                serializer = None
                graphene_model = None

        for field in ("model", "serializer", "graphene_model"):
            with self.assertRaises(NotImplementedError) as ctx:
                _require_io_setting(MisconfiguredMutation, field)
            self.assertIn("MisconfiguredMutation", str(ctx.exception))
            self.assertIn(field, str(ctx.exception))

    def test_require_io_setting_returns_configured_value(self):
        from config.graphql.base import _require_io_setting

        class ConfiguredMutation:
            class IOSettings:
                model = Corpus

        self.assertIs(_require_io_setting(ConfiguredMutation, "model"), Corpus)

    def test_base_iosettings_defaults_are_none_on_mutation(self):
        """Base ``IOSettings`` must default to ``None`` so the runtime guard can fire."""
        from config.graphql.base import DRFDeletion, DRFMutation

        self.assertIsNone(DRFMutation.IOSettings.model)
        self.assertIsNone(DRFMutation.IOSettings.serializer)
        self.assertIsNone(DRFMutation.IOSettings.graphene_model)
        self.assertIsNone(DRFDeletion.IOSettings.model)

    def test_drf_deletion_mutate_raises_when_lookup_value_missing(self):
        """``DRFDeletion.mutate`` must raise ``ValueError`` when the lookup arg is omitted."""
        from unittest.mock import MagicMock

        from graphene import ResolveInfo

        from config.graphql.base import DRFDeletion

        class _DeleteCorpus(DRFDeletion):
            class IOSettings(DRFDeletion.IOSettings):
                model = Corpus
                lookup_field = "id"

        # ``@login_required`` from graphql_jwt looks for a ``ResolveInfo`` arg
        # via ``isinstance``; spec the mock so the decorator passes through
        # to the wrapped function where the real lookup-value check fires.
        # This relies on ``@graphql_ratelimit`` being a no-op under test
        # conditions (no real cache backend is consulted before the body).
        info = MagicMock(spec=ResolveInfo)
        info.context = MagicMock()
        info.context.user = MagicMock(is_authenticated=True)

        with self.assertRaises(ValueError) as ctx:
            _DeleteCorpus.mutate(None, info)
        self.assertIn("id", str(ctx.exception))

    def test_drf_mutation_obj_id_uses_graphene_type_name_not_metaclass(self):
        """Regression: ``to_global_id`` must use ``graphene_model.__name__``
        (the GraphQL type, e.g. ``"CorpusType"``), not
        ``graphene_model.__class__.__name__`` (the metaclass name like
        ``"SubclassWithMeta_Meta"``).
        """
        from graphene.test import Client
        from graphql_relay import from_global_id

        from config.graphql.schema import schema
        from opencontractserver.corpuses.models import Corpus

        user = User.objects.create_user(username="objIdRegressionUser", password="x")

        class _Ctx:
            def __init__(self, user):
                self.user = user

        client = Client(schema, context_value=_Ctx(user))
        result = client.execute("""
            mutation {
                createCorpus(title: "ObjIdRegression") {
                    ok
                    objId
                }
            }
            """)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])

        obj_id = result["data"]["createCorpus"]["objId"]
        type_name, pk = from_global_id(obj_id)
        # The fix: ``__name__`` produces the graphene type name.
        self.assertEqual(type_name, "CorpusType")
        # Underlying row exists at that pk — proves the global id is decodable.
        self.assertTrue(Corpus.objects.filter(pk=int(pk)).exists())
