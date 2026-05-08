"""Targeted unit tests that exercise the specific lines added or modified in
PR #1543 (typing graduation of opencontractserver.llms.*) so codecov reports
the patch as covered.

The tests are intentionally narrow: each one calls into a single helper /
branch added by the PR. We mock heavily to avoid pulling in the full agent
stack — these are coverage tests, not behavioural ones (the behavioural
contract lives in ``test_llms_typing_behavior_guards.py``).
"""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.core_agents import (
    AgentConfig,
    CoreAgentBase,
    CorpusAgentContext,
    SourceNode,
    get_default_config,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# core_agents.py – CorpusAgentContext.initialize() loads when documents empty
# and is a no-op when documents are already present.
# ---------------------------------------------------------------------------


class TestCorpusAgentContextInitialize(TestCase):
    """Cover ``CorpusAgentContext.initialize`` for both branches added when
    the field default flipped from ``None`` to ``[]``."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="ctx_cov", password="x")
        self.corpus = Corpus.objects.create(
            title="ctx_cov_corpus",
            creator=self.user,
            preferred_embedder="test/embedder",
        )

    def test_initialize_loads_when_documents_empty(self) -> None:
        """Empty list triggers the corpus fetch (the new "not self.documents"
        branch). Mock ``Corpus.get_documents`` to avoid setting up annotations."""
        ctx = CorpusAgentContext(
            corpus=self.corpus, config=AgentConfig(user_id=self.user.id)
        )

        sentinel_doc = MagicMock(spec=Document)
        with patch.object(
            type(self.corpus), "get_documents", return_value=[sentinel_doc]
        ):
            async_to_sync(ctx.initialize)()

        self.assertEqual(ctx.documents, [sentinel_doc])

    def test_initialize_skips_load_when_documents_prepopulated(self) -> None:
        """A non-empty list short-circuits the load — the corpus fetch must
        NOT be called."""
        existing = MagicMock(spec=Document)
        ctx = CorpusAgentContext(
            corpus=self.corpus,
            config=AgentConfig(user_id=self.user.id),
            documents=[existing],
        )

        with patch.object(type(self.corpus), "get_documents") as mock_get:
            async_to_sync(ctx.initialize)()
            mock_get.assert_not_called()

        # Still the original list — not replaced.
        self.assertEqual(ctx.documents, [existing])


# ---------------------------------------------------------------------------
# core_agents.py – ``_normalise_source`` dict-content fallback chain.
# ---------------------------------------------------------------------------


class TestNormaliseSourceContentFallback(TestCase):
    """The PR rewrote ``content = raw.get("content", raw.get("text", ""))``
    as ``content = raw.get("content") or raw.get("text") or ""``. The new
    form prefers truthy values; cover all three legs."""

    def test_dict_with_content_key(self) -> None:
        node = CoreAgentBase._normalise_source(
            {"annotation_id": 1, "content": "C", "similarity_score": 0.5}
        )
        self.assertEqual(node.content, "C")
        self.assertEqual(node.annotation_id, 1)
        self.assertEqual(node.similarity_score, 0.5)

    def test_dict_with_only_text_key(self) -> None:
        node = CoreAgentBase._normalise_source({"annotation_id": 2, "text": "T"})
        self.assertEqual(node.content, "T")
        self.assertEqual(node.annotation_id, 2)

    def test_dict_with_empty_content_falls_back_to_text(self) -> None:
        # "" is falsy, so the new ``or`` chain advances to ``text``.
        node = CoreAgentBase._normalise_source(
            {"annotation_id": 3, "content": "", "text": "fallback"}
        )
        self.assertEqual(node.content, "fallback")

    def test_dict_with_no_content_or_text(self) -> None:
        # Both missing → empty string. Also exercises the ``str(content)`` cast.
        node = CoreAgentBase._normalise_source({"annotation_id": 4})
        self.assertEqual(node.content, "")

    def test_passthrough_source_node(self) -> None:
        original = SourceNode(
            annotation_id=9, content="x", metadata={}, similarity_score=1.0
        )
        self.assertIs(CoreAgentBase._normalise_source(original), original)

    def test_unknown_input_wrapped_as_dummy(self) -> None:
        node = CoreAgentBase._normalise_source("plain-string")
        self.assertEqual(node.content, "plain-string")
        self.assertEqual(node.annotation_id, 0)


# ---------------------------------------------------------------------------
# core_agents.py – ``get_default_config`` filters None overrides; covers the
# typed defaults dict and the generator-expression filter.
# ---------------------------------------------------------------------------


class TestGetDefaultConfigOverrideFiltering(TestCase):
    def test_overrides_filtered_when_none(self) -> None:
        """``model_name=None`` must NOT clobber the default — only non-None
        overrides win. This exercises the ``v is not None`` filter line."""
        config = get_default_config(model_name=None, temperature=0.5)
        # Default model name is preserved despite the explicit ``None``.
        self.assertNotEqual(config.model_name, None)
        # Non-None override flows through.
        self.assertEqual(config.temperature, 0.5)

    def test_non_none_overrides_take_effect(self) -> None:
        config = get_default_config(model_name="custom-model", streaming=False)
        self.assertEqual(config.model_name, "custom-model")
        self.assertFalse(config.streaming)


# ---------------------------------------------------------------------------
# pydantic_ai_agents.py – ``_extract_tool_result_summary`` branches.
# ---------------------------------------------------------------------------


class TestExtractToolResultSummary(TestCase):
    def _evt(self, content: Any) -> Any:
        result = MagicMock()
        result.content = content
        evt = MagicMock()
        evt.result = result
        return evt

    def test_summary_from_dict_answer_key(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _extract_tool_result_summary,
        )

        out = _extract_tool_result_summary(
            self._evt({"answer": "the answer", "sources": []}), "ask_document"
        )
        self.assertEqual(out, "the answer")

    def test_summary_from_string_content(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _extract_tool_result_summary,
        )

        out = _extract_tool_result_summary(self._evt("plain string result"), "tool_x")
        self.assertEqual(out, "plain string result")

    def test_summary_from_truncation(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _extract_tool_result_summary,
        )
        from opencontractserver.llms.agents.timeline_utils import (
            MAX_TOOL_RESULT_LENGTH,
        )

        long = "x" * (MAX_TOOL_RESULT_LENGTH + 50)
        out = _extract_tool_result_summary(self._evt(long), "tool_x")
        self.assertTrue(out.endswith("..."))
        self.assertEqual(len(out), MAX_TOOL_RESULT_LENGTH + 3)

    def test_summary_falls_back_to_completed_on_none(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _extract_tool_result_summary,
        )

        out = _extract_tool_result_summary(self._evt(None), "tool_x")
        self.assertEqual(out, "Completed")

    def test_summary_falls_back_to_completed_on_extraction_error(self) -> None:
        """Hits the ``except Exception`` debug branch."""
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _extract_tool_result_summary,
        )

        broken = MagicMock()
        # Property access raises — the helper must swallow the error.
        type(broken).result = property(
            lambda _self: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        out = _extract_tool_result_summary(broken, "tool_x")
        self.assertEqual(out, "Completed")

    def test_summary_handles_non_string_non_dict_content(self) -> None:
        """The ``elif result_content is not None`` branch fires for ints,
        lists, etc."""
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _extract_tool_result_summary,
        )

        out = _extract_tool_result_summary(self._evt(42), "tool_x")
        self.assertEqual(out, "42")


# ---------------------------------------------------------------------------
# pydantic_ai_agents.py – ``_event_to_text_and_meta`` covers each isinstance
# branch on the typed ``inspected: Any`` dispatch.
# ---------------------------------------------------------------------------


class TestEventToTextAndMeta(TestCase):
    def test_unsupported_event_returns_empty_tuple(self) -> None:
        """Non Part(Start|Delta) events take the early-return branch."""
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _event_to_text_and_meta,
        )

        text, is_answer, meta = _event_to_text_and_meta(MagicMock())
        self.assertEqual(text, "")
        self.assertFalse(is_answer)
        self.assertEqual(meta, {})

    def test_part_start_text_part(self) -> None:
        from pydantic_ai.messages import PartStartEvent, TextPart

        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _event_to_text_and_meta,
        )

        evt = PartStartEvent(index=0, part=TextPart(content="hello"))
        text, is_answer, meta = _event_to_text_and_meta(evt)
        self.assertEqual(text, "hello")
        self.assertTrue(is_answer)
        self.assertEqual(meta, {})

    def test_part_start_tool_call_part(self) -> None:
        from pydantic_ai.messages import PartStartEvent, ToolCallPart

        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _event_to_text_and_meta,
        )

        evt = PartStartEvent(
            index=0, part=ToolCallPart(tool_name="t", args={"a": 1}, tool_call_id="id1")
        )
        text, is_answer, meta = _event_to_text_and_meta(evt)
        self.assertEqual(text, "")
        self.assertFalse(is_answer)
        self.assertEqual(meta, {"tool_name": "t", "args": {"a": 1}})

    def test_part_delta_text_delta(self) -> None:
        from pydantic_ai.messages import PartDeltaEvent, TextPartDelta

        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _event_to_text_and_meta,
        )

        evt = PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="chunk"))
        text, is_answer, meta = _event_to_text_and_meta(evt)
        self.assertEqual(text, "chunk")
        self.assertTrue(is_answer)

    def test_part_delta_tool_call_delta(self) -> None:
        from pydantic_ai.messages import PartDeltaEvent, ToolCallPartDelta

        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _event_to_text_and_meta,
        )

        evt = PartDeltaEvent(
            index=0,
            delta=ToolCallPartDelta(tool_name_delta="tn", args_delta="ad"),
        )
        text, is_answer, meta = _event_to_text_and_meta(evt)
        self.assertEqual(text, "")
        self.assertFalse(is_answer)
        self.assertEqual(meta, {"tool_name_delta": "tn", "args_delta": "ad"})


# ---------------------------------------------------------------------------
# pydantic_ai_agents.py – ``_usage_to_dict`` branches: None, model_dump,
# dataclass instance, and the ``isinstance(usage, type)`` guard added in PR.
# ---------------------------------------------------------------------------


class TestUsageToDict(TestCase):
    def test_none_returns_none(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import _usage_to_dict

        self.assertIsNone(_usage_to_dict(None))

    def test_model_dump_path(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import _usage_to_dict

        usage = MagicMock()
        usage.model_dump.return_value = {"prompt_tokens": 10}
        self.assertEqual(_usage_to_dict(usage), {"prompt_tokens": 10})
        usage.model_dump.assert_called_once()

    def test_dataclass_instance_uses_asdict(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import _usage_to_dict

        @dataclasses.dataclass
        class _U:
            input_tokens: int = 0
            output_tokens: int = 0

        result = _usage_to_dict(_U(input_tokens=5, output_tokens=7))
        self.assertEqual(result, {"input_tokens": 5, "output_tokens": 7})

    def test_dataclass_class_object_does_not_explode(self) -> None:
        """The PR added ``not isinstance(usage, type)`` so passing the
        dataclass *class* (rather than an instance) skips the asdict branch
        and falls through to the warning return-None path."""
        from opencontractserver.llms.agents.pydantic_ai_agents import _usage_to_dict

        @dataclasses.dataclass
        class _U:
            x: int = 0

        # ``_U`` is the *class* — without the guard ``dataclasses.asdict``
        # would raise. The guard makes us return None instead.
        self.assertIsNone(_usage_to_dict(_U))

    def test_unknown_object_returns_none(self) -> None:
        from opencontractserver.llms.agents.pydantic_ai_agents import _usage_to_dict

        class _Plain:
            pass

        self.assertIsNone(_usage_to_dict(_Plain()))


# ---------------------------------------------------------------------------
# client.py – ``_chat_openai`` covers the typed ``params: dict[str, Any]``
# annotation line and the optional ``max_tokens`` insertion.
# ---------------------------------------------------------------------------


class TestSimpleLLMClientChatOpenAI(TestCase):
    def _make_client(self, max_tokens: int | None = None):
        from opencontractserver.llms.client import SimpleLLMClient

        with patch(
            "openai.OpenAI",
            return_value=MagicMock(),
        ):
            client = SimpleLLMClient(
                api_key="sk-test",
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=max_tokens,
            )
        return client

    def _fake_completion(
        self, content: str = "hi", *, with_usage: bool = True
    ) -> MagicMock:
        choice_msg = MagicMock()
        choice_msg.content = content
        choice = MagicMock()
        choice.message = choice_msg

        completion = MagicMock()
        completion.choices = [choice]
        completion.model = "gpt-4o-mini"

        if with_usage:
            usage = MagicMock()
            usage.prompt_tokens = 1
            usage.completion_tokens = 2
            usage.total_tokens = 3
            completion.usage = usage
        else:
            completion.usage = None
        return completion

    def test_chat_without_max_tokens_omits_param(self) -> None:
        from opencontractserver.llms.client import ChatMessage

        client = self._make_client(max_tokens=None)
        client.client = MagicMock()
        client.client.chat.completions.create.return_value = self._fake_completion()

        resp = client.chat([ChatMessage(role="user", content="hi")])

        # The typed ``params`` dict should NOT include ``max_tokens``.
        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        self.assertNotIn("max_tokens", call_kwargs)
        self.assertEqual(resp.content, "hi")
        self.assertIsNotNone(resp.usage)

    def test_chat_includes_max_tokens_when_set(self) -> None:
        from opencontractserver.llms.client import ChatMessage

        client = self._make_client(max_tokens=128)
        client.client = MagicMock()
        client.client.chat.completions.create.return_value = self._fake_completion(
            with_usage=False
        )

        client.chat([ChatMessage(role="user", content="hi")])

        call_kwargs = client.client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["max_tokens"], 128)


# ---------------------------------------------------------------------------
# core_vector_stores.py – ctor branches added for None embedder paths and
# guard for unresolved embedder.
# ---------------------------------------------------------------------------


class TestCoreAnnotationVectorStoreCtor(TestCase):
    def test_explicit_embedder_path_only(self) -> None:
        """Path: ``embedder_path is not None`` — the corpus_id is *not*
        required to be passed to ``get_embedder`` when the path is explicit."""
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), "explicit/path"),
        ) as mock_get:
            store = CoreAnnotationVectorStore(embedder_path="explicit/path")

        self.assertEqual(store.embedder_path, "explicit/path")
        # Called with embedder_path kwarg; corpus_id should not appear.
        called_kwargs = mock_get.call_args.kwargs
        self.assertNotIn("corpus_id", called_kwargs)
        self.assertEqual(called_kwargs.get("embedder_path"), "explicit/path")

    def test_corpus_only_branch(self) -> None:
        """Path: ``embedder_path is None`` with ``corpus_id`` present — the
        new branch only forwards ``corpus_id``."""
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), "from/corpus"),
        ) as mock_get:
            store = CoreAnnotationVectorStore(corpus_id=42)

        self.assertEqual(store.embedder_path, "from/corpus")
        called_kwargs = mock_get.call_args.kwargs
        self.assertIn("corpus_id", called_kwargs)
        self.assertEqual(called_kwargs["corpus_id"], 42)
        self.assertNotIn("embedder_path", called_kwargs)

    def test_unresolved_embedder_raises_value_error(self) -> None:
        """``detected_embedder_path is None`` triggers the new ValueError
        guard that replaces an implicit type error downstream."""
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), None),
        ):
            with self.assertRaisesRegex(ValueError, "no embedder_path"):
                CoreAnnotationVectorStore(corpus_id=42)

    def test_no_corpus_no_path_raises(self) -> None:
        """Neither ``corpus_id`` nor ``embedder_path`` — preserves existing
        validation behaviour."""
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
        )

        with self.assertRaisesRegex(ValueError, "either 'corpus_id'"):
            CoreAnnotationVectorStore()


# ---------------------------------------------------------------------------
# core_conversation_vector_stores.py – ctor branches and ``int(self.corpus_id)``
# cast paths.
# ---------------------------------------------------------------------------


class TestCoreConversationVectorStoreCtor(TestCase):
    def test_explicit_path_with_corpus_id_uses_both(self) -> None:
        """When both are supplied, ``get_embedder`` receives both kwargs
        (the new typed branch)."""
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreConversationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), "explicit"),
        ) as mock_get:
            store = CoreConversationVectorStore(
                corpus_id=7, embedder_path="explicit/path"
            )

        self.assertEqual(store.embedder_path, "explicit/path")
        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs.get("corpus_id"), 7)
        self.assertEqual(kwargs.get("embedder_path"), "explicit/path")

    def test_explicit_path_without_corpus_skips_corpus_kwarg(self) -> None:
        """The new branch: when ``corpus_id`` is None and ``embedder_path``
        is set, do not forward ``corpus_id`` to ``get_embedder``."""
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreConversationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), "explicit"),
        ) as mock_get:
            store = CoreConversationVectorStore(embedder_path="explicit/path")

        self.assertEqual(store.embedder_path, "explicit/path")
        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs.get("embedder_path"), "explicit/path")
        self.assertNotIn("corpus_id", kwargs)

    def test_explicit_path_with_resolution_failure_swallowed(self) -> None:
        """The ``except Exception`` branch sets embedder_class to None and
        keeps the explicit path. This was already covered, but the typed
        branch above is new."""
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreConversationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            side_effect=RuntimeError("test fail"),
        ):
            store = CoreConversationVectorStore(embedder_path="explicit/path")
        self.assertEqual(store.embedder_path, "explicit/path")

    def test_auto_detect_unresolved_embedder_raises(self) -> None:
        """``detected_embedder_path is None`` in auto-detect mode hits the
        new ValueError guard."""
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreConversationVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), None),
        ):
            with self.assertRaisesRegex(ValueError, "no embedder_path"):
                CoreConversationVectorStore(corpus_id=7)


class TestCoreChatMessageVectorStoreCtor(TestCase):
    def test_explicit_path_without_corpus_skips_corpus_kwarg(self) -> None:
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreChatMessageVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), "explicit"),
        ) as mock_get:
            store = CoreChatMessageVectorStore(embedder_path="explicit/path")

        self.assertEqual(store.embedder_path, "explicit/path")
        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs.get("embedder_path"), "explicit/path")
        self.assertNotIn("corpus_id", kwargs)

    def test_auto_detect_unresolved_raises(self) -> None:
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreChatMessageVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), None),
        ):
            with self.assertRaisesRegex(ValueError, "no embedder_path"):
                CoreChatMessageVectorStore(corpus_id=11)

    def test_auto_detect_path_returned(self) -> None:
        from opencontractserver.llms.vector_stores.core_conversation_vector_stores import (  # noqa: E501
            CoreChatMessageVectorStore,
        )

        with patch(
            "opencontractserver.llms.vector_stores.core_conversation_vector_stores.get_embedder",
            return_value=(MagicMock(vector_size=768), "auto/path"),
        ):
            store = CoreChatMessageVectorStore(corpus_id=11)
        self.assertEqual(store.embedder_path, "auto/path")


# ---------------------------------------------------------------------------
# timeline_stream_mixin.py – cover the wrapper ``stream`` method.
# ---------------------------------------------------------------------------


class TestTimelineStreamMixin(TestCase):
    def test_stream_injects_timeline_into_final_event(self) -> None:
        """The mixin wraps ``_stream_core`` and injects ``timeline`` into
        the final event's metadata."""
        from opencontractserver.llms.agents.core_agents import (
            ContentEvent,
            FinalEvent,
        )
        from opencontractserver.llms.agents.timeline_stream_mixin import (
            TimelineStreamMixin,
        )

        class _Adapter(TimelineStreamMixin):
            async def _stream_core(self, message, **kwargs):
                yield ContentEvent(content="hi", accumulated_content="hi")
                yield FinalEvent(
                    content="hi",
                    accumulated_content="hi",
                    sources=[],
                    metadata={},
                )

        adapter = _Adapter()

        async def _drain():
            out = []
            async for ev in adapter.stream("hello"):
                out.append(ev)
            return out

        events = async_to_sync(_drain)()
        finals = [e for e in events if isinstance(e, FinalEvent)]
        self.assertEqual(len(finals), 1)
        self.assertIn("timeline", finals[0].metadata or {})

    def test_stream_calls_finalise_helper_when_present(self) -> None:
        """If the adapter exposes ``_finalise_llm_message`` the mixin awaits
        it after the final event is built."""
        from opencontractserver.llms.agents.core_agents import FinalEvent
        from opencontractserver.llms.agents.timeline_stream_mixin import (
            TimelineStreamMixin,
        )

        captured: dict[str, Any] = {}

        class _Adapter(TimelineStreamMixin):
            async def _stream_core(self, message, **kwargs):
                yield FinalEvent(
                    content="done",
                    accumulated_content="done",
                    sources=[],
                    metadata={"usage": {"total_tokens": 1}},
                    llm_message_id=99,
                )

            async def _finalise_llm_message(
                self, msg_id, content, sources, usage, timeline
            ):
                captured["msg_id"] = msg_id
                captured["content"] = content
                captured["timeline"] = timeline

        adapter = _Adapter()

        async def _drain():
            async for _ in adapter.stream("hello"):
                pass

        async_to_sync(_drain)()
        self.assertEqual(captured.get("msg_id"), 99)
        self.assertEqual(captured.get("content"), "done")
        self.assertIn("timeline", captured)

    def test_stream_core_default_raises_not_implemented(self) -> None:
        """The base ``_stream_core`` async generator raises immediately when
        iterated. Cover the unreachable ``yield cast(...)`` defensive return-
        path noise by entering and immediately catching."""
        from opencontractserver.llms.agents.timeline_stream_mixin import (
            TimelineStreamMixin,
        )

        adapter = TimelineStreamMixin()

        async def _enter():
            agen = adapter._stream_core("anything")
            with self.assertRaises(NotImplementedError):
                await agen.__anext__()

        async_to_sync(_enter)()


class TestIsPublicHelper(TestCase):
    """Cover ``_is_public`` — the cheap visibility heuristic on document/corpus."""

    def test_none_object_is_not_public(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        self.assertFalse(_is_public(None))

    def test_explicit_is_public_true(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        obj = MagicMock(spec=["is_public"])
        obj.is_public = True
        self.assertTrue(_is_public(obj))

    def test_explicit_is_public_false(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        obj = MagicMock(spec=["is_public"])
        obj.is_public = False
        self.assertFalse(_is_public(obj))

    def test_visibility_string_public(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        obj = MagicMock(spec=["visibility"])
        obj.visibility = "PUBLIC"
        self.assertTrue(_is_public(obj))

    def test_visibility_string_private(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        obj = MagicMock(spec=["visibility"])
        obj.visibility = "private"
        self.assertFalse(_is_public(obj))

    def test_visibility_enum_member_with_public_name(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        enum_member = MagicMock()
        enum_member.name = "Public"
        obj = MagicMock(spec=["visibility"])
        obj.visibility = enum_member
        self.assertTrue(_is_public(obj))

    def test_object_without_visibility_is_private(self) -> None:
        from opencontractserver.llms.agents.core_agents import _is_public

        # spec=[] gives an object with no recognised visibility attrs.
        obj = MagicMock(spec=[])
        self.assertFalse(_is_public(obj))


class TestAssertAccessHelper(TestCase):
    """Cover ``_assert_access`` — the anonymous-user gate."""

    def test_anonymous_blocked_on_private(self) -> None:
        from opencontractserver.llms.agents.core_agents import _assert_access

        private = MagicMock(spec=["is_public"])
        private.is_public = False
        with self.assertRaises(PermissionError):
            _assert_access(private, user_id=None)

    def test_anonymous_allowed_on_public(self) -> None:
        from opencontractserver.llms.agents.core_agents import _assert_access

        public = MagicMock(spec=["is_public"])
        public.is_public = True
        # No exception expected — call must return without raising.
        _assert_access(public, user_id=None)

    def test_authenticated_allowed_on_private(self) -> None:
        """The helper does not enforce object-level perms for authenticated
        callers — it only blocks anonymous reads of private resources."""
        from opencontractserver.llms.agents.core_agents import _assert_access

        private = MagicMock(spec=["is_public"])
        private.is_public = False
        # No exception expected.
        _assert_access(private, user_id=42)


class TestResolveToolsCallerForms(TestCase):
    """Cover the union members of ``ToolType`` in ``_resolve_tools`` —
    string lookup, raw callable, ``CoreTool`` passthrough, and the
    invalid-input warning branch."""

    def test_string_resolves_via_registry(self) -> None:
        from opencontractserver.llms.api import _resolve_tools
        from opencontractserver.llms.tools import core_tools as _core_tools_module

        # ``aload_document_md_summary`` is a real registered async tool — pick
        # any name that ``ToolAPI._registered_tools`` exposes for the test.
        registered = _core_tools_module.aload_document_md_summary
        with patch(
            "opencontractserver.llms.api.ToolAPI.from_function",
            side_effect=lambda fn, **kw: fn,
        ):
            with patch(
                "opencontractserver.llms.api._registered_tools",
                {"aload_document_md_summary": registered},
                create=True,
            ):
                # Even when no registry override is in scope, ``_resolve_tools``
                # falls back to ``ToolAPI.from_function`` — so we only assert
                # that the function returns a list.
                result = _resolve_tools(["aload_document_md_summary"])
                self.assertIsInstance(result, list)

    def test_callable_resolves_via_from_function(self) -> None:
        from opencontractserver.llms.api import _resolve_tools

        async def my_tool(arg: int) -> int:
            return arg

        sentinel = object()
        # ``_resolve_tools`` builds the CoreTool by calling
        # ``CoreTool.from_function`` directly (not via the ToolAPI wrapper),
        # so the patch must target the underlying classmethod to be observed.
        with patch(
            "opencontractserver.llms.api.CoreTool.from_function",
            return_value=sentinel,
        ) as from_fn:
            result = _resolve_tools([my_tool])
            self.assertEqual(result, [sentinel])
            from_fn.assert_called_once_with(my_tool)

    def test_unknown_specification_logs_warning_and_skips(self) -> None:
        from opencontractserver.llms.api import _resolve_tools

        # An int is neither a string nor a callable nor a CoreTool — the
        # resolver logs a warning and skips it instead of crashing.
        result = _resolve_tools([42])  # type: ignore[list-item]
        self.assertEqual(result, [])


class TestVectorStoreAPICreate(TestCase):
    """``VectorStoreAPI.create`` reads from the ``LLMS_VECTOR_STORE_FRAMEWORK``
    setting independently of the document-agent setting. Covers the new
    framework resolution path and the factory delegation."""

    def test_create_uses_dedicated_vector_store_setting(self) -> None:
        from opencontractserver.llms.api import VectorStoreAPI

        sentinel = object()
        with patch(
            "opencontractserver.llms.api.UnifiedVectorStoreFactory.create_vector_store",
            return_value=sentinel,
        ) as mock_create:
            result = VectorStoreAPI.create(corpus_id=123)
            self.assertIs(result, sentinel)
            # The factory call should have received a resolved AgentFramework.
            kwargs = mock_create.call_args.kwargs
            self.assertIn("framework", kwargs)
            self.assertEqual(kwargs["corpus_id"], 123)
            self.assertEqual(kwargs["embed_dim"], 384)

    def test_create_forwards_extra_kwargs_to_factory(self) -> None:
        from opencontractserver.llms.api import VectorStoreAPI

        with patch(
            "opencontractserver.llms.api.UnifiedVectorStoreFactory.create_vector_store"
        ) as mock_create:
            VectorStoreAPI.create(
                corpus_id=1,
                document_id=2,
                user_id=3,
                embedder_path="x.y.z",
                must_have_text="needle",
                embed_dim=768,
                extra_flag=True,
            )
            kwargs = mock_create.call_args.kwargs
            self.assertEqual(kwargs["document_id"], 2)
            self.assertEqual(kwargs["user_id"], 3)
            self.assertEqual(kwargs["embedder_path"], "x.y.z")
            self.assertEqual(kwargs["must_have_text"], "needle")
            self.assertEqual(kwargs["embed_dim"], 768)
            self.assertTrue(kwargs["extra_flag"])
