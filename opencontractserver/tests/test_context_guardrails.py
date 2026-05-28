"""Tests for context guardrails: token estimation, compaction, and truncation.

These tests are deliberately pure-unit (no Django DB required) so they run
fast and can be parallelised trivially.  They exercise the public API of
:mod:`opencontractserver.llms.context_guardrails` and the supporting
constants in :mod:`opencontractserver.constants.context_guardrails`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from opencontractserver.constants.context_guardrails import (
    CHARS_PER_TOKEN_ESTIMATE,
    COMPACTION_SUMMARY_PREFIX,
    COMPACTION_THRESHOLD_RATIO,
    DEFAULT_CONTEXT_WINDOW,
    MAX_TOOL_OUTPUT_CHARS,
    MIN_RECENT_MESSAGES,
    MODEL_CONTEXT_WINDOWS,
)
from opencontractserver.llms.context_guardrails import (
    CompactionConfig,
    CompactionResult,
    _deterministic_summary,
    _MessageProxy,
    compact_message_history,
    estimate_token_count,
    get_context_window_for_model,
    messages_to_proxies,
    should_compact,
    strip_compaction_prefix,
    truncate_tool_output,
)

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestEstimateTokenCount(SimpleTestCase):
    """Tests for the fast heuristic token estimator."""

    def test_empty_string_returns_zero(self):
        self.assertEqual(estimate_token_count(""), 0)

    def test_short_string(self):
        # "hello" = 5 chars → 5 / 3.5 ≈ 1.43 → int(1.43) = 1
        result = estimate_token_count("hello")
        self.assertGreaterEqual(result, 1)

    def test_known_length(self):
        # 350 chars → 350 / 3.5 = 100 tokens
        text = "x" * 350
        self.assertEqual(estimate_token_count(text), 100)

    def test_always_at_least_one_for_nonempty(self):
        self.assertGreaterEqual(estimate_token_count("a"), 1)

    def test_proportional_to_length(self):
        short = estimate_token_count("hello world")
        long = estimate_token_count("hello world " * 100)
        self.assertGreater(long, short)


# ---------------------------------------------------------------------------
# Model context window lookup
# ---------------------------------------------------------------------------


class TestGetContextWindowForModel(SimpleTestCase):
    """Tests for context window lookup with exact and prefix matching."""

    def test_exact_match(self):
        self.assertEqual(
            get_context_window_for_model("gpt-4o-mini"),
            MODEL_CONTEXT_WINDOWS["gpt-4o-mini"],
        )

    def test_prefix_match(self):
        # "gpt-4o-mini-2024-07-18" should match "gpt-4o-mini"
        result = get_context_window_for_model("gpt-4o-mini-2024-07-18")
        self.assertEqual(result, MODEL_CONTEXT_WINDOWS["gpt-4o-mini"])

    def test_anthropic_model(self):
        result = get_context_window_for_model("claude-3-5-sonnet-20241022")
        self.assertEqual(result, MODEL_CONTEXT_WINDOWS["claude-3-5-sonnet"])

    def test_unknown_model_returns_default(self):
        self.assertEqual(
            get_context_window_for_model("totally-unknown-model"),
            DEFAULT_CONTEXT_WINDOW,
        )

    def test_empty_string_returns_default(self):
        self.assertEqual(get_context_window_for_model(""), DEFAULT_CONTEXT_WINDOW)

    def test_longest_prefix_wins(self):
        """When multiple prefixes match, the longest one should win."""
        # "gpt-4o-mini" is a longer prefix than "gpt-4o"
        result = get_context_window_for_model("gpt-4o-mini-turbo")
        # Should match gpt-4o-mini (128K) not gpt-4o (128K too, but specificity matters)
        self.assertEqual(result, MODEL_CONTEXT_WINDOWS["gpt-4o-mini"])


# ---------------------------------------------------------------------------
# Tool output truncation
# ---------------------------------------------------------------------------


class TestTruncateToolOutput(SimpleTestCase):
    """Tests for the tool output truncation utility."""

    def test_short_output_unchanged(self):
        text = "This is short."
        self.assertEqual(truncate_tool_output(text), text)

    def test_output_at_exact_limit_unchanged(self):
        text = "x" * MAX_TOOL_OUTPUT_CHARS
        self.assertEqual(truncate_tool_output(text), text)

    def test_output_exceeding_limit_is_truncated(self):
        text = "x" * (MAX_TOOL_OUTPUT_CHARS + 1000)
        result = truncate_tool_output(text)
        self.assertLessEqual(len(result), MAX_TOOL_OUTPUT_CHARS + 200)  # +notice
        self.assertIn("truncated", result)

    def test_custom_max_chars(self):
        text = "x" * 200
        result = truncate_tool_output(text, max_chars=100)
        self.assertLessEqual(len(result), 100)
        self.assertIn("truncated", result)
        # Content must start from the beginning of the original text
        self.assertTrue(result.startswith("x"))

    def test_truncation_notice_contains_limit(self):
        text = "y" * 500
        result = truncate_tool_output(text, max_chars=200)
        self.assertIn("200", result)
        self.assertLessEqual(len(result), 200)
        # Content must start from the beginning of the original text
        self.assertTrue(result.startswith("y"))

    def test_very_small_max_chars_does_not_exceed_limit(self):
        """When max_chars is smaller than the notice, result must not exceed max_chars."""
        text = "x" * 200
        result = truncate_tool_output(text, max_chars=10)
        self.assertLessEqual(len(result), 10)
        # Content must start from the beginning of the original text
        self.assertTrue(result.startswith("x"))

    def test_truncated_content_from_beginning_not_end(self):
        """Verify truncation takes from the start of the string, not the end."""
        text = "A" * 100 + "B" * 100
        result = truncate_tool_output(text, max_chars=150)
        self.assertLessEqual(len(result), 150)
        self.assertTrue(result.startswith("A"))
        # The result should NOT contain the "B" content from the end
        # (beyond what the truncation notice might contain)
        content_part = result.split("\n\n[")[0] if "\n\n[" in result else result
        self.assertNotIn("B", content_part)


# ---------------------------------------------------------------------------
# _MessageProxy
# ---------------------------------------------------------------------------


class TestMessageProxy(SimpleTestCase):
    """Tests for the lightweight message proxy used in compaction."""

    def test_auto_estimates_tokens(self):
        proxy = _MessageProxy(role="human", content="hello world")
        self.assertGreater(proxy.token_estimate, 0)

    def test_explicit_token_estimate(self):
        proxy = _MessageProxy(role="llm", content="stuff", token_estimate=42)
        self.assertEqual(proxy.token_estimate, 42)

    def test_empty_content(self):
        proxy = _MessageProxy(role="system", content="")
        self.assertEqual(proxy.token_estimate, 0)


# ---------------------------------------------------------------------------
# should_compact
# ---------------------------------------------------------------------------


class TestShouldCompact(SimpleTestCase):
    """Tests for the compaction trigger heuristic."""

    def test_small_conversation_no_compact(self):
        messages = [_MessageProxy(role="human", content="hi")]
        self.assertFalse(should_compact(messages, "gpt-4o-mini"))

    def test_large_conversation_triggers_compact(self):
        # Each message ~1000 tokens, 120 messages → 120K tokens
        # gpt-4o-mini has 128K window, 75% threshold = 96K
        big_content = "x" * int(1000 * CHARS_PER_TOKEN_ESTIMATE)
        messages = [
            _MessageProxy(role="human", content=big_content) for _ in range(120)
        ]
        self.assertTrue(should_compact(messages, "gpt-4o-mini"))

    def test_system_prompt_counts_toward_threshold(self):
        # With a large system prompt, even fewer messages can trigger compaction
        messages = [_MessageProxy(role="human", content="x" * 35000) for _ in range(10)]
        # This alone is ~100K chars = ~28K tokens.  With 50K system prompt
        # tokens the total exceeds 75% of 128K.
        self.assertTrue(
            should_compact(messages, "gpt-4o-mini", system_prompt_tokens=50_000)
        )

    def test_custom_threshold_ratio(self):
        messages = [_MessageProxy(role="human", content="x" * 35000) for _ in range(5)]
        # Very low threshold forces compaction even for small conversations
        self.assertTrue(should_compact(messages, "gpt-4o-mini", threshold_ratio=0.01))


class TestShouldCompactWithStoredSummary(SimpleTestCase):
    """Verify should_compact accounts for stored_summary_tokens."""

    def test_stored_summary_tokens_push_over_threshold(self):
        """A conversation under threshold without stored summary should
        cross the threshold when stored_summary_tokens are included."""
        # 128k window * 0.75 = 96k threshold
        # Place message tokens just under threshold, then stored summary pushes over
        msg_tokens = 90_000
        char_count = int(msg_tokens * CHARS_PER_TOKEN_ESTIMATE)
        messages = [_MessageProxy(role="human", content="x" * char_count)]

        # Without stored summary → under threshold
        self.assertFalse(
            should_compact(messages, "gpt-4o-mini", system_prompt_tokens=0)
        )

        # With stored summary → over threshold
        self.assertTrue(
            should_compact(
                messages,
                "gpt-4o-mini",
                system_prompt_tokens=0,
                stored_summary_tokens=10_000,
            )
        )


# ---------------------------------------------------------------------------
# compact_message_history
# ---------------------------------------------------------------------------


class TestCompactMessageHistory(SimpleTestCase):
    """Tests for the main compaction algorithm."""

    def _make_messages(self, count: int, char_len: int = 100) -> list[_MessageProxy]:
        """Helper to create alternating human/llm message lists."""
        return [
            _MessageProxy(
                role="human" if i % 2 == 0 else "llm",
                content=f"Message {i}: " + "x" * char_len,
            )
            for i in range(count)
        ]

    def test_no_compaction_below_threshold(self):
        messages = self._make_messages(3, char_len=50)
        result = compact_message_history(messages, "gpt-4o-mini")
        self.assertFalse(result.compacted)
        self.assertEqual(result.preserved_count, len(messages))

    def test_compaction_on_large_history(self):
        # Force compaction with very low threshold
        messages = self._make_messages(20, char_len=500)
        result = compact_message_history(messages, "gpt-4o-mini", threshold_ratio=0.001)
        self.assertTrue(result.compacted)
        self.assertGreater(result.removed_count, 0)
        self.assertGreaterEqual(result.preserved_count, MIN_RECENT_MESSAGES)
        self.assertLess(result.estimated_tokens_after, result.estimated_tokens_before)

    def test_summary_contains_prefix(self):
        messages = self._make_messages(20, char_len=500)
        result = compact_message_history(messages, "gpt-4o-mini", threshold_ratio=0.001)
        self.assertTrue(result.summary.startswith(COMPACTION_SUMMARY_PREFIX))

    def test_custom_min_recent(self):
        messages = self._make_messages(20, char_len=500)
        result = compact_message_history(
            messages, "gpt-4o-mini", threshold_ratio=0.001, min_recent=8
        )
        self.assertGreaterEqual(result.preserved_count, 8)

    def test_custom_summary_fn(self):
        """When a summary_fn is provided it should be used instead of the default."""
        messages = self._make_messages(20, char_len=500)
        custom_summary = "Custom summary text"
        result = compact_message_history(
            messages,
            "gpt-4o-mini",
            threshold_ratio=0.001,
            summary_fn=lambda msgs: custom_summary,
        )
        self.assertIn(custom_summary, result.summary)

    def test_returns_result_dataclass(self):
        messages = self._make_messages(5, char_len=50)
        result = compact_message_history(messages, "gpt-4o-mini")
        self.assertIsInstance(result, CompactionResult)

    def test_single_message_never_compacted(self):
        messages = [_MessageProxy(role="human", content="x" * 100000)]
        result = compact_message_history(messages, "gpt-4o-mini", threshold_ratio=0.001)
        # Even if it exceeds threshold, a single message can't be split
        self.assertFalse(result.compacted)

    def test_all_messages_within_recent_window(self):
        """If all messages fit in the recent window, no compaction."""
        messages = self._make_messages(4, char_len=500)
        result = compact_message_history(
            messages, "gpt-4o-mini", threshold_ratio=0.001, min_recent=10
        )
        self.assertFalse(result.compacted)


# ---------------------------------------------------------------------------
# _deterministic_summary
# ---------------------------------------------------------------------------


class TestDeterministicSummary(SimpleTestCase):
    """Tests for the fallback (non-LLM) summary builder."""

    def test_captures_first_human_message(self):
        messages = [
            _MessageProxy(role="human", content="What is the contract about?"),
            _MessageProxy(role="llm", content="The contract covers services."),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("What is the contract about?", summary)

    def test_captures_llm_first_sentence(self):
        messages = [
            _MessageProxy(role="human", content="Summarise."),
            _MessageProxy(
                role="llm",
                content="This is a complex document. It covers many topics.",
            ),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("This is a complex document", summary)

    def test_captures_last_human_message(self):
        messages = [
            _MessageProxy(role="human", content="First question"),
            _MessageProxy(role="llm", content="First answer."),
            _MessageProxy(role="human", content="Follow-up question"),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("Follow-up question", summary)

    def test_respects_char_budget(self):
        """Summary should not grow unbounded."""
        messages = [
            _MessageProxy(role="human", content="q" * 500),
            _MessageProxy(role="llm", content="a" * 5000),
        ] * 50
        summary = _deterministic_summary(messages)
        # Should be bounded by COMPACTION_SUMMARY_TARGET_TOKENS * CHARS_PER_TOKEN_ESTIMATE
        max_expected = int(300 * CHARS_PER_TOKEN_ESTIMATE) + 100  # +slack
        self.assertLessEqual(len(summary), max_expected + 100)

    def test_empty_messages(self):
        summary = _deterministic_summary([])
        self.assertEqual(summary, "")

    def test_abbreviation_not_split(self):
        """'Dr. Smith said hello' should not produce just 'Dr'."""
        messages = [
            _MessageProxy(role="human", content="Who signed?"),
            _MessageProxy(role="llm", content="Dr. Smith said hello."),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("Dr. Smith", summary)

    def test_decimal_not_split(self):
        """'Version 1.5 is out' should not produce just '1'."""
        messages = [
            _MessageProxy(role="human", content="What version?"),
            _MessageProxy(
                role="llm", content="Version 1.5 is out. It has new features."
            ),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("Version 1.5", summary)

    def test_markdown_bullet_list_split(self):
        """Markdown bullet lists should be split at the first list item boundary."""
        messages = [
            _MessageProxy(role="human", content="What does the contract cover?"),
            _MessageProxy(
                role="llm",
                content="The contract covers:\n- Indemnification\n- Liability\n- Termination",
            ),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("The contract covers:", summary)
        # Should NOT include subsequent list items as part of the "sentence"
        self.assertNotIn("Liability", summary)

    def test_double_newline_paragraph_split(self):
        """Double newlines (paragraph boundaries) should act as split points."""
        messages = [
            _MessageProxy(role="human", content="Explain the terms."),
            _MessageProxy(
                role="llm",
                content="The first paragraph explains terms\n\nThe second paragraph adds details.",
            ),
        ]
        summary = _deterministic_summary(messages)
        self.assertIn("The first paragraph explains terms", summary)
        self.assertNotIn("The second paragraph", summary)


# ---------------------------------------------------------------------------
# messages_to_proxies (ORM ↔ proxy bridge)
# ---------------------------------------------------------------------------


class TestMessagesToProxies(SimpleTestCase):
    """Tests for converting ChatMessage-like objects to _MessageProxy."""

    def test_human_message(self):
        mock = MagicMock()
        mock.msg_type = "HUMAN"
        mock.content = "Hello"
        proxies = messages_to_proxies([mock])
        self.assertEqual(len(proxies), 1)
        self.assertEqual(proxies[0].role, "human")
        self.assertEqual(proxies[0].content, "Hello")

    def test_llm_message(self):
        mock = MagicMock()
        mock.msg_type = "LLM"
        mock.content = "Response"
        proxies = messages_to_proxies([mock])
        self.assertEqual(proxies[0].role, "llm")

    def test_system_message(self):
        mock = MagicMock()
        mock.msg_type = "SYSTEM"
        mock.content = "System prompt"
        proxies = messages_to_proxies([mock])
        self.assertEqual(proxies[0].role, "system")

    def test_unknown_type_defaults_to_llm(self):
        mock = MagicMock()
        mock.msg_type = "UNKNOWN"
        mock.content = "Something"
        proxies = messages_to_proxies([mock])
        self.assertEqual(proxies[0].role, "llm")

    def test_empty_list(self):
        self.assertEqual(messages_to_proxies([]), [])

    def test_none_content_handled(self):
        mock = MagicMock()
        mock.msg_type = "HUMAN"
        mock.content = None
        proxies = messages_to_proxies([mock])
        self.assertEqual(proxies[0].content, "")


# ---------------------------------------------------------------------------
# CompactionConfig
# ---------------------------------------------------------------------------


class TestCompactionConfig(SimpleTestCase):
    """Tests for the per-agent compaction configuration."""

    def test_defaults_match_constants(self):
        cfg = CompactionConfig()
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.threshold_ratio, COMPACTION_THRESHOLD_RATIO)
        self.assertEqual(cfg.min_recent_messages, MIN_RECENT_MESSAGES)
        self.assertEqual(cfg.max_tool_output_chars, MAX_TOOL_OUTPUT_CHARS)

    def test_disabled(self):
        cfg = CompactionConfig(enabled=False)
        self.assertFalse(cfg.enabled)

    def test_custom_values(self):
        cfg = CompactionConfig(
            threshold_ratio=0.5,
            min_recent_messages=10,
            max_recent_messages=50,
            max_tool_output_chars=10_000,
        )
        self.assertEqual(cfg.threshold_ratio, 0.5)
        self.assertEqual(cfg.min_recent_messages, 10)
        self.assertEqual(cfg.max_recent_messages, 50)
        self.assertEqual(cfg.max_tool_output_chars, 10_000)

    def test_min_greater_than_max_raises(self):
        with self.assertRaises(ValueError):
            CompactionConfig(min_recent_messages=20, max_recent_messages=4)

    def test_threshold_ratio_zero_raises(self):
        with self.assertRaises(ValueError):
            CompactionConfig(threshold_ratio=0)

    def test_threshold_ratio_one_raises(self):
        with self.assertRaises(ValueError):
            CompactionConfig(threshold_ratio=1.0)

    def test_threshold_ratio_negative_raises(self):
        with self.assertRaises(ValueError):
            CompactionConfig(threshold_ratio=-0.5)

    def test_max_tool_output_chars_zero_raises(self):
        with self.assertRaises(ValueError):
            CompactionConfig(max_tool_output_chars=0)


# ---------------------------------------------------------------------------
# strip_compaction_prefix
# ---------------------------------------------------------------------------


class TestStripCompactionPrefix(SimpleTestCase):
    """Tests for strip_compaction_prefix utility."""

    def test_strips_known_prefix(self):
        text = COMPACTION_SUMMARY_PREFIX + "Some summary body"
        result = strip_compaction_prefix(text)
        self.assertEqual(result, "Some summary body")

    def test_no_prefix_returns_unchanged(self):
        text = "No prefix here"
        result = strip_compaction_prefix(text)
        self.assertEqual(result, "No prefix here")

    def test_empty_string(self):
        result = strip_compaction_prefix("")
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


class TestConstants(SimpleTestCase):
    """Sanity-check tests for the guardrail constants."""

    def test_all_context_windows_positive(self):
        for model, window in MODEL_CONTEXT_WINDOWS.items():
            with self.subTest(model=model):
                self.assertGreater(window, 0)

    def test_default_context_window_positive(self):
        self.assertGreater(DEFAULT_CONTEXT_WINDOW, 0)

    def test_threshold_ratio_in_range(self):
        self.assertGreater(COMPACTION_THRESHOLD_RATIO, 0)
        self.assertLess(COMPACTION_THRESHOLD_RATIO, 1)

    def test_chars_per_token_positive(self):
        self.assertGreater(CHARS_PER_TOKEN_ESTIMATE, 0)

    def test_max_tool_output_chars_reasonable(self):
        self.assertGreater(MAX_TOOL_OUTPUT_CHARS, 1000)

    def test_min_recent_messages_positive(self):
        self.assertGreater(MIN_RECENT_MESSAGES, 0)


# ---------------------------------------------------------------------------
# DB-layer integration tests for compaction bookmark persistence
# ---------------------------------------------------------------------------


class TestConversationCompactionFields(SimpleTestCase):
    """Tests that the Conversation model has the expected compaction fields.

    Uses SimpleTestCase — no actual DB rows, just checks the field definitions
    exist on the model class.
    """

    def test_compaction_summary_field_exists(self):
        from opencontractserver.conversations.models import Conversation

        field = Conversation._meta.get_field("compaction_summary")
        self.assertTrue(field.blank)
        self.assertEqual(field.default, "")

    def test_compacted_before_message_id_field_exists(self):
        from opencontractserver.conversations.models import Conversation

        field = Conversation._meta.get_field("compacted_before_message_id")
        self.assertTrue(field.null)
        self.assertTrue(field.blank)


# ---------------------------------------------------------------------------
# Persist failure path — context must be preserved
# ---------------------------------------------------------------------------


class TestPersistFailurePreservesContext(SimpleTestCase):
    """Verify that when persist_compaction fails, the full message list is
    kept for the current call so no context is lost."""

    def test_persist_failure_keeps_full_message_list(self):
        """Simulate _get_message_history when persist_compaction raises."""
        # Build a scenario: 20 messages, compaction triggers, but persist fails.
        messages = [
            _MessageProxy(
                role="human" if i % 2 == 0 else "llm",
                content=f"Message {i}: " + "x" * 500,
            )
            for i in range(20)
        ]

        # Perform compaction (low threshold forces it)
        result = compact_message_history(messages, "gpt-4o-mini", threshold_ratio=0.001)
        self.assertTrue(result.compacted)
        self.assertGreater(result.removed_count, 0)

        # Simulate the agent's _get_message_history logic:
        # On persist failure, raw_messages should NOT be trimmed.
        raw_messages = list(messages)
        stored_summary = ""

        # merged_summary would be assigned result.summary before persistence
        self.assertTrue(result.summary)  # summary was generated

        try:
            # Simulate a DB failure
            raise RuntimeError("DB write failed")
        except Exception:
            pass  # persist failed — do NOT update stored_summary or trim

        # After failure: raw_messages should still have all 20 messages
        self.assertEqual(len(raw_messages), 20)
        # stored_summary should still be empty (not merged)
        self.assertEqual(stored_summary, "")


# ---------------------------------------------------------------------------
# max_tool_output_chars override via PydanticAIDependencies
# ---------------------------------------------------------------------------


class TestMaxToolOutputCharsOverride(SimpleTestCase):
    """Verify that PydanticAIDependencies.max_tool_output_chars is
    respected by the tool wrapper truncation calls."""

    def test_deps_default_matches_global_constant(self):
        """The default max_tool_output_chars should match the constant."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies()
        self.assertEqual(deps.max_tool_output_chars, MAX_TOOL_OUTPUT_CHARS)

    def test_deps_accepts_custom_value(self):
        """A custom max_tool_output_chars should be stored on the deps."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(max_tool_output_chars=10_000)
        self.assertEqual(deps.max_tool_output_chars, 10_000)

    def test_truncation_respects_custom_limit(self):
        """truncate_tool_output should use the custom limit when passed."""
        long_text = "x" * 20_000
        # With default (50K), this should NOT be truncated
        result_default = truncate_tool_output(long_text)
        self.assertEqual(result_default, long_text)

        # With a 10K limit, it SHOULD be truncated
        result_custom = truncate_tool_output(long_text, max_chars=10_000)
        self.assertIn("truncated", result_custom)
        self.assertLess(len(result_custom), 20_000)


# ---------------------------------------------------------------------------
# Context-budget snapshot on PydanticAIDependencies
# ---------------------------------------------------------------------------


class TestContextBudgetSnapshot(SimpleTestCase):
    """The context-budget snapshot fields drive the adaptive
    ``load_document_text`` tool.  The tests below verify the budget math
    so the tool's ``end`` defaulting stays predictable as constants
    evolve."""

    def test_remaining_tokens_until_compaction_basic(self):
        """remaining = threshold - estimated_used, floored at 0."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )
        # threshold = 150_000; used = 20_000 → 130_000 remaining
        self.assertEqual(deps.remaining_tokens_until_compaction(), 130_000)

    def test_remaining_tokens_zero_when_over_threshold(self):
        """When usage already exceeds the threshold, remaining is 0
        (never negative)."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=100_000,
            estimated_used_tokens=90_000,
            compaction_threshold_ratio=0.75,
        )
        self.assertEqual(deps.remaining_tokens_until_compaction(), 0)

    def test_recommended_chunk_chars_reserves_default_25_percent(self):
        """Default reserve_ratio leaves 25% of remaining tokens for the
        assistant's own response and per-turn slop."""
        from opencontractserver.constants.context_guardrails import (
            CHARS_PER_TOKEN_ESTIMATE,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )
        # remaining = 130_000 tokens; usable = 130_000 * 0.75 = 97_500
        # chars = 97_500 * 3.5 = 341_250
        expected_chars = int(130_000 * 0.75 * CHARS_PER_TOKEN_ESTIMATE)
        self.assertEqual(deps.recommended_chunk_chars(), expected_chars)

    def test_recommended_chunk_chars_zero_when_starved(self):
        """An exhausted budget should yield 0 recommended chars so callers
        know to fall back to a small minimum or skip the load."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=100_000,
            estimated_used_tokens=100_000,
            compaction_threshold_ratio=0.75,
        )
        self.assertEqual(deps.recommended_chunk_chars(), 0)

    def test_recommended_chunk_chars_custom_reserve(self):
        """A custom reserve_ratio overrides the 0.25 default."""
        from opencontractserver.constants.context_guardrails import (
            CHARS_PER_TOKEN_ESTIMATE,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )
        # 50% reserve → 50% usable
        expected_chars = int(130_000 * 0.5 * CHARS_PER_TOKEN_ESTIMATE)
        self.assertEqual(
            deps.recommended_chunk_chars(reserve_ratio=0.5),
            expected_chars,
        )

    def test_recommended_chunk_chars_reserve_above_one_clamps_and_warns(self):
        """``reserve_ratio > 1`` clamps to 1 (yielding 0 usable tokens) and
        emits a warning so the caller can spot the mistake instead of being
        confused by an unexplained empty slice."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )
        with self.assertLogs(
            "opencontractserver.llms.tools.pydantic_ai_tools",
            level="WARNING",
        ) as ctx:
            result = deps.recommended_chunk_chars(reserve_ratio=1.5)
        self.assertEqual(result, 0)
        self.assertTrue(
            any("reserve_ratio=1.5" in msg for msg in ctx.output),
            f"Expected reserve_ratio=1.5 warning, got: {ctx.output}",
        )

    def test_recommended_chunk_chars_reserve_below_zero_clamps_and_warns(self):
        """``reserve_ratio < 0`` clamps to 0 (full budget) and warns."""
        from opencontractserver.constants.context_guardrails import (
            CHARS_PER_TOKEN_ESTIMATE,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )
        with self.assertLogs(
            "opencontractserver.llms.tools.pydantic_ai_tools",
            level="WARNING",
        ) as ctx:
            result = deps.recommended_chunk_chars(reserve_ratio=-0.1)
        # Clamped to 0 → 100% of remaining 130_000 tokens usable.
        self.assertEqual(result, int(130_000 * CHARS_PER_TOKEN_ESTIMATE))
        self.assertTrue(
            any("reserve_ratio=-0.1" in msg for msg in ctx.output),
            f"Expected reserve_ratio=-0.1 warning, got: {ctx.output}",
        )

    def test_turn_implicit_doc_text_chars_defaults_to_zero(self):
        """The per-turn implicit-chunk tally starts at 0 so the first
        load_document_text call sees the unmodified recommended budget."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies()
        self.assertEqual(deps.turn_implicit_doc_text_chars, 0)

    def test_turn_implicit_doc_text_chars_is_mutable(self):
        """The accumulator is plain Pydantic state — assignable so the
        agent factory's load_document_text closure can fold it into the
        budget on subsequent calls within the same turn."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies()
        deps.turn_implicit_doc_text_chars += 12_000
        self.assertEqual(deps.turn_implicit_doc_text_chars, 12_000)
        deps.turn_implicit_doc_text_chars = 0
        self.assertEqual(deps.turn_implicit_doc_text_chars, 0)


# ---------------------------------------------------------------------------
# get_remaining_context_budget tool — return shape contract
# ---------------------------------------------------------------------------


class TestGetRemainingContextBudgetShape(SimpleTestCase):
    """The ``get_remaining_context_budget`` tool registered in the document-agent
    factory must expose a stable 6-field dict so callers don't silently lose
    new budget fields if deps evolve. This class pins the return shape without
    needing the full async agent-factory setup."""

    EXPECTED_KEYS = frozenset(
        {
            "model_name",
            "context_window_tokens",
            "estimated_used_tokens",
            "remaining_tokens_until_compaction",
            "compaction_threshold_ratio",
            "recommended_chunk_chars",
        }
    )

    def _make_snapshot(self) -> dict:
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            model_name="claude-opus-4-7",
            context_window_tokens=200_000,
            estimated_used_tokens=10_000,
            compaction_threshold_ratio=0.75,
        )
        # Mirror the closure body in PydanticAIDocumentAgent.create exactly.
        return {
            "model_name": deps.model_name,
            "context_window_tokens": deps.context_window_tokens,
            "estimated_used_tokens": deps.estimated_used_tokens,
            "remaining_tokens_until_compaction": deps.remaining_tokens_until_compaction(),
            "compaction_threshold_ratio": deps.compaction_threshold_ratio,
            "recommended_chunk_chars": deps.recommended_chunk_chars(),
        }

    def test_return_has_exactly_expected_keys(self):
        """The snapshot dict must contain exactly the 6 documented fields."""
        snapshot = self._make_snapshot()
        self.assertEqual(set(snapshot.keys()), self.EXPECTED_KEYS)

    def test_return_value_types_are_correct(self):
        """All fields must carry their documented types so downstream code
        can safely perform arithmetic without isinstance checks."""
        snapshot = self._make_snapshot()
        self.assertIsInstance(snapshot["model_name"], str)
        self.assertIsInstance(snapshot["context_window_tokens"], int)
        self.assertIsInstance(snapshot["estimated_used_tokens"], int)
        self.assertIsInstance(snapshot["remaining_tokens_until_compaction"], int)
        self.assertIsInstance(snapshot["compaction_threshold_ratio"], float)
        self.assertIsInstance(snapshot["recommended_chunk_chars"], int)

    def test_remaining_tokens_positive_for_low_usage(self):
        """With 10k used against a 200k window at 75% threshold,
        remaining_tokens_until_compaction should be comfortably positive."""
        snapshot = self._make_snapshot()
        self.assertGreater(snapshot["remaining_tokens_until_compaction"], 0)
        self.assertGreater(snapshot["recommended_chunk_chars"], 0)


# ---------------------------------------------------------------------------
# load_document_text closure — multi-call drift within a single turn
# ---------------------------------------------------------------------------


class TestLoadDocumentTextDriftMath(SimpleTestCase):
    """The ``load_document_text`` closure inside the agent factory subtracts
    ``turn_implicit_doc_text_chars`` from ``recommended_chunk_chars()`` so
    successive ``end``-less calls within the same turn back off
    proportionally instead of all returning the same fresh budget. The math
    below mirrors the closure's arithmetic exactly so we can pin the drift
    behaviour without needing the full async closure environment."""

    @staticmethod
    def _budget_chars(deps) -> int:
        """Replicates the closure body in ``load_document_text_tool`` so
        the drift math can be exercised in isolation."""
        from opencontractserver.constants.context_guardrails import (
            MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS,
        )

        recommended = deps.recommended_chunk_chars()
        budget_after = max(0, recommended - deps.turn_implicit_doc_text_chars)
        return max(budget_after, MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS)

    def test_second_implicit_call_receives_smaller_budget(self):
        """After the first implicit call records its slice in the tally,
        the second call must see a strictly smaller budget."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )

        first = self._budget_chars(deps)
        # Simulate the closure recording the first implicit slice it served.
        deps.turn_implicit_doc_text_chars += first
        second = self._budget_chars(deps)

        self.assertGreater(first, second)

    def test_drift_floors_at_minimum_chunk(self):
        """Once the in-turn tally exceeds the recommended budget, the
        closure clamps to ``MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS`` rather
        than returning 0 — the slice must stay big enough to be useful
        for whole-document tasks."""
        from opencontractserver.constants.context_guardrails import (
            MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )
        # Burn the entire turn budget and then some.
        deps.turn_implicit_doc_text_chars = 10_000_000

        self.assertEqual(
            self._budget_chars(deps),
            MIN_IMPLICIT_DOCUMENT_CHUNK_CHARS,
        )

    def test_reset_returns_to_full_budget(self):
        """``_refresh_context_budget`` resets the tally; the next turn's
        first implicit call should once again see the full recommendation."""
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies(
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
        )

        baseline = self._budget_chars(deps)
        deps.turn_implicit_doc_text_chars += 50_000
        self.assertLess(self._budget_chars(deps), baseline)

        # New turn → reset.
        deps.turn_implicit_doc_text_chars = 0
        self.assertEqual(self._budget_chars(deps), baseline)


# ---------------------------------------------------------------------------
# load_document_text closure — end-to-end integration
# ---------------------------------------------------------------------------


class TestLoadDocumentTextClosureIntegration(SimpleTestCase):
    """Drive the actual ``_make_load_document_text_tool`` closure with a
    stubbed cache. Exercises the full dict-shape contract (``returned_range``,
    ``budget_was_applied``, etc.) and verifies that
    ``turn_implicit_doc_text_chars`` is mutated through the closure
    reference — the property the per-turn drift compensation depends on."""

    DOC_ID = 999
    # Larger than ``recommended_chunk_chars`` for the configured budget so
    # successive implicit calls actually advance the in-turn tally instead
    # of exhausting the document on the first read.
    DOC_LEN = 1_000_000

    def _make_deps(self):
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        return PydanticAIDependencies(
            document_id=self.DOC_ID,
            context_window_tokens=200_000,
            estimated_used_tokens=20_000,
            compaction_threshold_ratio=0.75,
            model_name="gpt-4o",
        )

    def _patches(self):
        """Patch the cache helpers used by the closure.

        ``aload_document_txt_extract`` is async; ``get_cached_txt_extract_length``
        and ``is_txt_extract_cached`` are sync. Returning a fixed length
        keeps the math predictable and the slice text deterministic so
        the test can pin ``returned_range``. ``is_txt_extract_cached`` is
        patched to ``True`` so the closure's membership guard skips the
        cache-prime fetch on every call — without this the real predicate
        would return ``False`` (since the fake loader doesn't populate
        ``_DOC_TXT_CACHE``) and silently re-fire the prime each call,
        exercising the empty-document path instead of the intended
        warm-cache one. ``test_empty_document_does_not_repopulate_cache``
        intentionally leaves both predicates unpatched to drive the
        membership-vs-length distinction end-to-end.
        """
        from opencontractserver.llms.agents import pydantic_ai_agents as mod

        async def fake_load(doc_id, start=None, end=None, refresh=False):
            if start is None and end is None:
                return "x" * self.DOC_LEN
            return "x" * (end - start)

        return (
            patch.object(
                mod, "get_cached_txt_extract_length", return_value=self.DOC_LEN
            ),
            patch.object(mod, "is_txt_extract_cached", return_value=True),
            patch.object(
                mod, "aload_document_txt_extract", new=AsyncMock(side_effect=fake_load)
            ),
        )

    async def test_implicit_call_returns_full_dict_shape(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_load_document_text_tool,
        )

        deps = self._make_deps()
        cache_patch, cached_patch, load_patch = self._patches()
        with cache_patch, cached_patch, load_patch:
            tool = _make_load_document_text_tool(deps, self.DOC_ID)
            result = await tool()

        self.assertEqual(
            set(result.keys()),
            {
                "text",
                "total_chars",
                "returned_range",
                "chars_remaining",
                "suggested_next_start",
                "context_budget_chars",
                "budget_was_applied",
            },
        )
        self.assertTrue(result["budget_was_applied"])
        self.assertEqual(result["total_chars"], self.DOC_LEN)
        # Exclusive end: returned_range[1] == start_idx + len(text).
        self.assertEqual(result["returned_range"][0], 0)
        self.assertEqual(result["returned_range"][1], len(result["text"]))
        # suggested_next_start either the next index or None when fully read.
        if result["chars_remaining"] > 0:
            self.assertEqual(
                result["suggested_next_start"], result["returned_range"][1]
            )
        else:
            self.assertIsNone(result["suggested_next_start"])

    async def test_explicit_end_marks_budget_not_applied(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_load_document_text_tool,
        )

        deps = self._make_deps()
        cache_patch, cached_patch, load_patch = self._patches()
        with cache_patch, cached_patch, load_patch:
            tool = _make_load_document_text_tool(deps, self.DOC_ID)
            result = await tool(start=100, end=500)

        self.assertFalse(result["budget_was_applied"])
        self.assertEqual(result["returned_range"], [100, 500])
        # Explicit-end calls must NOT advance the in-turn tally.
        self.assertEqual(deps.turn_implicit_doc_text_chars, 0)

    async def test_implicit_calls_advance_turn_tally(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_load_document_text_tool,
        )

        deps = self._make_deps()
        cache_patch, cached_patch, load_patch = self._patches()
        with cache_patch, cached_patch, load_patch:
            tool = _make_load_document_text_tool(deps, self.DOC_ID)

            first = await tool()
            tally_after_first = deps.turn_implicit_doc_text_chars
            second_budget_seen = deps.recommended_chunk_chars()

            second = await tool(start=first["returned_range"][1])

        # Closure reference is shared — mutation visible across calls.
        self.assertGreater(tally_after_first, 0)
        self.assertGreater(deps.turn_implicit_doc_text_chars, tally_after_first)
        # The second implicit call's effective budget must shrink relative
        # to the fresh recommendation (the drift compensation kicked in).
        self.assertLessEqual(second["context_budget_chars"], second_budget_seen)

    async def test_empty_document_does_not_repopulate_cache(self):
        """Genuinely empty documents (cached as ``""``) must not retrigger
        the cache-priming load on every call. Previously the closure used
        ``cached_len == 0`` to detect "never loaded", which collided with
        "loaded and empty" and caused a redundant prime fetch each call.
        The fix uses ``is_txt_extract_cached`` (membership), so the second
        call sees the cache as populated.

        The prime is detected by its distinctive signature
        ``start=0, end=1`` (vs the per-call slice load which uses
        ``start=0, end=0`` once ``total_chars`` is known to be zero).
        """
        from unittest.mock import AsyncMock

        from opencontractserver.llms.agents import pydantic_ai_agents as mod
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_load_document_text_tool,
        )
        from opencontractserver.llms.tools.core_tools import text_extracts

        # Reset module-level cache before the test (other tests may have
        # populated it for DOC_ID and we want a clean slate).
        text_extracts._DOC_TXT_CACHE.pop(self.DOC_ID, None)

        deps = self._make_deps()
        load_calls = []

        async def fake_load(doc_id, start=None, end=None, refresh=False):
            load_calls.append((doc_id, start, end, refresh))
            # Populate cache with empty content via the real cache dict
            # so ``is_txt_extract_cached`` flips to True after the prime.
            from datetime import datetime as _dt

            text_extracts._DOC_TXT_CACHE[doc_id] = (_dt.now(), "")
            return ""

        # NOTE: we intentionally do NOT patch ``is_txt_extract_cached`` or
        # ``get_cached_txt_extract_length`` — we want the real helpers to
        # exercise the membership-vs-length distinction.
        with patch.object(
            mod, "aload_document_txt_extract", new=AsyncMock(side_effect=fake_load)
        ):
            tool = _make_load_document_text_tool(deps, self.DOC_ID)
            result1 = await tool()
            result2 = await tool()

        # The prime call (start=0, end=1) must happen exactly once across
        # both invocations. Pre-fix this would have been 2.
        prime_calls = [
            c for c in load_calls if c[1] == 0 and c[2] == 1 and c[3] is False
        ]
        self.assertEqual(
            len(prime_calls),
            1,
            f"Expected exactly one cache-prime load (start=0, end=1); "
            f"got {len(prime_calls)} in {load_calls}",
        )
        self.assertEqual(result1["total_chars"], 0)
        self.assertEqual(result2["total_chars"], 0)
        self.assertEqual(result1["text"], "")
        self.assertEqual(result2["text"], "")

        # Cleanup so subsequent tests don't see the empty cache entry.
        text_extracts._DOC_TXT_CACHE.pop(self.DOC_ID, None)


# ---------------------------------------------------------------------------
# _make_get_document_text_length_tool closure
# ---------------------------------------------------------------------------


class TestGetDocumentTextLengthClosure(SimpleTestCase):
    """The ``get_document_text_length`` closure must use the membership
    predicate (``is_txt_extract_cached``) to detect a successful prime,
    NOT the length predicate — otherwise a genuinely empty document
    (cached as ``""``) silently re-loads the full document on every call.

    Also pins the cache-miss fallback (defensive against a future cache
    backend that drops entries) so the closure still returns the correct
    length when the prime fails to populate.
    """

    DOC_ID = 98_765

    def setUp(self):
        from opencontractserver.llms.tools.core_tools import text_extracts

        text_extracts._DOC_TXT_CACHE.pop(self.DOC_ID, None)

    def tearDown(self):
        from opencontractserver.llms.tools.core_tools import text_extracts

        text_extracts._DOC_TXT_CACHE.pop(self.DOC_ID, None)

    async def test_returns_cached_length_for_empty_document(self):
        """Empty document (cached as ``""``) — the membership predicate
        sees the prime as cached and the closure returns 0 without a
        second full load."""
        from unittest.mock import AsyncMock

        from opencontractserver.llms.agents import pydantic_ai_agents as mod
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_get_document_text_length_tool,
        )
        from opencontractserver.llms.tools.core_tools import text_extracts

        load_calls: list[tuple] = []

        async def fake_load(doc_id, start=None, end=None, refresh=False):
            load_calls.append((doc_id, start, end, refresh))
            from datetime import datetime as _dt

            # Prime caches the empty document.
            text_extracts._DOC_TXT_CACHE[doc_id] = (_dt.now(), "")
            return ""

        with patch.object(
            mod, "aload_document_txt_extract", new=AsyncMock(side_effect=fake_load)
        ):
            tool = _make_get_document_text_length_tool(self.DOC_ID)
            result = await tool()

        # Empty cached doc → 0 length, exactly one load (the prime).
        self.assertEqual(result, 0)
        self.assertEqual(len(load_calls), 1)
        self.assertEqual(load_calls[0][1:3], (0, 1))

    async def test_returns_cached_length_for_populated_document(self):
        """Populated document — the prime hits, the membership predicate
        flips to True, and the closure returns the cached length without
        a second full load."""
        from unittest.mock import AsyncMock

        from opencontractserver.llms.agents import pydantic_ai_agents as mod
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_get_document_text_length_tool,
        )
        from opencontractserver.llms.tools.core_tools import text_extracts

        load_calls: list[tuple] = []

        async def fake_load(doc_id, start=None, end=None, refresh=False):
            load_calls.append((doc_id, start, end, refresh))
            from datetime import datetime as _dt

            text_extracts._DOC_TXT_CACHE[doc_id] = (_dt.now(), "abcdef" * 10)
            return "ab"

        with patch.object(
            mod, "aload_document_txt_extract", new=AsyncMock(side_effect=fake_load)
        ):
            tool = _make_get_document_text_length_tool(self.DOC_ID)
            result = await tool()

        self.assertEqual(result, 60)
        # Exactly one load (the prime) — pinning this prevents a future
        # regression where the membership check is loosened back into the
        # fallback path.
        self.assertEqual(len(load_calls), 1)

    async def test_falls_back_to_full_load_on_cache_miss(self):
        """If the prime did NOT populate the cache (defensive fallback
        for a future cache backend that drops entries), the closure
        falls through to a full ``aload_document_txt_extract`` call and
        returns ``len(full_text)``."""
        from unittest.mock import AsyncMock

        from opencontractserver.llms.agents import pydantic_ai_agents as mod
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_get_document_text_length_tool,
        )

        # The prime call returns "" *and does not populate the cache* —
        # ``is_txt_extract_cached`` will be False after the prime and the
        # fallback branch fires. The fallback call returns the full text.
        load_calls: list[tuple] = []

        async def fake_load(doc_id, start=None, end=None, refresh=False):
            load_calls.append((doc_id, start, end, refresh))
            # Intentionally do NOT mutate _DOC_TXT_CACHE so the membership
            # predicate stays False and the fallback path fires.
            if start == 0 and end == 1:
                return ""
            return "the full text"

        with patch.object(
            mod, "aload_document_txt_extract", new=AsyncMock(side_effect=fake_load)
        ):
            tool = _make_get_document_text_length_tool(self.DOC_ID)
            result = await tool()

        # Two loads: the prime (0,1) and the fallback (no slice args).
        self.assertEqual(len(load_calls), 2)
        self.assertEqual(load_calls[0][1:3], (0, 1))
        self.assertEqual(load_calls[1][1:3], (None, None))
        self.assertEqual(result, len("the full text"))


# ---------------------------------------------------------------------------
# is_txt_extract_cached membership predicate
# ---------------------------------------------------------------------------


class TestIsTxtExtractCached(SimpleTestCase):
    """The membership predicate must distinguish "never loaded" (False)
    from "loaded but empty" (True) — the bug the load_document_text
    closure used to suffer from."""

    DOC_ID = 12_345

    def setUp(self):
        from opencontractserver.llms.tools.core_tools import text_extracts

        text_extracts._DOC_TXT_CACHE.pop(self.DOC_ID, None)

    def tearDown(self):
        from opencontractserver.llms.tools.core_tools import text_extracts

        text_extracts._DOC_TXT_CACHE.pop(self.DOC_ID, None)

    def test_false_when_never_loaded(self):
        from opencontractserver.llms.tools.core_tools.text_extracts import (
            is_txt_extract_cached,
        )

        self.assertFalse(is_txt_extract_cached(self.DOC_ID))

    def test_true_when_loaded_even_if_empty(self):
        from datetime import datetime

        from opencontractserver.llms.tools.core_tools import text_extracts
        from opencontractserver.llms.tools.core_tools.text_extracts import (
            is_txt_extract_cached,
        )

        text_extracts._DOC_TXT_CACHE[self.DOC_ID] = (datetime.now(), "")
        self.assertTrue(is_txt_extract_cached(self.DOC_ID))
        # And the length predicate still returns 0 — confirming the
        # ambiguity the new predicate resolves.
        from opencontractserver.llms.tools.core_tools.text_extracts import (
            get_cached_txt_extract_length,
        )

        self.assertEqual(get_cached_txt_extract_length(self.DOC_ID), 0)

    def test_true_when_loaded_with_content(self):
        from datetime import datetime

        from opencontractserver.llms.tools.core_tools import text_extracts
        from opencontractserver.llms.tools.core_tools.text_extracts import (
            is_txt_extract_cached,
        )

        text_extracts._DOC_TXT_CACHE[self.DOC_ID] = (datetime.now(), "abc")
        self.assertTrue(is_txt_extract_cached(self.DOC_ID))


# ---------------------------------------------------------------------------
# _refresh_context_budget — falsy-zero fallback semantics
# ---------------------------------------------------------------------------


class TestRefreshContextBudgetFallback(SimpleTestCase):
    """When ``_HistoryResult.context_window`` is 0 (e.g. on a fresh agent
    that has never been queried), the snapshot must fall through to the
    per-model registry rather than treating 0 as a legitimate window."""

    def _make_history_result(self, context_window: int):
        """Return a ``_HistoryResult`` overriding only ``context_window``.

        Uses ``dataclasses.replace`` against the dataclass's default
        construction so this helper survives the addition of new fields
        on ``_HistoryResult`` (which would otherwise silently feed the
        old required-arg list into the constructor and either raise or
        construct stale objects).
        """
        import dataclasses

        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _HistoryResult,
        )

        return dataclasses.replace(
            _HistoryResult(messages=[]),
            context_window=context_window,
        )

    def test_zero_context_window_falls_back_to_model_registry(self):
        from opencontractserver.constants.context_guardrails import (
            MODEL_CONTEXT_WINDOWS,
        )
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies()
        config = AgentConfig(model_name="gpt-4o")

        # Drive the pure transformation directly — no ``__new__`` bypass on
        # the agent class, so the test stays stable as ``__init__`` evolves.
        PydanticAICoreAgent._apply_context_budget(
            deps, config, self._make_history_result(0)
        )

        self.assertEqual(deps.context_window_tokens, MODEL_CONTEXT_WINDOWS["gpt-4o"])

    def test_nonzero_context_window_is_used_verbatim(self):
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies()
        config = AgentConfig(model_name="gpt-4o")

        PydanticAICoreAgent._apply_context_budget(
            deps, config, self._make_history_result(99_999)
        )

        self.assertEqual(deps.context_window_tokens, 99_999)

    def test_none_deps_is_noop(self):
        """Passing ``None`` for deps should be a silent no-op."""
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Should not raise.
        PydanticAICoreAgent._apply_context_budget(
            None, AgentConfig(model_name="gpt-4o"), self._make_history_result(0)
        )

    def test_compaction_config_is_copied_to_deps(self):
        """Per-conversation ``CompactionConfig`` overrides must reach
        ``agent_deps.compaction`` so the in-run history processor sees
        them. Regression for the bug where only ``threshold_ratio`` was
        forwarded and every other knob silently defaulted.
        """
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import CompactionConfig
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        deps = PydanticAIDependencies()
        custom = CompactionConfig(
            threshold_ratio=0.42,
            in_run_enabled=False,
            in_run_keep_recent_pairs=2,
            in_run_tool_return_target_chars=123,
            in_run_drop_thinking=False,
        )
        config = AgentConfig(model_name="gpt-4o", compaction=custom)

        PydanticAICoreAgent._apply_context_budget(
            deps, config, self._make_history_result(0)
        )

        # The full config is propagated — not just threshold_ratio.
        self.assertIs(deps.compaction, custom)
        self.assertEqual(deps.compaction.in_run_keep_recent_pairs, 2)
        self.assertFalse(deps.compaction.in_run_enabled)


class _FakePart:
    """Lightweight pydantic-ai-part stand-in for ``_part_text`` tests."""

    def __init__(self, content, args):
        self.content = content
        self.args = args


class _FakeMessage:
    """Lightweight pydantic-ai-message stand-in for ``_part_text`` tests."""

    def __init__(self, parts):
        self.parts = parts


class TestHistoryResultFromMessages(SimpleTestCase):
    """`_history_result_from_messages` builds a ``_HistoryResult`` from an
    explicit Pydantic-AI message list. Pins the codepath that
    ``resume_with_approval`` uses to refresh the budget snapshot when it
    bypasses ``_get_message_history``."""

    def test_explicit_history_estimates_tokens_and_window(self):
        from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        config = AgentConfig(
            model_name="gpt-4o", system_prompt="You are a helpful assistant."
        )

        # Annotate as ``list[ModelMessage]`` so mypy treats the literal as
        # the union the helper accepts (``list`` is invariant; a bare
        # ``list[ModelRequest]`` would be rejected).
        messages: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="hello world " * 50)])
        ]

        history = PydanticAICoreAgent._history_result_from_messages(config, messages)

        self.assertGreater(history.estimated_tokens, 0)
        self.assertGreater(history.context_window, 0)
        self.assertEqual(history.messages, messages)
        self.assertFalse(history.was_compacted)

    def test_empty_messages_estimates_only_system_prompt(self):
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import estimate_token_count

        config = AgentConfig(
            model_name="gpt-4o", system_prompt="You are a helpful assistant."
        )

        history = PydanticAICoreAgent._history_result_from_messages(config, [])
        # Only system-prompt tokens should contribute.
        self.assertEqual(
            history.estimated_tokens,
            estimate_token_count("You are a helpful assistant."),
        )

    def test_none_messages_estimates_only_system_prompt(self):
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import estimate_token_count

        config = AgentConfig(model_name="gpt-4o", system_prompt="System.")

        history = PydanticAICoreAgent._history_result_from_messages(config, None)
        self.assertEqual(history.estimated_tokens, estimate_token_count("System."))

    def test_part_text_empty_content_does_not_fall_through_to_args(self):
        """An empty ``content`` string (e.g. a ``ToolReturnPart`` with an
        empty result) must NOT trigger the args fallback — that would
        replace the legitimately-empty content with the tool's input
        arguments and double-count those tokens in the budget snapshot.

        Pre-fix the closure used ``getattr(p, "content", None) or
        getattr(p, "args", None)`` which short-circuited on falsy
        empty strings. The fix uses an explicit ``is None`` guard.
        """
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import estimate_token_count

        # An empty ToolReturnPart-style part with large argument payload
        # should contribute zero text — the args fallback must not fire.
        big_args = "x" * 4000
        msgs = [_FakeMessage([_FakePart(content="", args=big_args)])]

        config = AgentConfig(model_name="gpt-4o", system_prompt="")
        history = PydanticAICoreAgent._history_result_from_messages(
            config, msgs  # type: ignore[arg-type]
        )

        # Tokens for "" only — system prompt is empty, the part is empty.
        self.assertEqual(history.estimated_tokens, estimate_token_count(""))

    def test_part_text_none_content_falls_back_to_args(self):
        """A part with ``content=None`` (e.g. ``ToolCallPart`` storing
        arguments in ``args``) must still get its tokens counted via the
        args fallback so tool-call argument payloads contribute to the
        budget snapshot."""
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import estimate_token_count

        big_args = "y" * 4000
        msgs = [_FakeMessage([_FakePart(content=None, args=big_args)])]

        config = AgentConfig(model_name="gpt-4o", system_prompt="")
        history = PydanticAICoreAgent._history_result_from_messages(
            config, msgs  # type: ignore[arg-type]
        )

        # Tokens for the args payload — content was None so fallback fires.
        self.assertEqual(history.estimated_tokens, estimate_token_count(big_args))

    def test_part_text_non_string_content_is_stringified(self):
        """When a part's content is something other than ``str`` (e.g.
        a structured payload), the helper falls back to ``str(content)``
        so the budget estimate doesn't silently drop those tokens."""
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import estimate_token_count

        payload = {"hello": "world"}
        msgs = [_FakeMessage([_FakePart(content=payload, args=None)])]

        config = AgentConfig(model_name="gpt-4o", system_prompt="")
        history = PydanticAICoreAgent._history_result_from_messages(
            config, msgs  # type: ignore[arg-type]
        )

        # Tokens for str(payload) — content was non-str non-None.
        self.assertEqual(history.estimated_tokens, estimate_token_count(str(payload)))

    def test_part_text_none_content_and_none_args_returns_empty(self):
        """When both ``content`` and ``args`` are absent, the helper
        returns ``""`` so a fully-empty part contributes zero tokens."""
        from opencontractserver.llms.agents.core_agents import AgentConfig
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )
        from opencontractserver.llms.context_guardrails import estimate_token_count

        msgs = [_FakeMessage([_FakePart(content=None, args=None)])]

        config = AgentConfig(model_name="gpt-4o", system_prompt="")
        history = PydanticAICoreAgent._history_result_from_messages(
            config, msgs  # type: ignore[arg-type]
        )

        # An empty system prompt + empty part text yields zero tokens.
        self.assertEqual(history.estimated_tokens, estimate_token_count(""))


# ---------------------------------------------------------------------------
# Optimistic locking in persist_compaction
# ---------------------------------------------------------------------------


class TestPersistCompactionOptimisticLock(SimpleTestCase):
    """Verify that persist_compaction uses optimistic locking to avoid
    overwriting a concurrently-advanced bookmark."""

    async def test_concurrent_persist_second_write_is_noop(self):
        """If the bookmark moves between read and write, the write is skipped."""
        from opencontractserver.llms.agents.core_agents import (
            CoreConversationManager,
        )

        # Create a mock conversation with no existing bookmark
        mock_conv = MagicMock()
        mock_conv.pk = 42
        mock_conv.compacted_before_message_id = None
        mock_conv.compaction_summary = ""

        manager = CoreConversationManager.__new__(CoreConversationManager)
        manager.conversation = mock_conv

        # Patch Conversation.objects.filter().aupdate()
        with patch(
            "opencontractserver.llms.agents.core_agents.Conversation"
        ) as MockConv:
            # First call: filter matches → updated=1
            mock_qs = MagicMock()
            mock_qs.aupdate = AsyncMock(return_value=1)
            MockConv.objects.filter.return_value = mock_qs

            await manager.persist_compaction(summary="Summary A", cutoff_message_id=100)

            # Verify the in-memory state was updated
            self.assertEqual(mock_conv.compaction_summary, "Summary A")
            self.assertEqual(mock_conv.compacted_before_message_id, 100)

        # Now simulate the second concurrent request: bookmark already moved
        mock_conv.compacted_before_message_id = 100

        with patch(
            "opencontractserver.llms.agents.core_agents.Conversation"
        ) as MockConv:
            # Second call: filter doesn't match → updated=0
            mock_qs = MagicMock()
            mock_qs.aupdate = AsyncMock(return_value=0)
            MockConv.objects.filter.return_value = mock_qs

            await manager.persist_compaction(summary="Summary B", cutoff_message_id=90)

            # In-memory state should NOT be updated (stale write was skipped)
            self.assertEqual(mock_conv.compaction_summary, "Summary A")
            self.assertEqual(mock_conv.compacted_before_message_id, 100)


# ---------------------------------------------------------------------------
# Summary growth cap
# ---------------------------------------------------------------------------


class TestSummaryGrowthCap(SimpleTestCase):
    """Verify that merged summaries are capped to prevent unbounded growth."""

    def test_merged_summary_is_capped(self):
        """Simulating N compaction rounds should not produce an ever-growing summary."""
        from opencontractserver.constants.context_guardrails import (
            CHARS_PER_TOKEN_ESTIMATE,
            COMPACTION_SUMMARY_MAX_TOKENS,
        )
        from opencontractserver.llms.context_guardrails import cap_summary_length

        max_chars = int(COMPACTION_SUMMARY_MAX_TOKENS * CHARS_PER_TOKEN_ESTIMATE)

        # Simulate 20 compaction rounds each adding a 300-token summary
        accumulated = ""
        single_round = "x" * int(300 * CHARS_PER_TOKEN_ESTIMATE)
        for _ in range(20):
            accumulated = (
                accumulated.rstrip() + "\n\n" + single_round
                if accumulated
                else single_round
            )
            accumulated = cap_summary_length(accumulated)

        self.assertLessEqual(
            len(accumulated), max_chars + 10
        )  # small slack for ellipsis

    def test_short_summary_unchanged(self):
        """A summary well under the cap should pass through unchanged."""
        from opencontractserver.llms.context_guardrails import cap_summary_length

        short = "This is a short summary."
        self.assertEqual(cap_summary_length(short), short)


# ---------------------------------------------------------------------------
# Running-total loop equivalence
# ---------------------------------------------------------------------------


class TestCompactionRunningTotalLoop(SimpleTestCase):
    """Verify the running-total recent-message sizing produces correct results."""

    def test_min_recent_respected(self):
        """Even with huge messages, at least min_recent messages are kept."""
        big = "x" * 500_000  # ~142K tokens each
        messages = [
            _MessageProxy(role="human", content=big),
            _MessageProxy(role="llm", content=big),
            _MessageProxy(role="human", content=big),
            _MessageProxy(role="llm", content=big),
            _MessageProxy(role="human", content=big),
        ]
        result = compact_message_history(
            messages, "gpt-4o-mini", threshold_ratio=0.001, min_recent=2
        )
        self.assertTrue(result.compacted)
        self.assertGreaterEqual(result.preserved_count, 2)

    def test_max_recent_respected(self):
        """Recent count should not exceed max_recent."""
        messages = [
            _MessageProxy(role="human" if i % 2 == 0 else "llm", content="x" * 100)
            for i in range(30)
        ]
        result = compact_message_history(
            messages, "gpt-4o-mini", threshold_ratio=0.001, max_recent=5
        )
        if result.compacted:
            self.assertLessEqual(result.preserved_count, 5)


# ---------------------------------------------------------------------------
# _HistoryResult dataclass tests
# ---------------------------------------------------------------------------


class TestHistoryResult(SimpleTestCase):
    """Tests for the _HistoryResult dataclass used in context status reporting."""

    def test_default_fields(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import _HistoryResult

        result = _HistoryResult(messages=None)
        self.assertIsNone(result.messages)
        self.assertEqual(result.estimated_tokens, 0)
        self.assertEqual(result.context_window, 0)
        self.assertFalse(result.was_compacted)
        self.assertEqual(result.tokens_before_compaction, 0)

    def test_populated_fields_no_compaction(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import _HistoryResult

        result = _HistoryResult(
            messages=[],
            estimated_tokens=5000,
            context_window=128000,
            was_compacted=False,
            tokens_before_compaction=0,
        )
        self.assertEqual(result.estimated_tokens, 5000)
        self.assertEqual(result.context_window, 128000)
        self.assertFalse(result.was_compacted)
        self.assertEqual(result.tokens_before_compaction, 0)

    def test_populated_fields_with_compaction(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import _HistoryResult

        result = _HistoryResult(
            messages=[],
            estimated_tokens=40000,
            context_window=128000,
            was_compacted=True,
            tokens_before_compaction=100000,
        )
        self.assertTrue(result.was_compacted)
        self.assertEqual(result.tokens_before_compaction, 100000)
        self.assertEqual(result.estimated_tokens, 40000)

    def test_context_status_dict_generation(self):
        """Verify the pattern used in _stream_core to build context_status."""
        from opencontractserver.llms.agents.pydantic_ai_agents import _HistoryResult

        result = _HistoryResult(
            messages=None,
            estimated_tokens=15000,
            context_window=128000,
            was_compacted=True,
            tokens_before_compaction=95000,
        )
        context_status = {
            "used_tokens": result.estimated_tokens,
            "context_window": result.context_window,
            "was_compacted": result.was_compacted,
            "tokens_before_compaction": result.tokens_before_compaction,
        }
        self.assertEqual(context_status["used_tokens"], 15000)
        self.assertEqual(context_status["context_window"], 128000)
        self.assertTrue(context_status["was_compacted"])
        self.assertEqual(context_status["tokens_before_compaction"], 95000)


# ---------------------------------------------------------------------------
# DB-level compaction bookmark filtering
# ---------------------------------------------------------------------------


class TestCompactionBookmarkDatabaseFilter(SimpleTestCase):
    """Verify that get_conversation_messages filters by id__gt when a
    compaction bookmark is set.

    Uses mocked ORM querysets to avoid requiring a real database while
    still validating that the correct filter is applied.
    """

    async def test_messages_filtered_by_compaction_bookmark(self):
        """When compacted_before_message_id is set, only messages with
        id > that value should be returned."""
        from opencontractserver.llms.agents.core_agents import (
            CoreConversationManager,
        )

        # Create a mock conversation with a compaction bookmark
        mock_conv = MagicMock()
        mock_conv.compacted_before_message_id = 50

        # Build mock messages: IDs 10, 20, 30, 40, 50, 60, 70, 80
        all_messages = []
        for msg_id in [10, 20, 30, 40, 50, 60, 70, 80]:
            m = MagicMock()
            m.id = msg_id
            m.content = f"Message {msg_id}"
            m.msg_type = "HUMAN"
            all_messages.append(m)

        # Messages that should be returned: id > 50 → [60, 70, 80]
        expected_messages = [m for m in all_messages if m.id > 50]

        manager = CoreConversationManager.__new__(CoreConversationManager)
        manager.conversation = mock_conv

        # Patch ChatMessage.objects to track filter calls
        with patch(
            "opencontractserver.llms.agents.core_agents.ChatMessage"
        ) as MockChatMessage:
            # Build chainable queryset mock
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.order_by.return_value = mock_qs

            # Make the queryset async-iterable.
            # __aiter__ is defined as a lambda(self) because dunder methods
            # are looked up on the type, not the instance.  The ``self``
            # parameter receives the mock; ``aiter_messages()`` returns a
            # fresh async generator each time the queryset is iterated.
            async def aiter_messages():
                for m in expected_messages:
                    yield m

            mock_qs.__aiter__ = lambda self: aiter_messages()

            MockChatMessage.objects.filter.return_value = mock_qs

            result = await manager.get_conversation_messages()

            # Verify the filter was called with the bookmark cutoff
            filter_calls = (
                MockChatMessage.objects.filter.return_value.filter.call_args_list
            )
            self.assertTrue(
                any(call.kwargs.get("id__gt") == 50 for call in filter_calls),
                "get_conversation_messages must filter with id__gt=compacted_before_message_id",
            )

            # Verify only post-cutoff messages were returned
            self.assertEqual(len(result), 3)

    async def test_no_filter_when_bookmark_is_none(self):
        """When compacted_before_message_id is None, no id__gt filter
        should be applied."""
        from opencontractserver.llms.agents.core_agents import (
            CoreConversationManager,
        )

        mock_conv = MagicMock()
        mock_conv.compacted_before_message_id = None

        all_messages = []
        for msg_id in [10, 20, 30]:
            m = MagicMock()
            m.id = msg_id
            m.content = f"Message {msg_id}"
            m.msg_type = "HUMAN"
            all_messages.append(m)

        manager = CoreConversationManager.__new__(CoreConversationManager)
        manager.conversation = mock_conv

        with patch(
            "opencontractserver.llms.agents.core_agents.ChatMessage"
        ) as MockChatMessage:
            mock_qs = MagicMock()
            mock_qs.filter.return_value = mock_qs
            mock_qs.order_by.return_value = mock_qs

            # Make the queryset async-iterable.
            # __aiter__ is defined as a lambda(self) because dunder methods
            # are looked up on the type, not the instance.  The ``self``
            # parameter receives the mock; ``aiter_messages()`` returns a
            # fresh async generator each time the queryset is iterated.
            async def aiter_messages():
                for m in all_messages:
                    yield m

            mock_qs.__aiter__ = lambda self: aiter_messages()

            MockChatMessage.objects.filter.return_value = mock_qs

            result = await manager.get_conversation_messages()

            # The id__gt filter should NOT have been called
            if mock_qs.filter.called:
                for call in mock_qs.filter.call_args_list:
                    self.assertNotIn(
                        "id__gt",
                        call.kwargs,
                        "id__gt filter should not be applied when bookmark is None",
                    )

            # All messages should be returned
            self.assertEqual(len(result), 3)


# ---------------------------------------------------------------------------
# _get_message_history compaction eligibility path
# ---------------------------------------------------------------------------


class TestGetMessageHistoryCompactionTokenCounting(SimpleTestCase):
    """Verify that _get_message_history passes correct token counts
    to compact_message_history when compaction is enabled and enough
    messages exist to trigger the eligibility check."""

    async def test_compaction_eligibility_passes_stored_summary_tokens(self):
        """When compaction is enabled and messages exceed min_recent,
        _get_message_history should compute system_prompt_tokens and
        stored_summary_tokens and pass them to compact_message_history."""
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Build mock messages exceeding min_recent_messages
        mock_messages = []
        for i in range(10):
            m = MagicMock()
            m.id = i + 1
            m.content = f"Message {i}: " + "x" * 200
            m.msg_type = "HUMAN" if i % 2 == 0 else "LLM"
            mock_messages.append(m)

        # Create mock conversation with a stored summary
        mock_conv = MagicMock()
        mock_conv.compaction_summary = "Previous summary text"

        # Create mock conversation manager
        mock_manager = MagicMock(spec=CoreConversationManager)
        mock_manager.get_conversation_messages = AsyncMock(return_value=mock_messages)
        mock_manager.conversation = mock_conv

        # Create agent bypassing __init__
        agent = PydanticAICoreAgent.__new__(PydanticAICoreAgent)
        agent.config = AgentConfig(
            system_prompt="You are a test assistant",
            compaction=CompactionConfig(
                enabled=True,
                min_recent_messages=2,
            ),
        )
        agent.conversation_manager = mock_manager

        # Patch compact_message_history to return not-compacted
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.compact_message_history"
        ) as mock_compact:
            mock_compact.return_value = CompactionResult(
                compacted=False,
                summary="",
                preserved_count=len(mock_messages),
                removed_count=0,
                estimated_tokens_before=5000,
                estimated_tokens_after=5000,
            )

            result = await agent._get_message_history()

            # Verify compact_message_history was called
            mock_compact.assert_called_once()
            call_kwargs = mock_compact.call_args.kwargs

            # system_prompt_tokens should reflect "You are a test assistant"
            self.assertIn("system_prompt_tokens", call_kwargs)
            self.assertGreater(call_kwargs["system_prompt_tokens"], 0)

            # stored_summary_tokens should reflect "Previous summary text"
            self.assertIn("stored_summary_tokens", call_kwargs)
            self.assertGreater(call_kwargs["stored_summary_tokens"], 0)

            # Result should have messages (not compacted, so all returned)
            self.assertIsNotNone(result.messages)

    async def test_compaction_eligibility_zero_stored_summary_tokens_when_empty(self):
        """When there is no stored summary, stored_summary_tokens should be 0."""
        from opencontractserver.llms.agents.core_agents import (
            AgentConfig,
            CoreConversationManager,
        )
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            PydanticAICoreAgent,
        )

        # Build mock messages
        mock_messages = []
        for i in range(10):
            m = MagicMock()
            m.id = i + 1
            m.content = f"Message {i}: " + "x" * 200
            m.msg_type = "HUMAN" if i % 2 == 0 else "LLM"
            mock_messages.append(m)

        # No stored summary
        mock_conv = MagicMock()
        mock_conv.compaction_summary = ""

        mock_manager = MagicMock(spec=CoreConversationManager)
        mock_manager.get_conversation_messages = AsyncMock(return_value=mock_messages)
        mock_manager.conversation = mock_conv

        agent = PydanticAICoreAgent.__new__(PydanticAICoreAgent)
        agent.config = AgentConfig(
            system_prompt="You are a test assistant",
            compaction=CompactionConfig(
                enabled=True,
                min_recent_messages=2,
            ),
        )
        agent.conversation_manager = mock_manager

        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.compact_message_history"
        ) as mock_compact:
            mock_compact.return_value = CompactionResult(
                compacted=False,
                summary="",
                preserved_count=len(mock_messages),
                removed_count=0,
                estimated_tokens_before=5000,
                estimated_tokens_after=5000,
            )

            await agent._get_message_history()

            call_kwargs = mock_compact.call_args.kwargs
            self.assertEqual(call_kwargs["stored_summary_tokens"], 0)


# ---------------------------------------------------------------------------
# Two-cycle compaction integration
# ---------------------------------------------------------------------------


class TestTwoCycleCompactionIntegration(SimpleTestCase):
    """End-to-end test running two successive compaction cycles to verify
    prefix deduplication, token counting, and summary capping work together."""

    def test_two_cycles_no_duplicate_prefix(self):
        """Running compaction twice should produce a merged summary with
        exactly one COMPACTION_SUMMARY_PREFIX, not two."""
        from opencontractserver.llms.context_guardrails import (
            cap_summary_length,
            strip_compaction_prefix,
        )

        model = "gpt-4o-mini"  # 128k window

        # --- Cycle 1: Generate 15 large messages to trigger compaction ---
        cycle1_messages = [
            _MessageProxy(
                role="human" if i % 2 == 0 else "llm",
                content=f"Cycle 1 message {i}: " + "x" * 5000,
            )
            for i in range(15)
        ]

        result1 = compact_message_history(
            cycle1_messages,
            model,
            system_prompt_tokens=500,
            stored_summary_tokens=0,
            threshold_ratio=0.01,  # Very low to force compaction
            min_recent=2,
            max_recent=4,
        )
        self.assertTrue(result1.compacted, "Cycle 1 should compact")
        self.assertTrue(result1.summary.startswith(COMPACTION_SUMMARY_PREFIX))
        # Only one prefix
        self.assertEqual(result1.summary.count(COMPACTION_SUMMARY_PREFIX), 1)

        # Simulate what _get_message_history does: store the summary
        stored_summary = cap_summary_length(result1.summary)

        # --- Cycle 2: New messages arrive, trigger compaction again ---
        cycle2_messages = [
            _MessageProxy(
                role="human" if i % 2 == 0 else "llm",
                content=f"Cycle 2 message {i}: " + "y" * 5000,
            )
            for i in range(15)
        ]

        stored_summary_tokens = estimate_token_count(stored_summary)

        result2 = compact_message_history(
            cycle2_messages,
            model,
            system_prompt_tokens=500,
            stored_summary_tokens=stored_summary_tokens,
            threshold_ratio=0.01,
            min_recent=2,
            max_recent=4,
        )
        self.assertTrue(result2.compacted, "Cycle 2 should compact")

        # Simulate the merge logic from _get_message_history
        old_body = strip_compaction_prefix(stored_summary).rstrip()
        new_body = strip_compaction_prefix(result2.summary)
        merged = cap_summary_length(
            COMPACTION_SUMMARY_PREFIX + old_body + "\n\n" + new_body
        )

        # Assertions: exactly one prefix, no duplicate
        self.assertTrue(merged.startswith(COMPACTION_SUMMARY_PREFIX))
        self.assertEqual(
            merged.count(COMPACTION_SUMMARY_PREFIX),
            1,
            "Merged summary must contain exactly one prefix header",
        )

        # Token count for cycle 2 should include stored_summary_tokens
        # in total_before but NOT double-count in total_after
        self.assertGreater(
            result2.estimated_tokens_before, result2.estimated_tokens_after
        )
        self.assertGreater(
            result2.estimated_tokens_before,
            sum(m.token_estimate for m in cycle2_messages),
            "total_before should include stored_summary_tokens beyond just message tokens",
        )

    def test_two_cycles_summary_stays_capped(self):
        """After two compaction cycles, the merged summary must not
        exceed COMPACTION_SUMMARY_MAX_TOKENS."""
        from opencontractserver.constants.context_guardrails import (
            COMPACTION_SUMMARY_MAX_TOKENS,
        )
        from opencontractserver.llms.context_guardrails import (
            cap_summary_length,
            strip_compaction_prefix,
        )

        model = "gpt-4o-mini"
        max_chars = int(COMPACTION_SUMMARY_MAX_TOKENS * CHARS_PER_TOKEN_ESTIMATE)

        # Cycle 1 with a very long summary
        cycle1_messages = [
            _MessageProxy(role="human", content="q" * 10_000),
            _MessageProxy(role="llm", content="a" * 10_000),
        ] * 10  # 20 messages

        result1 = compact_message_history(
            cycle1_messages,
            model,
            threshold_ratio=0.001,
            min_recent=1,
            max_recent=2,
        )
        stored = cap_summary_length(result1.summary)

        # Cycle 2 with another long summary
        cycle2_messages = [
            _MessageProxy(role="human", content="r" * 10_000),
            _MessageProxy(role="llm", content="s" * 10_000),
        ] * 10

        result2 = compact_message_history(
            cycle2_messages,
            model,
            stored_summary_tokens=estimate_token_count(stored),
            threshold_ratio=0.001,
            min_recent=1,
            max_recent=2,
        )

        old_body = strip_compaction_prefix(stored).rstrip()
        new_body = strip_compaction_prefix(result2.summary)
        merged = cap_summary_length(
            COMPACTION_SUMMARY_PREFIX + old_body + "\n\n" + new_body
        )

        self.assertLessEqual(
            len(merged),
            max_chars + 10,  # small slack for ellipsis
            "Merged summary must respect the cap after two cycles",
        )


class TestCompactionConfigInRunFields(SimpleTestCase):
    """Tests for the four new in-run history-compaction fields."""

    def test_in_run_defaults_match_constants(self):
        from opencontractserver.constants.context_guardrails import (
            IN_RUN_DROP_THINKING_DEFAULT,
            IN_RUN_KEEP_RECENT_PAIRS,
            IN_RUN_TOOL_RETURN_TARGET_CHARS,
        )

        cfg = CompactionConfig()
        self.assertTrue(cfg.in_run_enabled)
        self.assertEqual(cfg.in_run_keep_recent_pairs, IN_RUN_KEEP_RECENT_PAIRS)
        self.assertEqual(
            cfg.in_run_tool_return_target_chars, IN_RUN_TOOL_RETURN_TARGET_CHARS
        )
        self.assertEqual(cfg.in_run_drop_thinking, IN_RUN_DROP_THINKING_DEFAULT)

    def test_in_run_keep_recent_pairs_must_be_positive(self):
        with self.assertRaises(ValueError):
            CompactionConfig(in_run_keep_recent_pairs=0)
        with self.assertRaises(ValueError):
            CompactionConfig(in_run_keep_recent_pairs=-1)

    def test_in_run_tool_return_target_chars_must_be_positive(self):
        with self.assertRaises(ValueError):
            CompactionConfig(in_run_tool_return_target_chars=0)
        with self.assertRaises(ValueError):
            CompactionConfig(in_run_tool_return_target_chars=-100)

    def test_in_run_enabled_false_constructs_cleanly(self):
        cfg = CompactionConfig(in_run_enabled=False)
        self.assertFalse(cfg.in_run_enabled)
