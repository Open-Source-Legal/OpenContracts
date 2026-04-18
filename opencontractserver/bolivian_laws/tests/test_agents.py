"""Tests for the specialist + orchestrator agent layer.

These tests exercise the orchestration glue (source tagging, area
routing) without spinning up real LLM calls — the underlying
``oc_agents.for_corpus`` and pydantic_ai ``Agent`` are patched.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.bolivian_laws.constants import LegalArea
from opencontractserver.bolivian_laws.services.agents import (
    OrchestratorResponse,
    ask_specialists,
    consult_specialist,
)
from opencontractserver.bolivian_laws.services.ingestion import ensure_area_corpus

User = get_user_model()


@dataclass
class _FakeSource:
    content: str
    metadata: dict = field(default_factory=dict)
    similarity_score: float = 0.9


@dataclass
class _FakeResponse:
    content: str
    sources: list = field(default_factory=list)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSpecialistConsultation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="bl_agent_admin",
            password="testpass123",
            email="bl_agent@test.com",
        )
        # Pre-create the area corpus so the agent layer finds it.
        ensure_area_corpus(LegalArea.PENAL, user=cls.user)

    def test_consult_specialist_tags_sources_with_area(self):
        fake_agent = MagicMock()
        fake_agent.chat = AsyncMock(
            return_value=_FakeResponse(
                content="Respuesta penal.",
                sources=[
                    _FakeSource(content="art. 263 CP", metadata={"document_id": 42})
                ],
            )
        )
        with patch(
            "opencontractserver.bolivian_laws.services.agents.oc_agents.for_corpus",
            new=AsyncMock(return_value=fake_agent),
        ):
            answer, sources = _run(
                consult_specialist(LegalArea.PENAL.value, "¿Qué dice el art. 263?")
            )
        self.assertEqual(answer, "Respuesta penal.")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].area, "penal")
        self.assertEqual(sources[0].document_id, 42)
        self.assertIn("263", sources[0].snippet)

    def test_consult_specialist_handles_missing_corpus(self):
        # Civil corpus was never created.
        answer, sources = _run(
            consult_specialist(LegalArea.CIVIL.value, "Pregunta cualquiera")
        )
        self.assertIn("Sin corpus disponible", answer)
        self.assertEqual(sources, [])


class TestAskSpecialistsParallel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="bl_parallel_admin",
            password="testpass123",
            email="bl_parallel@test.com",
        )
        ensure_area_corpus(LegalArea.PENAL, user=cls.user)
        ensure_area_corpus(LegalArea.CONSTITUCIONAL, user=cls.user)

    def test_aggregates_answers_from_multiple_specialists(self):
        async def _fake_for_corpus(corpus, **kwargs) -> Any:
            agent = MagicMock()
            # Return area-specific answer based on the system prompt
            sp = kwargs.get("system_prompt", "")
            if "constitucional" in sp.lower():
                agent.chat = AsyncMock(
                    return_value=_FakeResponse(
                        content="Constitucional dice X.",
                        sources=[_FakeSource(content="Art. 14 CPE")],
                    )
                )
            else:
                agent.chat = AsyncMock(
                    return_value=_FakeResponse(
                        content="Penal dice Y.",
                        sources=[_FakeSource(content="Art. 263 CP")],
                    )
                )
            return agent

        with patch(
            "opencontractserver.bolivian_laws.services.agents.oc_agents.for_corpus",
            new=_fake_for_corpus,
        ):
            response: OrchestratorResponse = _run(
                ask_specialists(
                    [LegalArea.CONSTITUCIONAL.value, LegalArea.PENAL.value],
                    "Caso de detención sin orden",
                )
            )
        self.assertIn("Constitucional dice X.", response.answer)
        self.assertIn("Penal dice Y.", response.answer)
        self.assertEqual(set(response.consulted_areas), {"constitucional", "penal"})
        self.assertEqual(len(response.sources), 2)
        self.assertEqual(
            {s.area for s in response.sources}, {"constitucional", "penal"}
        )
