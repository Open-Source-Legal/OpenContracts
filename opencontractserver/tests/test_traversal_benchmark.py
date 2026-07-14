"""Tests for the traversal A/B benchmark harness.

The harness (``opencontractserver/benchmarks/traversal_benchmark.py``) makes real
LLM calls in production use, so the orchestration is exercised here with a
*mocked* agent. The deterministic reporting/parsing helpers need no DB or LLM
and are unit-tested directly.
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TransactionTestCase

from opencontractserver.benchmarks import traversal_benchmark as tb
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms import agents as agents_api

User = get_user_model()


# --------------------------------------------------------------------------- #
# A canned agent so the orchestration runs without a real LLM.                 #
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, content: str):
        self.content = content
        self.sources: list = []
        self.metadata = {
            "usage": {"total_tokens": 123},
            "timeline": [
                {"type": "tool_call", "tool": "similarity_search"},
                {"type": "tool_result", "tool": "similarity_search"},
                {"type": "tool_call", "tool": "get_document_references"},
            ],
        }


class _FakeAgent:
    def __init__(self, content: str, raise_on_chat: bool):
        self._content = content
        self._raise = raise_on_chat

    async def chat(self, question: str):
        if self._raise:
            raise RuntimeError("boom")
        return _FakeResponse(self._content)


def _make_fake_for_corpus(content="Section 145 of the DGCL governs.", raise_=False):
    async def _fake_for_corpus(corpus, **kwargs):
        return _FakeAgent(content, raise_)

    return _fake_for_corpus


class TraversalBenchmarkHelperTests(SimpleTestCase):
    """Pure reporting/parsing helpers — no DB, no LLM."""

    def test_load_questions_from_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "q.yaml"
            path.write_text(
                "questions:\n"
                "  - label: q1\n"
                "    corpus_id: 7\n"
                "    question: What governs indemnification?\n"
                "    expected_keys: [dgcl:145]\n",
                encoding="utf-8",
            )
            questions = tb.load_questions(path)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].corpus_id, 7)
        self.assertEqual(questions[0].expected_keys, ["dgcl:145"])

    def test_usage_tokens_variants(self):
        self.assertEqual(tb._usage_tokens({"total_tokens": 50}), 50)
        self.assertEqual(
            tb._usage_tokens({"request_tokens": 10, "response_tokens": 5}), 15
        )
        self.assertIsNone(tb._usage_tokens(None))
        self.assertIsNone(tb._usage_tokens({}))

    def test_key_grounded(self):
        self.assertTrue(tb._key_grounded("dgcl:145", "see dgcl:145 here", ""))
        # Prose "Section 145" grounds via the citation-token-adjacent number.
        self.assertTrue(tb._key_grounded("dgcl:145", "under Section 145", ""))
        self.assertTrue(tb._key_grounded("dgcl:145", "per § 145 thereof", ""))
        self.assertFalse(tb._key_grounded("dgcl:145", "unrelated text", ""))
        # A bare number without a citation token must NOT ground (page number,
        # unrelated figure) — the tightened metric's whole point.
        self.assertFalse(tb._key_grounded("dgcl:145", "the total was 145 units", ""))
        self.assertFalse(tb._key_grounded("dgcl:145", "see page 145", ""))
        # Adjacent-but-longer number must not partial-match.
        self.assertFalse(tb._key_grounded("dgcl:145", "section 1450 applies", ""))

    def test_mean(self):
        self.assertEqual(tb._mean([1.0, 2.0, 3.0]), 2.0)
        self.assertIsNone(tb._mean([]))

    def test_summarize_and_render(self):
        results = [
            tb.RunResult(
                config=tb.CONFIG_HEAVY_RAG,
                label="a",
                tokens=100,
                tool_call_count=1,
                latency_s=0.5,
                grounding_hit_rate=0.0,
                expected_key_count=1,
            ),
            tb.RunResult(
                config=tb.CONFIG_RAG_TRAVERSAL,
                label="a",
                tokens=200,
                tool_call_count=3,
                latency_s=1.0,
                grounding_hit_rate=1.0,
                grounded_keys=["dgcl:145"],
                expected_key_count=1,
            ),
            tb.RunResult(
                config=tb.CONFIG_RAG_TRAVERSAL, label="b", error="corpus x not found"
            ),
        ]
        summary = tb.summarize(results)
        self.assertEqual(summary[tb.CONFIG_HEAVY_RAG]["runs"], 1)
        self.assertEqual(summary[tb.CONFIG_RAG_TRAVERSAL]["errors"], 1)
        self.assertEqual(
            summary[tb.CONFIG_RAG_TRAVERSAL]["mean_grounding_hit_rate"], 1.0
        )

        md = tb.render_markdown(results)
        self.assertIn("Traversal benchmark", md)
        self.assertIn(tb.CONFIG_RAG_TRAVERSAL, md)

    def test_write_report(self):
        results = [
            tb.RunResult(config=tb.CONFIG_HEAVY_RAG, label="a", tokens=1, latency_s=0.1)
        ]
        with tempfile.TemporaryDirectory() as d:
            out = tb.write_report(results, d)
            self.assertTrue((out / "report.md").exists())
            payload = json.loads((out / "report.json").read_text())
        self.assertIn("summary", payload)
        self.assertEqual(len(payload["results"]), 1)


class TraversalBenchmarkRunTests(TransactionTestCase):
    """Orchestration + command, with the agent mocked.

    TransactionTestCase (not TestCase) so the corpus row is committed and visible
    to the async ORM call inside ``run_one`` running on the async thread.
    """

    def setUp(self):
        # Only a corpus is needed: run_one resolves Corpus.objects.aget(pk=...)
        # and everything downstream (for_corpus, chat) is mocked, so no documents
        # (and no on-commit parse tasks) are involved.
        self.user = User.objects.create_user(username="bench", password="p")
        self.corpus = Corpus.objects.create(title="Bench Corpus", creator=self.user)

    def test_run_one_success(self):
        question = tb.TraversalQuestion(
            corpus_id=self.corpus.id,
            question="What governs indemnification?",
            label="q1",
            expected_keys=["dgcl:145"],
        )
        with mock.patch.object(agents_api, "for_corpus", _make_fake_for_corpus()):
            result = async_to_sync(tb.run_one)(
                question, tb.CONFIG_RAG_TRAVERSAL, user_id=self.user.id, model=None
            )
        self.assertEqual(result.error, "")
        self.assertEqual(result.tokens, 123)
        self.assertEqual(result.tool_call_count, 2)  # two tool_call timeline entries
        self.assertEqual(result.grounding_hit_rate, 1.0)

    def test_run_one_corpus_not_found(self):
        question = tb.TraversalQuestion(corpus_id=99999, question="?", label="missing")
        with mock.patch.object(agents_api, "for_corpus", _make_fake_for_corpus()):
            result = async_to_sync(tb.run_one)(
                question, tb.CONFIG_HEAVY_RAG, user_id=self.user.id, model=None
            )
        self.assertIn("not found", result.error)

    def test_run_one_chat_raises_is_captured(self):
        question = tb.TraversalQuestion(
            corpus_id=self.corpus.id, question="?", label="boom"
        )
        with mock.patch.object(
            agents_api, "for_corpus", _make_fake_for_corpus(raise_=True)
        ):
            result = async_to_sync(tb.run_one)(
                question, tb.CONFIG_HEAVY_RAG, user_id=self.user.id, model=None
            )
        self.assertIn("RuntimeError", result.error)

    def test_run_benchmark_traversal_runs_both_configs(self):
        questions = [
            tb.TraversalQuestion(corpus_id=self.corpus.id, question="?", label="q1")
        ]
        with mock.patch.object(agents_api, "for_corpus", _make_fake_for_corpus()):
            results = async_to_sync(tb.run_benchmark_traversal)(
                questions, user_id=self.user.id, model=None
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(
            {r.config for r in results},
            {tb.CONFIG_HEAVY_RAG, tb.CONFIG_RAG_TRAVERSAL},
        )

    def test_management_command(self):
        with tempfile.TemporaryDirectory() as d:
            qpath = Path(d) / "q.yaml"
            qpath.write_text(
                "questions:\n"
                f"  - {{corpus_id: {self.corpus.id}, question: '?', label: q1}}\n",
                encoding="utf-8",
            )
            out = StringIO()
            with mock.patch.object(agents_api, "for_corpus", _make_fake_for_corpus()):
                call_command(
                    "benchmark_traversal",
                    "--questions",
                    str(qpath),
                    "--user",
                    self.user.username,
                    "--run-dir",
                    str(Path(d) / "run"),
                    stdout=out,
                )
            self.assertTrue((Path(d) / "run" / "report.md").exists())
        self.assertIn("Traversal benchmark", out.getvalue())
