"""Tests for the AgentActionResult model."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.conversations.models import Conversation
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusActionTrigger
from opencontractserver.documents.models import Document

User = get_user_model()


class AgentActionResultModelTestCase(TestCase):
    """Test cases for the AgentActionResult model."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.document = Document.objects.create(
            title="Test Document",
            description="Test description",
            creator=self.user,
        )
        self.agent_config = AgentConfiguration.objects.create(
            name="Test Agent Config",
            description="Test agent configuration",
            system_instructions="You are a helpful assistant",
            is_active=True,
            creator=self.user,
        )
        self.corpus_action = CorpusAction.objects.create(
            corpus=self.corpus,
            agent_config=self.agent_config,
            task_instructions="Summarize this document",
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        self.conversation = Conversation.objects.create(
            title="Test Conversation",
            creator=self.user,
        )

    def test_create_agent_action_result(self):
        """Test creating an AgentActionResult."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.PENDING,
            creator=self.user,
        )
        self.assertIsNotNone(result.id)
        self.assertEqual(result.corpus_action, self.corpus_action)
        self.assertEqual(result.document, self.document)
        self.assertEqual(result.conversation, self.conversation)
        self.assertEqual(result.status, AgentActionResult.Status.PENDING)

    def test_agent_action_result_status_transitions(self):
        """Test status transitions for AgentActionResult."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.PENDING,
            creator=self.user,
        )

        # Transition to running
        result.status = AgentActionResult.Status.RUNNING
        result.save()
        result.refresh_from_db()
        self.assertEqual(result.status, AgentActionResult.Status.RUNNING)

        # Transition to completed
        result.status = AgentActionResult.Status.COMPLETED
        result.agent_response = "Document summarized successfully."
        result.save()
        result.refresh_from_db()
        self.assertEqual(result.status, AgentActionResult.Status.COMPLETED)
        self.assertEqual(result.agent_response, "Document summarized successfully.")

    def test_agent_action_result_with_tools_executed(self):
        """Test AgentActionResult with tools_executed."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.COMPLETED,
            agent_response="Document description updated.",
            tools_executed=[
                {"tool": "search_annotations", "args": {"query": "summary"}},
                {
                    "tool": "update_document_description",
                    "args": {"description": "New desc"},
                },
            ],
            creator=self.user,
        )
        self.assertEqual(len(result.tools_executed), 2)
        self.assertEqual(result.tools_executed[0]["tool"], "search_annotations")

    def test_agent_action_result_with_error(self):
        """Test AgentActionResult with an error."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.FAILED,
            error_message="LLM API rate limit exceeded",
            creator=self.user,
        )
        self.assertEqual(result.status, AgentActionResult.Status.FAILED)
        self.assertEqual(result.error_message, "LLM API rate limit exceeded")

    def test_agent_action_result_str(self):
        """Test the string representation of AgentActionResult."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )
        expected_str = f"AgentActionResult({self.corpus_action.name} on doc:{self.document.id}: completed)"
        self.assertEqual(str(result), expected_str)

    def test_agent_action_result_visible_to_user(self):
        """Test the visible_to_user manager method."""
        # Create result with proper permissions
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )

        # Creator should see their own results
        visible = AgentActionResult.objects.visible_to_user(self.user)
        self.assertIn(result, visible)

        # Another user should not see it (without permissions)
        other_user = User.objects.create_user(username="other", password="testpass")
        visible_to_other = AgentActionResult.objects.visible_to_user(other_user)
        self.assertNotIn(result, visible_to_other)

    def test_agent_action_result_execution_metadata(self):
        """Test AgentActionResult with execution metadata."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            conversation=self.conversation,
            status=AgentActionResult.Status.COMPLETED,
            execution_metadata={
                "model_used": "gpt-4o-mini",
                "total_tokens": 1500,
                "prompt_tokens": 1000,
                "completion_tokens": 500,
            },
            creator=self.user,
        )
        self.assertEqual(result.execution_metadata["model_used"], "gpt-4o-mini")
        self.assertEqual(result.execution_metadata["total_tokens"], 1500)

    def test_agent_action_result_str_for_thread_based_action(self):
        """Test __str__ for thread-based AgentActionResult (without document)."""
        thread = Conversation.objects.create(
            title="Triggering Thread",
            creator=self.user,
        )
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=None,  # No document - thread-based action
            triggering_conversation=thread,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )
        expected_str = f"AgentActionResult({self.corpus_action.name} on thread:{thread.id}: completed)"
        self.assertEqual(str(result), expected_str)

    def test_agent_action_result_str_for_unknown_target(self):
        """Test __str__ when neither document nor triggering_conversation is set."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=None,
            triggering_conversation=None,
            status=AgentActionResult.Status.PENDING,
            creator=self.user,
        )
        expected_str = (
            f"AgentActionResult({self.corpus_action.name} on unknown: pending)"
        )
        self.assertEqual(str(result), expected_str)

    def test_agent_action_result_duration_seconds(self):
        """Test the duration_seconds property."""
        from datetime import timedelta

        from django.utils import timezone

        start = timezone.now()
        end = start + timedelta(seconds=30)

        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            started_at=start,
            completed_at=end,
            creator=self.user,
        )
        duration = result.duration_seconds
        assert duration is not None
        self.assertAlmostEqual(duration, 30.0)

    def test_agent_action_result_duration_seconds_none_when_incomplete(self):
        """Test duration_seconds is None when timestamps are missing."""
        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.RUNNING,
            started_at=None,
            completed_at=None,
            creator=self.user,
        )
        self.assertIsNone(result.duration_seconds)

    def test_visible_to_user_anonymous_user(self):
        """Test visible_to_user returns empty for anonymous on private corpus."""
        from django.contrib.auth.models import AnonymousUser

        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )

        anon = AnonymousUser()
        visible = AgentActionResult.objects.visible_to_user(anon)
        self.assertNotIn(result, visible)

    def test_visible_to_user_anonymous_user_public_corpus(self):
        """Test visible_to_user returns results for public corpus to anonymous."""
        from django.contrib.auth.models import AnonymousUser

        # Make corpus public
        self.corpus.is_public = True
        self.corpus.save()

        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )

        anon = AnonymousUser()
        visible = AgentActionResult.objects.visible_to_user(anon)
        self.assertIn(result, visible)

    def test_visible_to_user_superuser_has_no_blanket_access(self):
        """Scoped admin access (2026-05): a no-grant superuser is computed like
        a normal user. ``AgentActionResult.visible_to_user`` inherits visibility
        from ``corpus_action__corpus`` via ``Corpus.objects.visible_to_user``,
        so a result on a private corpus owned by another user is NOT visible to
        a stranger superuser. Granting corpus READ exposes it via the normal
        path."""
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        superuser = User.objects.create_superuser(
            username="agent_result_superuser",
            password="adminpass",
            email="agent_result_admin@test.com",
        )

        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )

        # No grant: the private corpus owned by ``self.user`` is invisible to
        # the superuser, so the result is too.
        visible = AgentActionResult.objects.visible_to_user(superuser)
        self.assertNotIn(result, visible)

        # Positive path: grant corpus READ via the normal guardian path.
        set_permissions_for_obj_to_user(superuser, self.corpus, [PermissionTypes.READ])
        visible_after = AgentActionResult.objects.visible_to_user(superuser)
        self.assertIn(result, visible_after)

    def test_visible_to_user_with_none_user(self):
        """Test visible_to_user handles None user (like anonymous)."""
        # Make corpus public for this test
        self.corpus.is_public = True
        self.corpus.save()

        result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.user,
        )

        visible = AgentActionResult.objects.visible_to_user(None)
        # Should return public results
        self.assertIn(result, visible)


class AgentConfigurationSlugTestCase(TestCase):
    """Test AgentConfiguration slug auto-generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def test_auto_generates_slug_from_name(self):
        """Test that slug is auto-generated from name if not provided."""
        agent = AgentConfiguration.objects.create(
            name="My Research Assistant",
            system_instructions="You are helpful",
            creator=self.user,
        )
        self.assertEqual(agent.slug, "my-research-assistant")

    def test_preserves_explicit_slug(self):
        """Test that explicit slug is preserved."""
        agent = AgentConfiguration.objects.create(
            name="My Research Assistant",
            slug="custom-slug",
            system_instructions="You are helpful",
            creator=self.user,
        )
        self.assertEqual(agent.slug, "custom-slug")

    def test_handles_slug_collision(self):
        """Test that slug collision is handled by appending number."""
        # Create first agent with auto-generated slug
        agent1 = AgentConfiguration.objects.create(
            name="Test Agent",
            system_instructions="You are helpful",
            creator=self.user,
        )
        self.assertEqual(agent1.slug, "test-agent")

        # Create second agent with same name - should get different slug
        agent2 = AgentConfiguration.objects.create(
            name="Test Agent",
            system_instructions="You are also helpful",
            creator=self.user,
        )
        self.assertEqual(agent2.slug, "test-agent-1")

        # Create third agent with same name - should increment
        agent3 = AgentConfiguration.objects.create(
            name="Test Agent",
            system_instructions="You are very helpful",
            creator=self.user,
        )
        self.assertEqual(agent3.slug, "test-agent-2")
