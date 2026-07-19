"""Coverage-focused tests for ``config/graphql/conversation_types.py``.

Targets resolver branches a full-suite coverage run showed as never
exercised: mention-resolution edge cases in ``resolve_mentions_for_user``
(the shared chokepoint documented on that function), scalar-field
fallbacks (``userVote``, ``conversationType``, ``msgType``, ``agentType``),
connection fields with filter arguments, permission-annotation fields, and
the permission-aware ``get_node``/``get_queryset`` hooks.

Deliberately NOT re-tested here (already covered elsewhere, confirmed by
grep before writing this file):
  * corpus/document mention success + cross-user permission filtering
    -> opencontractserver/tests/test_mentions.py
  * agent mention resolution (global, corpus-scoped, inactive, mismatched
    corpus, unknown slug) -> test_chat_message_mentioned_resources.py
  * MessageType.userVote authenticated upvote/downvote/removed
    -> test_voting_mutations_graphql.py
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.utils import timezone
from graphql_relay import to_global_id

from config.graphql import conversation_types as ct
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    ConversationVote,
    ModerationAction,
)
from opencontractserver.conversations.models import (
    ModerationActionType as ModerationActionTypeChoices,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTrigger,
)
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.mention_extractor import ExtractedMention
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.research.models import ResearchReport
from opencontractserver.types.enums import JobStatus, PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


def _request(user):
    """Graphene-style fake request object: only ``.user`` is read."""
    return type("Request", (), {"user": user})()


class _Ctx:
    """Minimal GraphQL-context stand-in (carries only ``.user``)."""

    def __init__(self, user):
        self.user = user


class _Info:
    """Minimal ``strawberry.Info``-like stand-in for direct resolver calls."""

    def __init__(self, user):
        self.context = _Ctx(user)


class _Row:
    """Lightweight stand-in for a Django row exposing only the attributes a
    pure ``_resolve_*`` helper reads (mirrors the pattern in
    ``test_fk_visibility_traversal.py``)."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# --------------------------------------------------------------------------- #
# resolve_mentions_for_user edge cases
# --------------------------------------------------------------------------- #


class MentionResolutionEdgeCaseTests(TestCase):
    """Defensive branches of ``resolve_mentions_for_user`` that the
    extractor's real grammar never produces (malformed ``slug``/``id``), plus
    the annotation-mention branch and the catch-all exception guard, none of
    which any existing test exercises."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="mentioner", password="test", slug="mentioner"
        )

        self.corpus = Corpus.objects.create(
            title="Mention Corpus", creator=self.user, slug="mention-corpus"
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        original_doc = Document.objects.create(
            title="Mentioned Doc",
            creator=self.user,
            slug="mentioned-doc-orig",
            backend_lock=True,
        )
        self.doc_in_corpus, _, _ = self.corpus.add_document(
            document=original_doc, user=self.user
        )
        self.doc_in_corpus.slug = "mentioned-doc"
        self.doc_in_corpus.save(update_fields=["slug"])

        # A second, equally-visible corpus that the document above is NOT
        # placed in — used to hit the "corpus visible but doc not there"
        # branch (conversation_types.py line 270).
        self.other_corpus = Corpus.objects.create(
            title="Other Corpus", creator=self.user, slug="other-corpus"
        )
        set_permissions_for_obj_to_user(
            self.user, self.other_corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )

        # A standalone document with zero DocumentPath rows — used to hit
        # the "no corpus context at all" branch (lines 293-294).
        self.standalone_doc = Document.objects.create(
            title="Standalone Doc",
            creator=self.user,
            slug="standalone-doc",
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(
            self.user, self.standalone_doc, [PermissionTypes.READ]
        )

        self.label = AnnotationLabel.objects.create(
            text="Indemnification Clause", creator=self.user
        )
        self.annotation = Annotation.objects.create(
            document=self.doc_in_corpus,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            raw_text="Neither party shall be liable for indirect damages.",
            page=1,
        )

        self.conversation = Conversation.objects.create(
            title="Mention Thread",
            creator=self.user,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        self.gql_client = Client(schema)

    def _query_mentions(self, content: str, user=None):
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user,
            content=content,
        )
        query = """
            query GetMessage($id: ID!) {
                chatMessage(id: $id) {
                    mentionedResources {
                        type
                        slug
                        title
                        url
                        rawText
                        annotationLabel
                        corpus { slug }
                        document { slug corpus { slug } }
                    }
                }
            }
        """
        result = self.gql_client.execute(
            query,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=_request(user or self.user),
        )
        self.assertIsNone(result.get("errors"))
        return result["data"]["chatMessage"]["mentionedResources"]

    # -- annotation mention branch (lines 118, 308-315) --------------------- #

    def test_annotation_mention_resolves_with_full_metadata(self):
        ann_gid = to_global_id("AnnotationType", self.annotation.id)
        mentions = self._query_mentions(
            f"See [context](/d/mentioner/{self.doc_in_corpus.slug}?ann={ann_gid})"
        )
        self.assertEqual(len(mentions), 1)
        entry = mentions[0]
        self.assertEqual(entry["type"], "annotation")
        self.assertIsNone(entry["slug"], "annotations don't have slugs")
        self.assertEqual(entry["annotationLabel"], "Indemnification Clause")
        self.assertEqual(
            entry["rawText"],
            "Neither party shall be liable for indirect damages.",
        )
        self.assertEqual(entry["document"]["slug"], self.doc_in_corpus.slug)

    def test_annotation_mention_missing_id_is_skipped(self):
        # extract_mentions never emits an annotation mention without an id
        # (``_classify_url`` only builds one when ``_decode_annotation_id``
        # succeeds), so this guard is only reachable via a directly
        # constructed ExtractedMention.
        mentions = ct.resolve_mentions_for_user(
            [ExtractedMention(type="annotation", id=None, url="/d/x/y?ann=bad")],
            self.user,
        )
        self.assertEqual(mentions, [])

    def test_annotation_mention_unknown_id_is_silently_omitted(self):
        mentions = ct.resolve_mentions_for_user(
            [
                ExtractedMention(
                    type="annotation", id=999_999_999, url="/d/x/y?ann=999999999"
                )
            ],
            self.user,
        )
        self.assertEqual(mentions, [])

    # -- malformed mentions the real extractor never produces --------------- #
    # (its grammar always supplies a non-empty slug for corpus/document/agent
    # mentions -- these guards protect resolve_mentions_for_user, the single
    # chokepoint shared by every current AND future caller, against any
    # caller that skips extract_mentions and builds ExtractedMention rows
    # directly.)

    def test_corpus_mention_missing_slug_is_skipped(self):
        mentions = ct.resolve_mentions_for_user(
            [ExtractedMention(type="corpus", slug=None, url="/c/_/x")], self.user
        )
        self.assertEqual(mentions, [])

    def test_document_mention_missing_slug_is_skipped(self):
        mentions = ct.resolve_mentions_for_user(
            [ExtractedMention(type="document", slug=None, url="/d/_/x")], self.user
        )
        self.assertEqual(mentions, [])

    def test_agent_mention_missing_slug_is_skipped(self):
        mentions = ct.resolve_mentions_for_user(
            [ExtractedMention(type="agent", slug=None, url="/agents/")], self.user
        )
        self.assertEqual(mentions, [])

    # -- document-in-corpus edge cases (lines 268, 270, 293-294) ------------ #

    def test_document_mention_corpus_slug_not_found_is_skipped(self):
        mentions = self._query_mentions(
            f"[link](/d/mentioner/no-such-corpus/{self.doc_in_corpus.slug})"
        )
        self.assertEqual(mentions, [])

    def test_document_mention_corpus_visible_but_document_not_in_it_is_skipped(self):
        mentions = self._query_mentions(
            f"[link](/d/mentioner/{self.other_corpus.slug}/{self.doc_in_corpus.slug})"
        )
        self.assertEqual(mentions, [])

    def test_standalone_document_mention_has_no_corpus_context(self):
        mentions = self._query_mentions(f"@document:{self.standalone_doc.slug}")
        self.assertEqual(len(mentions), 1)
        entry = mentions[0]
        self.assertEqual(entry["type"], "document")
        self.assertIsNone(entry["corpus"])
        self.assertEqual(entry["url"], f"/d/mentioner/{self.standalone_doc.slug}")

    # -- catch-all exception guard (lines 366, 368, 369) --------------------- #

    def test_mention_resolution_exception_is_isolated_and_logged(self):
        """A construction failure for one mention must not swallow the
        others, and must be logged rather than propagated (the resolver's
        documented "silent omission: never leak existence via error"
        contract)."""
        real_type = ct.MentionedResourceType

        def _boom_on_annotation(*args, **kwargs):
            if kwargs.get("type") == "annotation":
                raise RuntimeError("simulated construction failure")
            return real_type(*args, **kwargs)

        mentions = [
            ExtractedMention(type="corpus", slug=self.corpus.slug, url="/c/x/y"),
            ExtractedMention(
                type="annotation",
                id=self.annotation.id,
                url=f"/d/x/y?ann={self.annotation.id}",
            ),
        ]

        with mock.patch.object(
            ct, "MentionedResourceType", side_effect=_boom_on_annotation
        ), self.assertLogs(
            "config.graphql.conversation_types", level="ERROR"
        ) as log_ctx:
            resolved = ct.resolve_mentions_for_user(mentions, self.user)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].type, "corpus")
        self.assertTrue(
            any("Mention resolution failed" in line for line in log_ctx.output)
        )


# --------------------------------------------------------------------------- #
# ConversationType scalar/permission fields
# --------------------------------------------------------------------------- #


class ConversationTypeScalarFieldTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="conv_owner", password="test", slug="conv-owner"
        )
        # is_public=True so the anonymous-user branch of userVote is
        # actually reachable through the top-level `conversation(id)` node
        # lookup (a private THREAD is invisible to anonymous callers before
        # the userVote resolver ever runs). No explicit per-user permission
        # grant here -- creator visibility alone is enough for the owner to
        # fetch their own conversation, and it keeps objectSharedWith's
        # underlying `conversationuserobjectpermission_set` empty (see
        # test_object_shared_with_field_returns_empty_when_unshared).
        self.conversation = Conversation.objects.create(
            title="Scalar Thread",
            description="a real description",
            compaction_summary="earlier turns summarized here",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )
        self.gql_client = Client(schema)

    def _execute(self, query, user):
        return self.gql_client.execute(
            query,
            variables={"id": to_global_id("ConversationType", self.conversation.id)},
            context_value=_request(user),
        )

    def test_description_and_compaction_summary_fields(self):
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) "
            "{ description compactionSummary } }",
            self.owner,
        )
        self.assertIsNone(result.get("errors"))
        node = result["data"]["conversation"]
        self.assertEqual(node["description"], "a real description")
        self.assertEqual(node["compactionSummary"], "earlier turns summarized here")

    def test_conversation_type_helper_returns_none_when_blank(self):
        # Django doesn't validate choices at the ORM level, so a blank
        # conversation_type is reachable via direct assignment even though
        # the model default is CHAT. Such a row also matches neither the
        # CHAT nor THREAD branch of ConversationQuerySet.visible_to_user, so
        # it is unreachable via any GraphQL query (including by its own
        # creator) -- the pure helper is the only way to exercise this
        # fallback.
        self.assertIsNone(
            ct._resolve_ConversationType_conversation_type(
                _Row(conversation_type=""), None
            )
        )

    def test_all_messages_field_returns_every_message(self):
        first = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.owner,
            content="first",
        )
        second = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.owner,
            content="second",
        )
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { allMessages { id } } }",
            self.owner,
        )
        self.assertIsNone(result.get("errors"))
        ids = {m["id"] for m in result["data"]["conversation"]["allMessages"]}
        self.assertEqual(
            ids,
            {
                to_global_id("MessageType", first.id),
                to_global_id("MessageType", second.id),
            },
        )

    def test_user_vote_anonymous_returns_null(self):
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { userVote } }",
            AnonymousUser(),
        )
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["conversation"]["userVote"])

    def test_user_vote_no_vote_returns_null(self):
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { userVote } }",
            self.owner,
        )
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["conversation"]["userVote"])

    def test_user_vote_reflects_upvote_and_downvote(self):
        ConversationVote.objects.create(
            conversation=self.conversation,
            creator=self.owner,
            vote_type="upvote",
        )
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { userVote } }",
            self.owner,
        )
        self.assertEqual(result["data"]["conversation"]["userVote"], "UPVOTE")

        ConversationVote.objects.filter(
            conversation=self.conversation, creator=self.owner
        ).update(vote_type="downvote")
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { userVote } }",
            self.owner,
        )
        self.assertEqual(result["data"]["conversation"]["userVote"], "DOWNVOTE")

    def test_my_permissions_and_is_published_fields(self):
        set_permissions_for_obj_to_user(
            self.owner, self.conversation, [PermissionTypes.CRUD]
        )
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { myPermissions isPublished } }",
            self.owner,
        )
        self.assertIsNone(result.get("errors"))
        node = result["data"]["conversation"]
        self.assertIn("read_conversation", node["myPermissions"])
        self.assertIsInstance(node["isPublished"], bool)

    def test_object_shared_with_field_returns_empty_when_unshared(self):
        # No explicit per-user permission has been granted on self.conversation
        # (see setUp), so `conversationuserobjectpermission_set` is empty and
        # the resolver's loop body never executes.
        result = self._execute(
            "query($id: ID!) { conversation(id: $id) { objectSharedWith } }",
            self.owner,
        )
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["conversation"]["objectSharedWith"], [])

    def test_get_node_conversation_type_returns_none_for_null_pk(self):
        self.assertIsNone(ct._get_node_ConversationType(_Info(self.owner), None))


# --------------------------------------------------------------------------- #
# ConversationType connection fields
# --------------------------------------------------------------------------- #


class ConversationTypeConnectionFieldTests(TestCase):
    """Nested connection fields off ``conversation(id)`` — corpus action
    executions/results, moderation actions, notifications and research
    reports — none of which any existing test queries through
    ``ConversationType`` (only the top-level, independently-filtered
    ``moderationActions``/``conversations`` queries are covered elsewhere)."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="conn_owner", password="test", slug="conn-owner"
        )
        self.corpus = Corpus.objects.create(
            title="Connections Corpus", creator=self.owner, slug="connections-corpus"
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        self.conversation = Conversation.objects.create(
            title="Connections Thread",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.conversation, [PermissionTypes.CRUD]
        )
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.owner,
            content="kick off the action",
        )
        self.corpus_action = CorpusAction.objects.create(
            corpus=self.corpus,
            task_instructions="Summarize this thread",
            trigger=CorpusActionTrigger.NEW_MESSAGE,
            creator=self.owner,
        )
        self.gql_client = Client(schema)

    def _conversation(self, selection, user=None):
        result = self.gql_client.execute(
            "query($id: ID!) { conversation(id: $id) { %s } }" % selection,
            variables={"id": to_global_id("ConversationType", self.conversation.id)},
            context_value=_request(user or self.owner),
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        return result["data"]["conversation"]

    def test_corpus_action_executions_and_results_connections(self):
        completed_exec = CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            conversation=self.conversation,
            action_type=CorpusActionExecution.ActionType.AGENT,
            trigger=CorpusActionTrigger.NEW_THREAD,
            status=CorpusActionExecution.Status.COMPLETED,
            queued_at=timezone.now(),
            creator=self.owner,
        )
        CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            conversation=self.conversation,
            message=self.message,
            action_type=CorpusActionExecution.ActionType.AGENT,
            trigger=CorpusActionTrigger.NEW_MESSAGE,
            status=CorpusActionExecution.Status.RUNNING,
            queued_at=timezone.now(),
            creator=self.owner,
        )
        result_row = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            conversation=self.conversation,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.owner,
        )

        node = self._conversation("""
            corpusActionExecutions { edges { node { id status } } }
            filteredExecs: corpusActionExecutions(status: COMPLETED) {
                edges { node { id } }
            }
            corpusActionResults { edges { node { id status } } }
            """)
        exec_ids = {e["node"]["id"] for e in node["corpusActionExecutions"]["edges"]}
        self.assertEqual(len(exec_ids), 2)
        filtered_ids = {e["node"]["id"] for e in node["filteredExecs"]["edges"]}
        self.assertEqual(
            filtered_ids,
            {to_global_id("CorpusActionExecutionType", completed_exec.id)},
        )
        result_ids = {e["node"]["id"] for e in node["corpusActionResults"]["edges"]}
        self.assertEqual(
            result_ids, {to_global_id("AgentActionResultType", result_row.id)}
        )

    def test_moderation_actions_and_notifications_connections(self):
        moderation_action = ModerationAction.objects.create(
            conversation=self.conversation,
            action_type=ModerationActionTypeChoices.PIN_THREAD,
            moderator=None,
            creator=self.owner,
        )
        notification = Notification.objects.create(
            recipient=self.owner,
            notification_type=NotificationTypeChoices.THREAD_REPLY,
            conversation=self.conversation,
            message=self.message,
        )

        node = self._conversation("""
            moderationActions {
                edges { node { id isAutomated corpusId conversation { id } } }
            }
            notifications(notificationType: THREAD_REPLY) {
                edges { node { id } }
            }
            """)
        mod_edges = node["moderationActions"]["edges"]
        self.assertEqual(len(mod_edges), 1)
        mod_node = mod_edges[0]["node"]
        self.assertEqual(
            mod_node["id"],
            to_global_id("ModerationActionType", moderation_action.id),
        )
        self.assertTrue(mod_node["isAutomated"], "no moderator => automated")
        self.assertEqual(
            mod_node["corpusId"], to_global_id("CorpusType", self.corpus.id)
        )
        self.assertEqual(
            mod_node["conversation"]["id"],
            to_global_id("ConversationType", self.conversation.id),
        )

        notif_ids = {e["node"]["id"] for e in node["notifications"]["edges"]}
        self.assertIn(to_global_id("NotificationType", notification.id), notif_ids)

    def test_triggered_agent_action_results_and_research_reports_connections(self):
        triggered_result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            triggering_conversation=self.conversation,
            triggering_message=self.message,
            status=AgentActionResult.Status.FAILED,
            creator=self.owner,
        )
        report = ResearchReport.objects.create(
            corpus=self.corpus,
            prompt="Summarize contract risk factors",
            conversation=self.conversation,
            originating_message=self.message,
            status=JobStatus.COMPLETED.value,
            creator=self.owner,
        )

        node = self._conversation("""
            triggeredAgentActionResults(status: FAILED) {
                edges { node { id status } }
            }
            researchReports { edges { node { id status } } }
            """)
        triggered_ids = {
            e["node"]["id"] for e in node["triggeredAgentActionResults"]["edges"]
        }
        self.assertEqual(
            triggered_ids,
            {to_global_id("AgentActionResultType", triggered_result.id)},
        )
        report_ids = {e["node"]["id"] for e in node["researchReports"]["edges"]}
        self.assertEqual(report_ids, {to_global_id("ResearchReportType", report.id)})


# --------------------------------------------------------------------------- #
# MessageType scalar/permission fields
# --------------------------------------------------------------------------- #


class MessageTypeScalarFieldTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="msg_owner", password="test", slug="msg-owner"
        )
        self.corpus = Corpus.objects.create(
            title="Msg Field Corpus", creator=self.owner, slug="msg-field-corpus"
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        self.document = Document.objects.create(
            title="Msg Field Doc",
            creator=self.owner,
            slug="msg-field-doc",
            backend_lock=True,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )
        # is_public=True so the anonymous-user branch of userVote is
        # reachable: ChatMessage visibility for anonymous callers routes
        # entirely through Conversation.objects.visible_to_user (a private
        # THREAD hides its messages from anonymous before userVote ever
        # runs).
        self.conversation = Conversation.objects.create(
            title="Field Thread",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )
        # No explicit per-user permission grant on self.message here --
        # creator visibility is enough to fetch it, and it keeps
        # chatmessageuserobjectpermission_set empty for
        # test_object_shared_with_field_returns_empty_when_unshared.
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.owner,
            content="hello",
            source_document=self.document,
        )
        self.agent_config = AgentConfiguration.objects.create(
            name="Field Agent",
            slug="field-agent",
            system_instructions="Be helpful.",
            scope="GLOBAL",
            is_active=True,
            creator=self.owner,
        )
        self.gql_client = Client(schema)

    def _message(self, selection, message=None, user=None):
        result = self.gql_client.execute(
            "query($id: ID!) { chatMessage(id: $id) { %s } }" % selection,
            variables={"id": to_global_id("MessageType", (message or self.message).id)},
            context_value=_request(user or self.owner),
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        return result["data"]["chatMessage"]

    def test_msg_type_helper_returns_none_when_blank(self):
        # ChatMessage.msg_type is required at the form level but Django
        # doesn't validate choices at the ORM level, so an empty value is
        # reachable. The GraphQL field itself is non-null, so this defensive
        # fallback is only observable by calling the pure helper directly.
        self.assertIsNone(ct._resolve_MessageType_msg_type(_Row(msg_type=""), None))

    def test_agent_type_field_truthy_and_falsy(self):
        llm_message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="LLM",
            agent_type="document_agent",
            creator=self.owner,
            content="agent reply",
        )
        node = self._message("agentType", message=llm_message)
        self.assertEqual(node["agentType"], "DOCUMENT_AGENT")

        # self.message has no agent_type set (HUMAN message).
        node = self._message("agentType")
        self.assertIsNone(node["agentType"])

    def test_agent_configuration_field_resolves(self):
        self.message.agent_configuration = self.agent_config
        self.message.save(update_fields=["agent_configuration"])
        node = self._message("agentConfiguration { id name }")
        self.assertEqual(node["agentConfiguration"]["name"], "Field Agent")

    def test_source_document_field_resolves_visible_fk(self):
        node = self._message("sourceDocument { id slug }")
        self.assertEqual(node["sourceDocument"]["slug"], self.document.slug)

    def test_state_field(self):
        node = self._message("state")
        self.assertEqual(node["state"], "COMPLETED")

    def test_user_vote_anonymous_returns_null(self):
        node = self._message("userVote", user=AnonymousUser())
        self.assertIsNone(node["userVote"])

    def test_my_permissions_and_is_published_fields(self):
        set_permissions_for_obj_to_user(
            self.owner, self.message, [PermissionTypes.CRUD]
        )
        node = self._message("myPermissions isPublished")
        self.assertIn("read_chatmessage", node["myPermissions"])
        self.assertIsInstance(node["isPublished"], bool)

    def test_object_shared_with_field_returns_empty_when_unshared(self):
        node = self._message("objectSharedWith")
        self.assertEqual(node["objectSharedWith"], [])

    def test_get_node_message_type_returns_none_for_null_pk(self):
        self.assertIsNone(ct._get_node_MessageType(_Info(self.owner), None))


# --------------------------------------------------------------------------- #
# MessageType connection fields
# --------------------------------------------------------------------------- #


class MessageTypeConnectionFieldTests(TestCase):
    """Nested connection fields off ``chatMessage(id)``."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="msg_conn_owner", password="test", slug="msg-conn-owner"
        )
        self.corpus = Corpus.objects.create(
            title="Msg Conn Corpus", creator=self.owner, slug="msg-conn-corpus"
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        original_doc = Document.objects.create(
            title="Msg Conn Doc",
            creator=self.owner,
            slug="msg-conn-doc-orig",
            backend_lock=True,
        )
        self.document, _, _ = self.corpus.add_document(
            document=original_doc, user=self.owner
        )
        self.conversation = Conversation.objects.create(
            title="Conn Thread",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
        )
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.owner,
            content="root message",
        )
        set_permissions_for_obj_to_user(
            self.owner, self.message, [PermissionTypes.CRUD]
        )
        self.corpus_action = CorpusAction.objects.create(
            corpus=self.corpus,
            task_instructions="Do something useful",
            trigger=CorpusActionTrigger.NEW_MESSAGE,
            creator=self.owner,
        )
        self.gql_client = Client(schema)

    def _message(self, selection):
        result = self.gql_client.execute(
            "query($id: ID!) { chatMessage(id: $id) { %s } }" % selection,
            variables={"id": to_global_id("MessageType", self.message.id)},
            context_value=_request(self.owner),
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        return result["data"]["chatMessage"]

    def test_annotation_and_agent_mention_connections(self):
        indemnity_annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            raw_text="Indemnification clause text",
            page=1,
        )
        other_annotation = Annotation.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            raw_text="Unrelated other text",
            page=1,
        )
        self.message.source_annotations.add(indemnity_annotation, other_annotation)
        self.message.created_annotations.add(other_annotation)

        agent = AgentConfiguration.objects.create(
            name="Mentioned Agent",
            slug="mentioned-agent",
            system_instructions="Help.",
            scope="GLOBAL",
            is_active=True,
            creator=self.owner,
        )
        self.message.mentioned_agents.add(agent)

        node = self._message("""
            sourceAnnotations(rawText_Contains: "Indemn") {
                edges { node { id } }
            }
            createdAnnotations { edges { node { id } } }
            mentionedAgents(isActive: true) { edges { node { id slug } } }
            """)
        source_ids = {e["node"]["id"] for e in node["sourceAnnotations"]["edges"]}
        self.assertEqual(
            source_ids, {to_global_id("AnnotationType", indemnity_annotation.id)}
        )
        created_ids = {e["node"]["id"] for e in node["createdAnnotations"]["edges"]}
        self.assertEqual(
            created_ids, {to_global_id("AnnotationType", other_annotation.id)}
        )
        agent_slugs = {e["node"]["slug"] for e in node["mentionedAgents"]["edges"]}
        self.assertEqual(agent_slugs, {"mentioned-agent"})

    def test_corpus_action_executions_and_replies_connections(self):
        execution = CorpusActionExecution.objects.create(
            corpus_action=self.corpus_action,
            corpus=self.corpus,
            message=self.message,
            action_type=CorpusActionExecution.ActionType.AGENT,
            trigger=CorpusActionTrigger.NEW_MESSAGE,
            status=CorpusActionExecution.Status.RUNNING,
            queued_at=timezone.now(),
            creator=self.owner,
        )
        reply = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.owner,
            parent_message=self.message,
            content="a reply",
        )

        node = self._message("""
            corpusActionExecutions { edges { node { id } } }
            replies { edges { node { id } } }
            """)
        exec_ids = {e["node"]["id"] for e in node["corpusActionExecutions"]["edges"]}
        self.assertEqual(
            exec_ids, {to_global_id("CorpusActionExecutionType", execution.id)}
        )
        reply_ids = {e["node"]["id"] for e in node["replies"]["edges"]}
        self.assertEqual(reply_ids, {to_global_id("MessageType", reply.id)})

    def test_moderation_actions_and_notifications_connections(self):
        # Message-level moderation action with no linked conversation:
        # ModerationActionType.corpusId must fall back to null.
        moderation_action = ModerationAction.objects.create(
            message=self.message,
            action_type=ModerationActionTypeChoices.DELETE_MESSAGE,
            moderator=self.owner,
            creator=self.owner,
        )
        notification = Notification.objects.create(
            recipient=self.owner,
            notification_type=NotificationTypeChoices.MESSAGE_DELETED,
            message=self.message,
        )

        node = self._message("""
            moderationActions { edges { node { id isAutomated corpusId } } }
            notifications(notificationType: MESSAGE_DELETED) {
                edges { node { id } }
            }
            """)
        mod_edges = node["moderationActions"]["edges"]
        self.assertEqual(len(mod_edges), 1)
        mod_node = mod_edges[0]["node"]
        self.assertEqual(
            mod_node["id"],
            to_global_id("ModerationActionType", moderation_action.id),
        )
        self.assertFalse(mod_node["isAutomated"], "moderator is set")
        self.assertIsNone(mod_node["corpusId"], "no conversation linked")

        notif_ids = {e["node"]["id"] for e in node["notifications"]["edges"]}
        self.assertIn(to_global_id("NotificationType", notification.id), notif_ids)

    def test_triggered_agent_action_results_and_research_reports_connections(self):
        triggered_result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            triggering_conversation=self.conversation,
            triggering_message=self.message,
            status=AgentActionResult.Status.COMPLETED,
            creator=self.owner,
        )
        report = ResearchReport.objects.create(
            corpus=self.corpus,
            prompt="Deep dive on indemnification",
            conversation=self.conversation,
            originating_message=self.message,
            status=JobStatus.COMPLETED.value,
            creator=self.owner,
        )

        node = self._message("""
            triggeredAgentActionResults { edges { node { id } } }
            triggeredResearchReports { edges { node { id } } }
            """)
        triggered_ids = {
            e["node"]["id"] for e in node["triggeredAgentActionResults"]["edges"]
        }
        self.assertEqual(
            triggered_ids,
            {to_global_id("AgentActionResultType", triggered_result.id)},
        )
        report_ids = {
            e["node"]["id"] for e in node["triggeredResearchReports"]["edges"]
        }
        self.assertEqual(report_ids, {to_global_id("ResearchReportType", report.id)})
