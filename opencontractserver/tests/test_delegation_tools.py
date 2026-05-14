"""Unit tests for the delegation tool factory."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.tool_factory import CoreTool

User = get_user_model()


class FilterByScopeTests(TestCase):
    """Tests for ``filter_by_scope`` chat-scope filtering of agent querysets."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="u", password="x", email="u@example.com"
        )
        self.corpus_a = Corpus.objects.create(title="A", creator=self.user)
        self.corpus_b = Corpus.objects.create(title="B", creator=self.user)

        # Document `doc_in_a` lives in corpus_a via DocumentPath (the actual
        # Document <-> Corpus relation in this codebase — there is no FK or
        # M2M directly on Document).
        self.doc_in_a = Document.objects.create(title="D", creator=self.user)
        DocumentPath.objects.create(
            document=self.doc_in_a,
            corpus=self.corpus_a,
            path="/d.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        self.global_agent = AgentConfiguration.objects.create(
            name="Global",
            slug="global-bot",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="g",
        )
        self.corpus_a_agent = AgentConfiguration.objects.create(
            name="A Bot",
            slug="a-bot",
            scope="CORPUS",
            corpus=self.corpus_a,
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a",
        )
        self.corpus_b_agent = AgentConfiguration.objects.create(
            name="B Bot",
            slug="b-bot",
            scope="CORPUS",
            corpus=self.corpus_b,
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="b",
        )

    def test_standalone_doc_chat_yields_global_only(self):
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=None, document_id=None))
        slugs = {a.slug for a in result}
        self.assertIn("global-bot", slugs)
        self.assertNotIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)

    def test_corpus_chat_yields_global_plus_that_corpus(self):
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=self.corpus_a.id, document_id=None))
        slugs = {a.slug for a in result}
        self.assertIn("global-bot", slugs)
        self.assertIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)

    def test_doc_in_corpus_chat_yields_global_plus_that_corpus(self):
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=None, document_id=self.doc_in_a.id))
        slugs = {a.slug for a in result}
        self.assertIn("global-bot", slugs)
        self.assertIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)

    def test_doc_without_corpus_yields_global_only(self):
        # Standalone doc — not in any corpus (no DocumentPath).
        standalone = Document.objects.create(title="standalone", creator=self.user)
        from opencontractserver.llms.tools.delegation_tools import filter_by_scope

        qs = AgentConfiguration.objects.all()
        result = list(filter_by_scope(qs, corpus_id=None, document_id=standalone.id))
        slugs = {a.slug for a in result}
        # Only assert behaviour for agents we created in setUp: corpus-scoped
        # agents must NOT appear, but the global one must. Other test-DB
        # fixtures (e.g. seeded defaults) are tolerated as long as they're
        # not corpus-scoped to A or B.
        self.assertIn("global-bot", slugs)
        self.assertNotIn("a-bot", slugs)
        self.assertNotIn("b-bot", slugs)
        # No result should be a CORPUS-scoped agent.
        scopes = {a.scope for a in result}
        self.assertEqual(scopes - {"GLOBAL"}, set())


class BuildDelegationToolTests(TestCase):
    """Tests for the ``build_delegation_tool`` per-turn factory."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="u_builder", password="x", email="builder@example.com"
        )
        self.agent = AgentConfiguration.objects.create(
            name="Research Bot",
            slug="research-bot",
            description="Reads documents and summarizes them",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="research",
        )

    def test_tool_name_uses_snake_case_slug(self):
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda agent, pin: None,
            user=self.user,
            corpus=None,
            document=None,
            conversation=None,
        )
        self.assertIsInstance(tool, CoreTool)
        self.assertEqual(tool.name, "delegate_to_research_bot")

    def test_tool_description_is_agent_description(self):
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda agent, pin: None,
            user=self.user,
            corpus=None,
            document=None,
            conversation=None,
        )
        self.assertEqual(tool.description, "Reads documents and summarizes them")

    def test_tool_falls_back_to_default_description_when_agent_has_none(self):
        agent_no_desc = AgentConfiguration.objects.create(
            name="Bare",
            slug="bare-bot",
            description="",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="bare",
        )
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            agent_no_desc,
            relay_factory=lambda agent, pin: None,
            user=self.user,
            corpus=None,
            document=None,
            conversation=None,
        )
        # Falls back to a generic description mentioning the slug
        self.assertIn("bare-bot", tool.description.lower())


class StreamRelayTests(TestCase):
    """Tests for the ``StreamRelay`` dataclass shape."""

    def test_stream_relay_is_constructible_with_callables(self):
        from opencontractserver.llms.tools.delegation_tools import StreamRelay

        async def noop(_):
            return None

        async def noop_thought(_, __):
            return None

        async def noop_approval(_):
            return None

        async def noop_finish(_):
            return None

        user = User.objects.create_user(
            username="relay_user", password="x", email="r@x.com"
        )
        agent = AgentConfiguration.objects.create(
            name="X",
            slug="x-bot",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=user,
            system_instructions="x",
        )
        relay = StreamRelay(
            parent_message_id="msg-1",
            agent=agent,
            pin=False,
            on_token=noop,
            on_thought=noop_thought,
            on_approval=noop_approval,
            on_finish=noop_finish,
        )
        self.assertEqual(relay.parent_message_id, "msg-1")
        self.assertFalse(relay.pin)
        self.assertIs(relay.agent, agent)


# --------------------------------------------------------------------------- #
# Behavioural tests for the delegation tool ``_body``                          #
# --------------------------------------------------------------------------- #


def _make_stub_event(
    *, type: str, content: str = "", accumulated_content: str = "", **extra
) -> SimpleNamespace:
    """Build a minimal duck-typed stand-in for a stream event.

    The tool body only accesses ``type``, ``content``, ``accumulated_content``,
    ``thought``, ``metadata``, ``pending_tool_call`` and ``error`` via
    ``getattr``, so a ``SimpleNamespace`` suffices and avoids dragging the
    full event dataclass hierarchy (and its strict field signatures) into the
    test setup.
    """
    return SimpleNamespace(
        type=type,
        content=content,
        accumulated_content=accumulated_content,
        **extra,
    )


class _FakeSubAgent:
    """An async-iterable stand-in for a sub-agent.

    ``stream(prompt)`` returns an async generator yielding the events the test
    supplies, recording the prompt for assertion.
    """

    def __init__(self, events):
        self._events = events
        self.prompts_received: list[str] = []

    def stream(self, prompt: str):
        self.prompts_received.append(prompt)

        async def _gen():
            for e in self._events:
                yield e

        return _gen()


class BuildDelegationToolBodyTests(TransactionTestCase):
    """Exercise the actual ``_body`` coroutine returned by ``build_delegation_tool``.

    ``TransactionTestCase`` is used because the body issues async ORM calls via
    ``sync_to_async`` and we don't want the outer ``TestCase`` transaction
    blocking them.
    """

    serialized_rollback = False

    def setUp(self):
        self.user = User.objects.create_user(
            username="u_body",
            password="x",
            email="body@example.com",
        )
        self.corpus = Corpus.objects.create(title="C", creator=self.user)
        self.agent = AgentConfiguration.objects.create(
            name="Body Bot",
            slug="body-bot",
            description="Behavioural test agent",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="You are a careful sub-agent.",
        )

    async def _build_tool_and_invoke(
        self,
        *,
        events,
        pin: bool,
        relay=None,
        factory_target: str = "for_corpus",
    ):
        """Build the tool, patch the sub-agent factory, and call ``_body``."""
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        fake = _FakeSubAgent(events)

        def _relay_factory(agent_arg, pin_arg):
            return relay

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_relay_factory,
            user=self.user,
            corpus=self.corpus,
            document=None,
            conversation=None,
        )

        with patch.object(
            agents_api, factory_target, new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = fake
            result = await tool.function(prompt="hello sub-agent", pin=pin)
            return result, mock_factory, fake

    async def test_body_accumulates_content_no_pin(self):
        """pin=False: tool returns accumulated content and pinned_message_id=None."""
        events = [
            _make_stub_event(type="content", content="Hello "),
            _make_stub_event(type="content", content="world."),
            _make_stub_event(
                type="final",
                content="",
                accumulated_content="Hello world.",
            ),
        ]
        result, mock_factory, fake = await self._build_tool_and_invoke(
            events=events, pin=False
        )

        self.assertEqual(result, {"result": "Hello world.", "pinned_message_id": None})
        # Factory was called and got our prompt.
        mock_factory.assert_awaited_once()
        self.assertEqual(fake.prompts_received, ["hello sub-agent"])

    async def test_body_passes_persist_false_and_system_prompt(self):
        """Sub-agent factory MUST receive persist=False and system_prompt."""
        events = [
            _make_stub_event(type="final", content="ok", accumulated_content="ok"),
        ]
        _, mock_factory, _ = await self._build_tool_and_invoke(events=events, pin=False)

        mock_factory.assert_awaited_once()
        call_kwargs = mock_factory.call_args.kwargs
        self.assertIs(
            call_kwargs.get("persist"),
            False,
            "Sub-agent factory must be called with persist=False so the "
            "sub-agent does not write a parallel ChatMessage stream.",
        )
        self.assertEqual(
            call_kwargs.get("system_prompt"),
            "You are a careful sub-agent.",
            "Sub-agent factory must receive the agent's system_instructions "
            "via system_prompt so the configured AgentConfiguration is "
            "honoured.",
        )

    async def test_body_omits_system_prompt_when_instructions_blank(self):
        """If system_instructions is empty, we must NOT pass system_prompt."""
        self.agent.system_instructions = ""
        await self.agent.asave()
        events = [
            _make_stub_event(type="final", content="ok", accumulated_content="ok"),
        ]
        _, mock_factory, _ = await self._build_tool_and_invoke(events=events, pin=False)

        mock_factory.assert_awaited_once()
        call_kwargs = mock_factory.call_args.kwargs
        self.assertNotIn(
            "system_prompt",
            call_kwargs,
            "Empty system_instructions should not result in system_prompt=''; "
            "the kwarg should be omitted so the framework default applies.",
        )
        # persist=False is unconditional, though.
        self.assertIs(call_kwargs.get("persist"), False)

    async def test_body_pin_true_invokes_relay_callbacks(self):
        """pin=True: relay.on_token captures tokens and relay.on_finish gets final text."""
        from opencontractserver.llms.tools.delegation_tools import StreamRelay

        tokens: list[str] = []
        finishes: list[str] = []
        thoughts: list[tuple[str, dict]] = []

        async def on_token(t):
            tokens.append(t)

        async def on_thought(t, md):
            thoughts.append((t, md))

        async def on_approval(_):
            return None

        async def on_finish(final):
            finishes.append(final)
            return 4242  # pretend persisted message id

        relay = StreamRelay(
            parent_message_id="parent-msg-1",
            agent=self.agent,
            pin=True,
            on_token=on_token,
            on_thought=on_thought,
            on_approval=on_approval,
            on_finish=on_finish,
        )

        events = [
            _make_stub_event(type="content", content="alpha "),
            _make_stub_event(type="content", content="beta"),
            _make_stub_event(
                type="final", content="", accumulated_content="alpha beta"
            ),
        ]
        result, _, _ = await self._build_tool_and_invoke(
            events=events, pin=True, relay=relay
        )

        self.assertEqual(tokens, ["alpha ", "beta"])
        self.assertEqual(finishes, ["alpha beta"])
        self.assertEqual(result, {"result": "alpha beta", "pinned_message_id": 4242})
        # The body announces delegation start as a thought.
        self.assertEqual(len(thoughts), 1)
        thought_text, thought_md = thoughts[0]
        self.assertIn("body-bot", thought_text)
        self.assertEqual(thought_md.get("agent_slug"), "body-bot")

    async def test_body_propagates_tool_confirmation_required(self):
        """ToolConfirmationRequired must NOT be swallowed by the body."""
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: None,
            user=self.user,
            corpus=self.corpus,
            document=None,
            conversation=None,
        )

        # Make the streaming raise ToolConfirmationRequired mid-iteration.
        class _RaisingAgent:
            def stream(self, prompt):
                async def _gen():
                    if False:  # pragma: no cover - generator marker
                        yield None
                    raise ToolConfirmationRequired(
                        tool_name="needs_approval",
                        tool_args={"x": 1},
                        tool_call_id="abc",
                    )

                return _gen()

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = _RaisingAgent()
            with self.assertRaises(ToolConfirmationRequired):
                await tool.function(prompt="please", pin=False)

    async def test_body_propagates_permission_error(self):
        """PermissionError raised by sub-agent stream must propagate."""
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: None,
            user=self.user,
            corpus=self.corpus,
            document=None,
            conversation=None,
        )

        class _PermDeniedAgent:
            def stream(self, prompt):
                async def _gen():
                    if False:  # pragma: no cover
                        yield None
                    raise PermissionError("nope")

                return _gen()

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = _PermDeniedAgent()
            with self.assertRaises(PermissionError):
                await tool.function(prompt="please", pin=False)

    async def test_body_returns_error_string_for_operational_failure(self):
        """Non-security exceptions during streaming surface as an error string."""
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: None,
            user=self.user,
            corpus=self.corpus,
            document=None,
            conversation=None,
        )

        class _BoomAgent:
            def stream(self, prompt):
                async def _gen():
                    if False:  # pragma: no cover
                        yield None
                    raise RuntimeError("kaboom")

                return _gen()

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = _BoomAgent()
            result = await tool.function(prompt="please", pin=False)

        self.assertIn("kaboom", result["result"])
        self.assertIsNone(result["pinned_message_id"])
