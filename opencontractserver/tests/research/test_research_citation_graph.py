"""The closed-citation-graph contract for the deep-research loop (issue #2201).

``find_citable_passages`` exists so the agent can attribute what it just read
instead of hunting for a citeable id — the failure that burned a 3M-token run.
That only works if a hit's ``annotation_id`` lands in the run's
``retrieved_annotation_ids`` accumulator, because ``record_finding`` rejects any
id retrieval never produced and ``finalize`` intersects against the same set.

``_citable_passage_rows`` (the row shaping) is unit-tested in
``test_research_report_service``; this drives the *closure* bound inside
``_run_deep_research_async``, which is where the accumulator registration
actually happens. The agent factory is stubbed so no LLM is involved: the stub's
``chat`` plays the three tool calls the contract spans — retrieve, record,
finalize — and the assertions check the id survives every hop.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TransactionTestCase

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.llms import api as llms_api
from opencontractserver.research.models import ResearchReport
from opencontractserver.tasks.research_tasks import _run_deep_research_async
from opencontractserver.types.enums import JobStatus, PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

PHRASE = "maintain the premises in good repair"


class _StubDeps:
    """Stands in for ``PydanticAIDependencies`` — only the accumulator matters."""

    def __init__(self) -> None:
        self.retrieved_annotation_ids: list[int] = []


class _StubAgent:
    """Agent whose ``chat`` replays the tool sequence the contract spans."""

    def __init__(self, tools, script):
        self.agent_deps = _StubDeps()
        self._tools = {tool.__name__: tool for tool in tools}
        self._script = script

    async def chat(self, *args, **kwargs):
        await self._script(self._tools)
        return SimpleNamespace(content="stub run complete")


class CitationGraphContractTestCase(TransactionTestCase):
    """TransactionTestCase because the loop dispatches DB work through
    ``sync_to_async``; a TestCase's per-test transaction is invisible there
    (same reasoning as ``AstartDeepResearchTestCase``)."""

    def setUp(self):
        self.user = User.objects.create_user(username="graph-owner", password="x")
        self.corpus = Corpus.objects.create(title="Leases", creator=self.user)
        self.doc = Document.objects.create(
            title="Lease.pdf", creator=self.user, file_type="application/pdf"
        )
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/lease.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=self.user,
        )
        label = AnnotationLabel.objects.create(
            text="SENTENCE", label_type="TOKEN_LABEL", creator=self.user
        )
        self.annotation = Annotation.objects.create(
            annotation_label=label,
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            page=1,
            raw_text=f"The tenant shall {PHRASE} throughout the term.",
            json={},
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])
        self.report = ResearchReport.objects.create(
            creator=self.user,
            corpus=self.corpus,
            prompt="Who maintains the premises?",
            status=JobStatus.RUNNING.value,
        )

    def _drive(self, script) -> dict:
        """Run the loop with a stubbed agent that executes ``script``."""
        captured: dict = {}

        async def fake_for_corpus(**kwargs):
            captured["tools"] = kwargs["tools"]
            captured["agent"] = _StubAgent(kwargs["tools"], script)
            return captured["agent"]

        # Reload the way the Celery task does, so FK access inside the async
        # loop never triggers a lazy query on the event loop.
        report = ResearchReport.objects.select_related(
            "corpus", "creator", "conversation"
        ).get(pk=self.report.pk)
        # Patch the AgentAPI SINGLETON, not the same-named package. The loop
        # does ``from opencontractserver.llms import agents``, and
        # ``llms/__init__`` re-exports ``llms.api.agents`` — the AgentAPI()
        # instance — which shadows the ``llms.agents`` package of the same
        # name. Patching the package leaves the real factory in place, builds a
        # real agent, and sends the run at the live LLM.
        with patch.object(llms_api.agents, "for_corpus", side_effect=fake_for_corpus):
            captured["result"] = asyncio.run(_run_deep_research_async(report))
        # Fail loudly if the stub was bypassed. Without this, patching the wrong
        # object degrades into a real agent quietly reaching for a live LLM, and
        # the test fails somewhere unrelated (or, with credentials present,
        # passes for the wrong reason).
        self.assertIn(
            "agent",
            captured,
            "the agent factory was not stubbed — this run reached the real one",
        )
        return captured

    def test_retrieved_ids_register_and_are_accepted_downstream(self):
        outcome: dict = {}

        async def script(tools):
            rows = await tools["find_citable_passages"](PHRASE)
            outcome["rows"] = rows
            annotation_id = rows[0]["annotation_id"]
            # The contract: an id that find_citable_passages returned must be
            # accepted by record_finding, which rejects anything retrieval did
            # not produce.
            outcome["record"] = await tools["record_finding"](
                "The tenant must maintain the premises in good repair.",
                [annotation_id],
                "Obligations",
            )
            await tools["finalize_report"](
                "The tenant carries the repair obligation.",
                "The tenant must maintain the premises in good repair "
                f'<cite ids="{annotation_id}"/>.',
            )

        captured = self._drive(script)

        # 1. Retrieval surfaced the real annotation with a paste-ready handle.
        rows = outcome["rows"]
        self.assertEqual(rows[0]["annotation_id"], self.annotation.pk)
        self.assertEqual(rows[0]["cite"], f'<cite ids="{self.annotation.pk}"/>')

        # 2. It registered in the run's accumulator...
        self.assertIn(
            self.annotation.pk, captured["agent"].agent_deps.retrieved_annotation_ids
        )

        # 3. ...so record_finding accepted it rather than rejecting it as an id
        #    no retrieval tool produced.
        self.assertIn("Recorded finding", outcome["record"])
        self.assertNotIn("Error", outcome["record"])

        # 4. ...and finalize kept the footnote instead of dropping the citation.
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, JobStatus.COMPLETED.value)
        self.assertIn("[^1]", self.report.content)
        self.assertEqual(
            [c["annotation_id"] for c in self.report.citations], [self.annotation.pk]
        )

    def test_a_miss_returns_guidance_and_registers_nothing(self):
        outcome: dict = {}

        async def script(tools):
            outcome["miss"] = await tools["find_citable_passages"](
                "a phrase that appears in no document"
            )

        captured = self._drive(script)

        self.assertIsInstance(outcome["miss"], str)
        self.assertIn("No corpus passage contains", outcome["miss"])
        self.assertEqual(captured["agent"].agent_deps.retrieved_annotation_ids, [])
