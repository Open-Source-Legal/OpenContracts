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


def _make_noop_relay(agent: AgentConfiguration, pin: bool):
    """Build a no-op ``StreamRelay`` for tests that don't exercise relay paths.

    Mirrors the production ``relay_factory`` signature (must always return a
    relay — never ``None``). Use in tests that only verify tool metadata or
    that mock the sub-agent stream to raise before any forwarders run.
    """
    from opencontractserver.llms.tools.delegation_tools import StreamRelay

    async def _on_token(_t: str) -> None:
        return None

    async def _on_thought(_t: str, _md: dict) -> None:
        return None

    async def _on_approval(_p: dict):
        return None

    async def _on_finish(_t: str):
        return None

    return StreamRelay(
        agent=agent,
        pin=pin,
        on_token=_on_token,
        on_thought=_on_thought,
        on_approval=_on_approval,
        on_finish=_on_finish,
    )


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
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=None,
            document=None,
        )
        self.assertIsInstance(tool, CoreTool)
        self.assertEqual(tool.name, "delegate_to_research_bot")

    def test_tool_description_is_agent_description(self):
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=None,
            document=None,
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
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=None,
            document=None,
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
            agent=agent,
            pin=False,
            on_token=noop,
            on_thought=noop_thought,
            on_approval=noop_approval,
            on_finish=noop_finish,
        )
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
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
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
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
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
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
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

    async def test_body_returns_cycle_limit_error_when_exhausted(self):
        """A sub-agent that perpetually emits ApprovalNeededEvent must
        eventually be aborted with an explicit cycle-limit error string
        rather than silently returning partial accumulated content.
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            MAX_DELEGATION_APPROVAL_CYCLES,
            StreamRelay,
            build_delegation_tool,
        )

        # Relay that auto-approves every approval — so the sub-agent's
        # never-ending approval requests just keep cycling.
        approvals_seen: list[int] = []

        async def on_approval(_):
            approvals_seen.append(1)
            return {"approved": True, "llm_message_id": None}

        async def noop_token(_):
            return None

        async def noop_thought(_t, _md):
            return None

        async def noop_finish(_):
            return None

        relay = StreamRelay(
            agent=self.agent,
            pin=False,
            on_token=noop_token,
            on_thought=noop_thought,
            on_approval=on_approval,
            on_finish=noop_finish,
        )

        # An async generator factory that always yields an approval_needed
        # event and never settles — both ``stream(...)`` and
        # ``resume_with_approval(...)`` return a fresh one of these so the
        # tool body cycles forever (until the bound trips).
        def _approval_event():
            return _make_stub_event(
                type="approval_needed",
                content="",
                accumulated_content="",
                pending_tool_call={"name": "x", "arguments": {}},
                llm_message_id=42,
            )

        class _LoopingAgent:
            def __init__(self):
                self.resume_calls = 0

            def stream(self, prompt):
                async def _gen():
                    yield _approval_event()

                return _gen()

            def resume_with_approval(self, msg_id, approved, stream=True):
                self.resume_calls += 1

                async def _gen():
                    yield _approval_event()

                return _gen()

        looping = _LoopingAgent()

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = looping
            result = await tool.function(prompt="please", pin=False)

        # The tool must have surfaced the explicit cycle-limit error string.
        self.assertIn(
            f"cycle limit ({MAX_DELEGATION_APPROVAL_CYCLES})", result["result"]
        )
        self.assertIn("aborting delegation", result["result"])
        self.assertIsNone(result["pinned_message_id"])
        # We must have stopped at exactly the bound — no more, no fewer.
        self.assertEqual(looping.resume_calls, MAX_DELEGATION_APPROVAL_CYCLES)

    async def test_body_uses_for_document_when_document_provided(self):
        """When a document is passed, the body must call agents_api.for_document.

        The factory call is the branch that wires the sub-agent up to the
        document context — verifying we hit ``for_document`` (and not
        ``for_corpus``) when the chat is doc-scoped exercises a different
        branch than every other body test.
        """
        from asgiref.sync import sync_to_async

        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        doc = await sync_to_async(Document.objects.create)(
            title="DocForBody", creator=self.user
        )
        # Without a DocumentPath the body still has a document context to
        # pass to ``for_document`` — the visibility check just walks the
        # creator's perms.
        events = [
            _make_stub_event(type="final", content="ok", accumulated_content="ok"),
        ]
        fake = _FakeSubAgent(events)

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=None,
            document=doc,
        )

        with patch.object(
            agents_api, "for_document", new_callable=AsyncMock
        ) as mock_for_document, patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_for_corpus:
            mock_for_document.return_value = fake
            result = await tool.function(prompt="hi", pin=False)

        mock_for_document.assert_awaited_once()
        mock_for_corpus.assert_not_called()
        self.assertEqual(result["result"], "ok")
        # for_document received the document and the (None) corpus
        call_kwargs = mock_for_document.call_args.kwargs
        self.assertIs(call_kwargs.get("document"), doc)
        self.assertIsNone(call_kwargs.get("corpus"))

    async def test_body_returns_error_when_no_doc_or_corpus_context(self):
        """If both corpus and document are None at tool-build time, the body
        must report back to the LLM rather than crash the turn.
        """
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=None,
            document=None,
        )

        result = await tool.function(prompt="hello", pin=False)
        self.assertIn("no document or corpus", result["result"].lower())
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_returns_error_when_agent_no_longer_visible(self):
        """Agent deactivated between tool build and invocation → fail soft."""
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )
        # Make the agent invisible — flip ``is_active`` so the
        # ``filter(pk=..., is_active=True)`` race guard fails.
        self.agent.is_active = False
        await self.agent.asave()

        result = await tool.function(prompt="hi", pin=False)
        self.assertIn("no longer available", result["result"].lower())
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_returns_error_when_document_no_longer_accessible(self):
        """Document permission revoked mid-turn → fail soft with explicit msg."""
        from asgiref.sync import sync_to_async

        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        # A document the user can see at build time, but we'll patch the
        # visible_to_user manager method to return an empty queryset to
        # simulate revocation rather than juggle guardian perms here.
        doc = await sync_to_async(Document.objects.create)(
            title="LosingAccess", creator=self.user
        )
        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=None,
            document=doc,
        )

        from opencontractserver.documents.models import Document as _Document

        original_manager = _Document.objects
        empty_qs = _Document.objects.none()
        with patch.object(_Document, "objects", wraps=original_manager) as mock_objects:
            mock_objects.visible_to_user.return_value = empty_qs
            result = await tool.function(prompt="hi", pin=False)

        self.assertIn("no longer accessible", result["result"].lower())
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_returns_error_when_corpus_no_longer_accessible(self):
        """Corpus permission revoked mid-turn → fail soft with explicit msg."""
        from opencontractserver.corpuses.models import Corpus as _Corpus
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        original_manager = _Corpus.objects
        empty_qs = _Corpus.objects.none()
        with patch.object(_Corpus, "objects", wraps=original_manager) as mock_objects:
            mock_objects.visible_to_user.return_value = empty_qs
            result = await tool.function(prompt="hi", pin=False)

        self.assertIn("no longer accessible", result["result"].lower())
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_returns_error_string_when_factory_raises_operationally(self):
        """Sub-agent factory blowing up (operationally) should NOT crash the
        turn; it must surface the failure as an error string to the LLM.
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.side_effect = RuntimeError("factory exploded")
            result = await tool.function(prompt="hi", pin=False)

        self.assertIn("factory exploded", result["result"])
        self.assertIn("body-bot", result["result"])
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_propagates_permission_error_from_factory(self):
        """PermissionError raised by the factory must propagate, not be
        swallowed — security exceptions short-circuit the body.
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            build_delegation_tool,
        )

        tool = build_delegation_tool(
            self.agent,
            relay_factory=_make_noop_relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.side_effect = PermissionError("nope")
            with self.assertRaises(PermissionError):
                await tool.function(prompt="hi", pin=False)

    async def test_body_forwards_thought_events_to_relay(self):
        """Thought events from the sub-agent must flow through relay.on_thought."""
        from opencontractserver.llms.tools.delegation_tools import StreamRelay

        thoughts: list[tuple[str, dict]] = []

        async def on_token(_):
            return None

        async def on_thought(text, md):
            thoughts.append((text, md))

        async def on_approval(_):
            return None

        async def on_finish(_):
            return None

        relay = StreamRelay(
            agent=self.agent,
            pin=False,
            on_token=on_token,
            on_thought=on_thought,
            on_approval=on_approval,
            on_finish=on_finish,
        )

        events = [
            _make_stub_event(
                type="thought",
                content="",
                thought="thinking hard",
                metadata={"step": 1},
            ),
            _make_stub_event(type="final", content="done", accumulated_content="done"),
        ]
        result, _, _ = await self._build_tool_and_invoke(
            events=events, pin=False, relay=relay
        )

        self.assertEqual(result["result"], "done")
        # At least one thought entry whose text starts with "thinking" and
        # whose metadata carries our step marker.  (When pin=True the body
        # also prepends its own "Delegating to ..." announcement; pin=False
        # skips that, so thoughts here is exactly the sub-agent's stream.)
        matched = [t for t in thoughts if t[0] == "thinking hard"]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0][1].get("step"), 1)

    async def test_body_returns_error_on_sub_agent_error_event(self):
        """An ``error`` event aborts the stream with an explicit error string."""
        events = [
            _make_stub_event(
                type="content", content="partial-", accumulated_content="partial-"
            ),
            _make_stub_event(type="error", content="", error="boom from sub-agent"),
        ]
        result, _, _ = await self._build_tool_and_invoke(events=events, pin=False)

        self.assertIn("boom from sub-agent", result["result"])
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_uses_final_accumulated_content_when_no_content_deltas(self):
        """Non-streaming path: only a ``final`` event with ``accumulated_content``
        — the body must use that as the result text instead of returning empty.
        """
        events = [
            _make_stub_event(
                type="final",
                content="",
                accumulated_content="complete answer from non-streaming run",
            ),
        ]
        result, _, _ = await self._build_tool_and_invoke(events=events, pin=False)
        self.assertEqual(result["result"], "complete answer from non-streaming run")

    async def test_body_swallows_on_finish_errors_but_returns_text(self):
        """If relay.on_finish raises an operational exception when pin=True,
        the body must still return the accumulated text — just with
        ``pinned_message_id=None`` — instead of crashing the conductor turn.
        """
        from opencontractserver.llms.tools.delegation_tools import StreamRelay

        async def on_token(_):
            return None

        async def on_thought(_t, _md):
            return None

        async def on_approval(_):
            return None

        async def on_finish(_):
            raise RuntimeError("persist failed")

        relay = StreamRelay(
            agent=self.agent,
            pin=True,
            on_token=on_token,
            on_thought=on_thought,
            on_approval=on_approval,
            on_finish=on_finish,
        )

        events = [
            _make_stub_event(
                type="content", content="hello", accumulated_content="hello"
            ),
            _make_stub_event(type="final", content="", accumulated_content="hello"),
        ]
        result, _, _ = await self._build_tool_and_invoke(
            events=events, pin=True, relay=relay
        )

        self.assertEqual(result["result"], "hello")
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_handles_non_dict_approval_decision(self):
        """A relay returning a non-dict decision (e.g. None) must be coerced
        into a denial, NOT propagated as an unstructured object — and the
        resulting resume cycle must complete cleanly with the recorded
        accumulated text.
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            StreamRelay,
            build_delegation_tool,
        )

        async def on_approval(_):
            # Non-dict decision: body must coerce to denial.
            return None

        async def noop(_):
            return None

        async def noop_thought(_t, _md):
            return None

        async def noop_finish(_):
            return None

        relay = StreamRelay(
            agent=self.agent,
            pin=False,
            on_token=noop,
            on_thought=noop_thought,
            on_approval=on_approval,
            on_finish=noop_finish,
        )

        approval_event = _make_stub_event(
            type="approval_needed",
            content="",
            pending_tool_call={"name": "x", "arguments": {}},
            llm_message_id=99,
        )

        class _ApprovalThenFinalAgent:
            def __init__(self):
                self.resume_calls = 0

            def stream(self, prompt):
                async def _gen():
                    yield approval_event

                return _gen()

            def resume_with_approval(self, msg_id, approved, stream=True):
                self.resume_calls += 1

                # On resume, emit a final result.
                async def _gen():
                    yield _make_stub_event(
                        type="final",
                        content="",
                        accumulated_content="post-denial answer",
                    )

                return _gen()

        agent_impl = _ApprovalThenFinalAgent()
        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = agent_impl
            result = await tool.function(prompt="please", pin=False)

        # Coerced to denial → resume continues with approved=False → final
        # event drives the accumulated text.
        self.assertEqual(agent_impl.resume_calls, 1)
        self.assertEqual(result["result"], "post-denial answer")

    async def test_body_returns_error_when_resume_yields_error_event(self):
        """The first stream yields ``approval_needed``; resume yields ``error``.

        Exercises the ``decision.get('_error')`` branch *inside* the resume
        loop (different code path than the pre-loop check).
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            StreamRelay,
            build_delegation_tool,
        )

        async def on_approval(_):
            return {"approved": True, "llm_message_id": 7}

        async def noop(_):
            return None

        async def noop_thought(_t, _md):
            return None

        async def noop_finish(_):
            return None

        relay = StreamRelay(
            agent=self.agent,
            pin=False,
            on_token=noop,
            on_thought=noop_thought,
            on_approval=on_approval,
            on_finish=noop_finish,
        )

        approval_event = _make_stub_event(
            type="approval_needed",
            content="",
            pending_tool_call={"name": "x", "arguments": {}},
            llm_message_id=7,
        )

        class _ApprovalThenErrorAgent:
            def stream(self, prompt):
                async def _gen():
                    yield approval_event

                return _gen()

            def resume_with_approval(self, msg_id, approved, stream=True):
                async def _gen():
                    yield _make_stub_event(
                        type="error", content="", error="resume blew up"
                    )

                return _gen()

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = _ApprovalThenErrorAgent()
            result = await tool.function(prompt="please", pin=False)

        self.assertIn("resume blew up", result["result"])
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_returns_error_when_resume_with_approval_raises(self):
        """If ``resume_with_approval`` itself raises (not just yields error),
        the body must catch and surface as an error string.
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            StreamRelay,
            build_delegation_tool,
        )

        async def on_approval(_):
            return {"approved": True, "llm_message_id": 11}

        async def noop(_):
            return None

        async def noop_thought(_t, _md):
            return None

        async def noop_finish(_):
            return None

        relay = StreamRelay(
            agent=self.agent,
            pin=False,
            on_token=noop,
            on_thought=noop_thought,
            on_approval=on_approval,
            on_finish=noop_finish,
        )

        approval_event = _make_stub_event(
            type="approval_needed",
            content="",
            pending_tool_call={"name": "x", "arguments": {}},
            llm_message_id=11,
        )

        class _ApprovalThenRaiseOnResume:
            def stream(self, prompt):
                async def _gen():
                    yield approval_event

                return _gen()

            def resume_with_approval(self, msg_id, approved, stream=True):
                raise RuntimeError("resume kaput")

        tool = build_delegation_tool(
            self.agent,
            relay_factory=lambda a, p: relay,
            user=self.user,
            corpus=self.corpus,
            document=None,
        )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = _ApprovalThenRaiseOnResume()
            result = await tool.function(prompt="please", pin=False)

        self.assertIn("resume kaput", result["result"])
        self.assertIsNone(result["pinned_message_id"])

    async def test_body_returns_error_when_msg_id_missing_during_resume(self):
        """Approval cycle with no sub-agent message id must NOT silently
        fall through to ``on_finish`` and ship partial accumulated text
        as success — it must return an explicit error string to the
        conductor so the LLM sees a real failure instead of a garbled
        ``result`` payload.
        """
        from opencontractserver.llms import agents as agents_api
        from opencontractserver.llms.tools.delegation_tools import (
            StreamRelay,
            build_delegation_tool,
        )

        # Relay that auto-approves but, critically, returns
        # ``llm_message_id=None`` so ``_sub_agent_msg_id`` resolves to
        # ``None`` in the resume loop.
        async def on_approval(_):
            return {"approved": True, "llm_message_id": None}

        async def noop_token(_):
            return None

        async def noop_thought(_t, _md):
            return None

        async def noop_finish(_):
            return None

        relay = StreamRelay(
            agent=self.agent,
            pin=False,
            on_token=noop_token,
            on_thought=noop_thought,
            on_approval=on_approval,
            on_finish=noop_finish,
        )

        # First-pass stream yields some accumulated content then an
        # approval_needed event — but the event itself has no
        # ``llm_message_id`` so the resume cycle has nothing to resume
        # against.  The body must abort with an explicit error.
        def _content_event(text: str):
            return _make_stub_event(
                type="content",
                content=text,
                accumulated_content=text,
            )

        def _approval_event_without_msg_id():
            return _make_stub_event(
                type="approval_needed",
                content="",
                accumulated_content="",
                pending_tool_call={"name": "x", "arguments": {}},
                # No llm_message_id field — getattr falls back to ``None``.
            )

        class _NoMsgIdAgent:
            def stream(self, prompt):
                async def _gen():
                    yield _content_event("partial-")
                    yield _content_event("text")
                    yield _approval_event_without_msg_id()

                return _gen()

            def resume_with_approval(self, msg_id, approved, stream=True):
                raise AssertionError(
                    "resume_with_approval must NOT be called when "
                    "msg_id is None — body must abort first."
                )

        with patch.object(
            agents_api, "for_corpus", new_callable=AsyncMock
        ) as mock_factory:
            mock_factory.return_value = _NoMsgIdAgent()
            tool = build_delegation_tool(
                self.agent,
                relay_factory=lambda a, p: relay,
                user=self.user,
                corpus=self.corpus,
                document=None,
            )
            result = await tool.function(prompt="please", pin=False)

        # Must surface a real failure, not a silent partial accumulation.
        self.assertNotEqual(result["result"], "partial-text")
        self.assertIn("could not be resumed", result["result"])
        self.assertIn("approval cycle", result["result"])
        self.assertIsNone(result["pinned_message_id"])
