"""Tests for TimelineBuilder tool result capture and truncation.

These tests verify the timeline builder correctly:
  - Captures tool_result entries with result content from metadata
  - Truncates results exceeding MAX_TOOL_RESULT_LENGTH
  - Handles missing tool_result metadata gracefully
  - Pairs tool_call and tool_result entries correctly
"""

from unittest import TestCase

from opencontractserver.llms.agents.core_agents import (
    FinalEvent,
    SourceEvent,
    ThoughtEvent,
)
from opencontractserver.llms.agents.timeline_utils import (
    MAX_TOOL_RESULT_LENGTH,
    TimelineBuilder,
)


class TestTimelineBuilderToolResult(TestCase):
    """Verify TimelineBuilder captures tool result content in timeline entries."""

    def setUp(self):
        self.builder = TimelineBuilder()

    def test_tool_result_with_content(self):
        """tool_result entry should include result string from metadata."""
        ev = ThoughtEvent(
            thought="Tool `similarity_search` returned a result.",
            metadata={
                "tool_name": "similarity_search",
                "tool_result": "Found 5 matching annotations",
            },
        )
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "tool_result")
        self.assertEqual(entries[0]["tool"], "similarity_search")
        self.assertEqual(entries[0]["result"], "Found 5 matching annotations")

    def test_tool_result_without_content(self):
        """tool_result entry should omit result key when metadata has no tool_result."""
        ev = ThoughtEvent(
            thought="Tool `my_tool` returned a result.",
            metadata={"tool_name": "my_tool"},
        )
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "tool_result")
        self.assertEqual(entries[0]["tool"], "my_tool")
        self.assertNotIn("result", entries[0])

    def test_tool_result_truncation(self):
        """Results exceeding MAX_TOOL_RESULT_LENGTH should be truncated with info."""
        original_len = MAX_TOOL_RESULT_LENGTH + 100
        long_result = "x" * original_len
        ev = ThoughtEvent(
            thought="Tool `long_output` returned a result.",
            metadata={
                "tool_name": "long_output",
                "tool_result": long_result,
            },
        )
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        result = entries[0]["result"]
        # Should start with MAX_TOOL_RESULT_LENGTH chars of content
        self.assertTrue(result.startswith("x" * MAX_TOOL_RESULT_LENGTH))
        # Should include truncation indicator with original length
        self.assertIn(f"truncated from {original_len} chars", result)

    def test_tool_result_at_exact_limit(self):
        """Results at exactly MAX_TOOL_RESULT_LENGTH should NOT be truncated."""
        exact_result = "y" * MAX_TOOL_RESULT_LENGTH
        ev = ThoughtEvent(
            thought="Tool `exact_fit` returned a result.",
            metadata={
                "tool_name": "exact_fit",
                "tool_result": exact_result,
            },
        )
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(entries[0]["result"], exact_result)

    def test_tool_call_entry_preserved(self):
        """tool_call entries should still include tool name and args."""
        ev = ThoughtEvent(
            thought="Calling tool `search_exact_text`",
            metadata={
                "tool_name": "search_exact_text",
                "args": {"query": "payment terms", "top_k": 5},
            },
        )
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "tool_call")
        self.assertEqual(entries[0]["tool"], "search_exact_text")
        self.assertEqual(entries[0]["args"]["query"], "payment terms")

    def test_tool_call_and_result_pair(self):
        """A tool_call followed by tool_result should produce two paired entries."""
        call_ev = ThoughtEvent(
            thought="Calling tool `similarity_search`",
            metadata={
                "tool_name": "similarity_search",
                "args": {"query": "test"},
            },
        )
        result_ev = ThoughtEvent(
            thought="Tool `similarity_search` returned a result.",
            metadata={
                "tool_name": "similarity_search",
                "tool_result": "Found 3 matching annotations",
            },
        )
        self.builder.add(call_ev)
        self.builder.add(result_ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["type"], "tool_call")
        self.assertEqual(entries[0]["tool"], "similarity_search")
        self.assertEqual(entries[1]["type"], "tool_result")
        self.assertEqual(entries[1]["tool"], "similarity_search")
        self.assertEqual(entries[1]["result"], "Found 3 matching annotations")

    def test_multiple_calls_to_same_tool(self):
        """Multiple calls to the same tool should produce separate call/result pairs."""
        for query in ["payment", "liability"]:
            call_ev = ThoughtEvent(
                thought="Calling tool `similarity_search`",
                metadata={
                    "tool_name": "similarity_search",
                    "args": {"query": query},
                },
            )
            result_ev = ThoughtEvent(
                thought="Tool `similarity_search` returned a result.",
                metadata={
                    "tool_name": "similarity_search",
                    "tool_result": f"Found results for {query}",
                },
            )
            self.builder.add(call_ev)
            self.builder.add(result_ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 4)
        self.assertEqual(entries[0]["type"], "tool_call")
        self.assertEqual(entries[0]["args"]["query"], "payment")
        self.assertEqual(entries[1]["type"], "tool_result")
        self.assertEqual(entries[1]["result"], "Found results for payment")
        self.assertEqual(entries[2]["type"], "tool_call")
        self.assertEqual(entries[2]["args"]["query"], "liability")
        self.assertEqual(entries[3]["type"], "tool_result")
        self.assertEqual(entries[3]["result"], "Found results for liability")

    def test_source_event(self):
        """SourceEvent should produce a sources entry with count."""
        from unittest.mock import MagicMock

        source1 = MagicMock()
        source2 = MagicMock()
        ev = SourceEvent(sources=[source1, source2])
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "sources")
        self.assertEqual(entries[0]["count"], 2)

    def test_final_event(self):
        """FinalEvent should produce a status entry."""
        ev = FinalEvent(content="done")
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "status")
        self.assertEqual(entries[0]["msg"], "run_finished")

    def test_regular_thought_event(self):
        """Regular ThoughtEvent without tool metadata should produce a thought entry."""
        ev = ThoughtEvent(thought="Analyzing the document structure")
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["type"], "thought")
        self.assertEqual(entries[0]["text"], "Analyzing the document structure")

    def test_reset_clears_timeline(self):
        """reset() should clear all accumulated entries."""
        ev = ThoughtEvent(thought="test")
        self.builder.add(ev)
        self.assertEqual(len(self.builder.timeline), 1)

        self.builder.reset()
        self.assertEqual(len(self.builder.timeline), 0)

    def test_dict_passthrough(self):
        """Pre-constructed dicts should be appended verbatim."""
        entry = {"type": "tool_result", "tool": "foo", "result": "bar"}
        self.builder.add(entry)

        self.assertEqual(self.builder.timeline[0], entry)

    def test_non_string_tool_result_converted(self):
        """Non-string tool_result values should be converted via str()."""
        ev = ThoughtEvent(
            thought="Tool `counter` returned a result.",
            metadata={
                "tool_name": "counter",
                "tool_result": 42,
            },
        )
        self.builder.add(ev)

        entries = self.builder.timeline
        self.assertEqual(entries[0]["result"], "42")
