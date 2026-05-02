"""Tests for the structured-extraction None-result classifier.

When ``doc_extract_query_task`` gets ``None`` back from pydantic-ai's
structured agent, it now classifies *why* by inspecting the captured
message log. See issue #1381.
"""

from __future__ import annotations

from typing import Any

from django.test import SimpleTestCase

from opencontractserver.constants.extraction import DEFAULT_EXTRACT_MODEL
from opencontractserver.constants.llm import (
    EXTRACT_DEFAULT_TEMPERATURE,
    NONE_RESULT_AGENT_COMMITTED,
    NONE_RESULT_NO_FINAL,
    NONE_RESULT_TOOL_LOOP,
    NONE_RESULT_UNKNOWN,
    TOOL_LOOP_THRESHOLD,
)
from opencontractserver.tasks.data_extract_tasks import (
    _classify_none_result,
    _failure_message_for_classification,
    _resolve_extract_temperature,
)
from opencontractserver.utils.llm import is_anthropic_model


def _make_response(*parts: Any) -> Any:
    """Construct a pydantic-ai ``ModelResponse`` from raw parts."""
    from pydantic_ai.messages import ModelResponse

    return ModelResponse(parts=list(parts))


def _tool_call(name: str, args: Any = None) -> Any:
    from pydantic_ai.messages import ToolCallPart

    return ToolCallPart(tool_name=name, args=args, tool_call_id="test")


def _text(content: str) -> Any:
    from pydantic_ai.messages import TextPart

    return TextPart(content=content)


class PydanticAiSchemaCanaryTests(SimpleTestCase):
    """Pin the pydantic-ai message-schema assumptions that the classifier relies on.

    ``_classify_none_result`` uses ``isinstance(msg, ModelResponse)`` and
    ``isinstance(part, ToolCallPart)`` rather than string-matching the
    private ``.kind`` / ``.part_kind`` discriminators (issue #1410). These
    canary tests fail fast if a pydantic-ai version bump renames either
    the class import path or the discriminator values, so the silent
    ``empty_history`` mis-classification mode is impossible to slip past.
    """

    def test_model_response_is_importable_and_constructible(self) -> None:
        from pydantic_ai.messages import ModelResponse, TextPart

        # Constructible with at least one part — the shape we depend on.
        msg = ModelResponse(parts=[TextPart(content="ok")])
        self.assertIsInstance(msg, ModelResponse)
        # The discriminator we used to depend on (string-match) still
        # exists; if upstream renames it the assertion forces a deliberate
        # update of the classifier rather than a silent regression.
        self.assertEqual(getattr(msg, "kind", None), "response")

    def test_tool_call_part_discriminator_unchanged(self) -> None:
        from pydantic_ai.messages import ToolCallPart

        part = ToolCallPart(
            tool_name="final_result", args={"value": None}, tool_call_id="canary"
        )
        self.assertEqual(getattr(part, "part_kind", None), "tool-call")

    def test_text_part_discriminator_unchanged(self) -> None:
        from pydantic_ai.messages import TextPart

        part = TextPart(content="hello")
        self.assertEqual(getattr(part, "part_kind", None), "text")


class ClassifyNoneResultTests(SimpleTestCase):
    """Unit tests for :func:`_classify_none_result`."""

    def test_empty_messages_is_unknown(self) -> None:
        self.assertEqual(_classify_none_result(None), NONE_RESULT_UNKNOWN)
        self.assertEqual(_classify_none_result([]), NONE_RESULT_UNKNOWN)

    def test_final_result_call_classifies_as_committed(self) -> None:
        """A ``final_result`` ToolCallPart means the agent committed."""
        messages = [
            _make_response(_tool_call("similarity_search", {"query": "x"})),
            _make_response(_tool_call("final_result", {"value": None})),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_AGENT_COMMITTED)

    def test_final_result_with_suffix_still_committed(self) -> None:
        """Pydantic-ai uses ``final_result_<TypeName>`` for non-string outputs."""
        messages = [
            _make_response(_tool_call("final_result_MyType", {"value": None})),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_AGENT_COMMITTED)

    def test_no_tool_calls_at_all_is_no_final(self) -> None:
        """Pure-text responses with no final_result indicate the loop bailed."""
        messages = [_make_response(_text("Let me search the document..."))]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_NO_FINAL)

    def test_tool_calls_without_final_is_no_final(self) -> None:
        """Tool calls but no final_result and no loop ⇒ no_final_response."""
        messages = [
            _make_response(_tool_call("similarity_search", {"query": "alpha"})),
            _make_response(_tool_call("similarity_search", {"query": "beta"})),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_NO_FINAL)

    def test_repeated_tool_call_classifies_as_tool_loop(self) -> None:
        """Same tool call repeated >= threshold without final ⇒ tool_loop."""
        repeated = _tool_call("similarity_search", {"query": "the same thing"})
        messages = [_make_response(repeated) for _ in range(TOOL_LOOP_THRESHOLD)]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_TOOL_LOOP)

    def test_repeats_below_threshold_are_not_tool_loop(self) -> None:
        """``TOOL_LOOP_THRESHOLD - 1`` repeats ⇒ no_final_response, not tool_loop.

        Pins the boundary so a future tweak of ``TOOL_LOOP_THRESHOLD``
        forces this test to be updated explicitly.
        """
        repeated = _tool_call("similarity_search", {"query": "same"})
        messages = [_make_response(repeated) for _ in range(TOOL_LOOP_THRESHOLD - 1)]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_NO_FINAL)

    def test_loop_then_final_is_committed_not_loop(self) -> None:
        """If the agent eventually commits, that wins over loop detection."""
        repeated = _tool_call("similarity_search", {"query": "loop"})
        messages = [_make_response(repeated) for _ in range(TOOL_LOOP_THRESHOLD)] + [
            _make_response(_tool_call("final_result", {"value": None})),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_AGENT_COMMITTED)

    def test_text_and_single_tool_calls_are_no_final(self) -> None:
        """Mix of narration + tool calls (under threshold) ⇒ no_final_response.

        This is the canonical Anthropic failure mode from issue #1381.
        """
        messages = [
            _make_response(
                _text("Let me search the document for password protection."),
                _tool_call("similarity_search", {"query": "password"}),
            ),
            _make_response(_text("Let me check access controls.")),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_NO_FINAL)

    def test_non_model_response_entries_are_skipped(self) -> None:
        """Non-``ModelResponse`` entries in the log are ignored, not crashing.

        Pydantic-AI's message log interleaves ``ModelRequest`` and
        ``ModelResponse`` objects.  Only the responses can carry tool calls,
        so the classifier must skip everything else cleanly.
        """
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        request = ModelRequest(parts=[UserPromptPart(content="hi")])
        # No ModelResponse at all ⇒ no_final_response (model never spoke).
        self.assertEqual(
            _classify_none_result([request]),
            NONE_RESULT_NO_FINAL,
        )
        # ModelRequest mixed with a tool-calling ModelResponse should still
        # short-circuit on the final_result like normal.
        messages = [
            request,
            _make_response(_tool_call("final_result", {"value": None})),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_AGENT_COMMITTED)

    def test_json_string_args_are_normalised_for_loop_detection(self) -> None:
        """``ToolCallPart.args`` as a JSON string must hash to the same key
        as the equivalent dict so the tool-loop detector counts both.

        Pydantic-AI emits ``ArgsJson`` (str) and ``ArgsDict`` (dict)
        interchangeably across model providers; conflating them in the
        Counter keeps loop detection accurate (issue #1381).

        Alternating dict/str args ``TOOL_LOOP_THRESHOLD`` times must trip
        the loop detector — without normalisation each variant would only
        count to half the threshold and the loop would be missed.
        """
        dict_call = _tool_call("similarity_search", {"query": "same"})
        # Same logical args, but as a JSON string.
        str_call = _tool_call("similarity_search", '{"query": "same"}')
        messages = [
            _make_response(dict_call if i % 2 == 0 else str_call)
            for i in range(TOOL_LOOP_THRESHOLD)
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_TOOL_LOOP)

    def test_malformed_json_string_args_do_not_crash(self) -> None:
        """A malformed JSON string in ``args`` must not raise."""
        bad_call = _tool_call("similarity_search", "{not-json")
        messages = [_make_response(bad_call)]
        # Single call below threshold ⇒ no_final_response, not an exception.
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_NO_FINAL)

    def test_unhashable_args_fall_back_to_repr(self) -> None:
        """If ``json.dumps`` cannot serialise ``args``, classification still works.

        ``default=str`` handles most exotic types, but a deliberately
        unserialisable callable triggers the ``TypeError`` fallback path.
        """

        class _BadArgs:
            def __repr__(self) -> str:
                return "<bad>"

            def __str__(self) -> str:
                # Invoked by ``json.dumps(..., default=str)`` when it tries
                # to coerce ``_BadArgs``; deliberately raises so the
                # classifier's ``except (TypeError, ValueError)`` branch
                # takes over.
                raise TypeError("nope")

        # Two repeats below threshold ⇒ no_final_response; the test is that
        # we reach a classification at all rather than crashing on dumps.
        bad = _BadArgs()
        messages = [
            _make_response(_tool_call("weird", bad)),
            _make_response(_tool_call("weird", bad)),
        ]
        self.assertEqual(_classify_none_result(messages), NONE_RESULT_NO_FINAL)


class FailureMessageTests(SimpleTestCase):
    """Smoke tests for :func:`_failure_message_for_classification`."""

    def test_messages_are_distinct_per_classification(self) -> None:
        """Each classification produces a distinct human-readable message."""
        messages = {
            classification: _failure_message_for_classification(classification)
            for classification in (
                NONE_RESULT_AGENT_COMMITTED,
                NONE_RESULT_NO_FINAL,
                NONE_RESULT_TOOL_LOOP,
                NONE_RESULT_UNKNOWN,
            )
        }
        self.assertEqual(len(set(messages.values())), 4)
        self.assertIn("not found", messages[NONE_RESULT_AGENT_COMMITTED].lower())
        self.assertIn("integration failure", messages[NONE_RESULT_NO_FINAL])
        self.assertIn("looped", messages[NONE_RESULT_TOOL_LOOP])

    def test_integration_failure_messages_reference_log(self) -> None:
        """Operators need a pointer to the raw conversation in the cell stacktrace."""
        for classification in (NONE_RESULT_NO_FINAL, NONE_RESULT_TOOL_LOOP):
            with self.subTest(classification=classification):
                self.assertIn(
                    "llm_call_log",
                    _failure_message_for_classification(classification),
                )


class IsAnthropicModelTests(SimpleTestCase):
    """Tests for the Anthropic model-name detector used for structured runs."""

    def test_anthropic_prefix_is_detected(self) -> None:
        self.assertTrue(is_anthropic_model("anthropic:claude-sonnet-4-6"))
        self.assertTrue(is_anthropic_model("ANTHROPIC:claude-3-haiku"))

    def test_bare_claude_name_is_detected(self) -> None:
        self.assertTrue(is_anthropic_model("claude-3-opus-20240229"))
        self.assertTrue(is_anthropic_model("Claude-Sonnet-4-6"))

    def test_openai_models_are_not_detected(self) -> None:
        self.assertFalse(is_anthropic_model("openai:gpt-4o-mini"))
        self.assertFalse(is_anthropic_model("gpt-4"))
        self.assertFalse(is_anthropic_model("o1-preview"))

    def test_empty_or_none_is_not_detected(self) -> None:
        self.assertFalse(is_anthropic_model(None))
        self.assertFalse(is_anthropic_model(""))


class ResolveExtractTemperatureTests(SimpleTestCase):
    """Tests for :func:`_resolve_extract_temperature`.

    The extract task must hand pydantic-ai ``temperature=None`` for
    Anthropic models so the agent layer's ``temperature=0`` guard fires
    automatically (issue #1381).  For OpenAI models the default 0.3 is
    safe and gives the model a little wiggle room.  This test pins the
    coupling so flipping ``DEFAULT_EXTRACT_MODEL`` to a Claude model
    cannot silently regress the fix.
    """

    def test_anthropic_default_yields_none(self) -> None:
        self.assertIsNone(_resolve_extract_temperature("anthropic:claude-sonnet-4-6"))
        self.assertIsNone(_resolve_extract_temperature("claude-3-opus-20240229"))

    def test_openai_default_yields_default_temperature(self) -> None:
        self.assertEqual(
            _resolve_extract_temperature("openai:gpt-4o-mini"),
            EXTRACT_DEFAULT_TEMPERATURE,
        )
        self.assertEqual(
            _resolve_extract_temperature("gpt-4"),
            EXTRACT_DEFAULT_TEMPERATURE,
        )

    def test_none_or_empty_falls_back_to_default(self) -> None:
        """Unknown / unset model is treated as non-Anthropic (fail-open)."""
        self.assertEqual(
            _resolve_extract_temperature(None),
            EXTRACT_DEFAULT_TEMPERATURE,
        )
        self.assertEqual(
            _resolve_extract_temperature(""),
            EXTRACT_DEFAULT_TEMPERATURE,
        )

    def test_current_default_model_is_openai(self) -> None:
        """Sanity check: today's default model wants the OpenAI temperature.

        If a future PR flips ``DEFAULT_EXTRACT_MODEL`` to a Claude model
        without thinking through the Anthropic guard, this test fails and
        forces a deliberate decision rather than a silent regression.
        """
        self.assertEqual(
            _resolve_extract_temperature(DEFAULT_EXTRACT_MODEL),
            EXTRACT_DEFAULT_TEMPERATURE,
        )
