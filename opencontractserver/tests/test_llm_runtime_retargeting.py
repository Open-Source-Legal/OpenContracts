"""Runtime LLM retargeting across every remote-LLM workflow (issue #2078).

``opencontractserver/tests/test_llm_runtime_config.py`` pins the *resolver*
(``resolve_model_spec``) and the model-spec plumbing. This module pins the
thing the resolver exists for: that each production workflow which talks to a
remote LLM actually **walks** that chain, so retargeting the install to a new
model — or a whole new model family — in the System Settings UI takes effect
without restarting Django or the Celery workers.

The failure mode this guards against is silent: a workflow that reads
``settings.OPENAI_MODEL`` (deploy-time env) or a module constant still *works*,
it just keeps calling the old provider forever. Nothing errors, so only an
assertion on the resolved spec catches it.

Each test configures ``PipelineSettings.default_llm`` (the live, admin-editable
singleton) and asserts the workflow resolves to it. No LLM calls are made —
the model-build seam of each workflow is patched and inspected.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from opencontractserver.constants.extraction import DEFAULT_EXTRACT_MODEL
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import PipelineSettings

User = get_user_model()

RETARGET_SPEC = "anthropic:claude-haiku-4-5"
OTHER_SPEC = "google-gla:gemini-2.5-flash"


class RetargetingTestCase(TestCase):
    """Shared helpers for configuring the live singleton."""

    def setUp(self) -> None:
        super().setUp()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

    @staticmethod
    def set_install_default(spec: str) -> None:
        """Retarget the install the way a superuser does in System Settings.

        ``save()`` bumps ``modified`` (auto_now) and clears the singleton
        cache, which is the mechanism that makes the change visible to every
        worker process without a restart.
        """
        instance = PipelineSettings.get_instance()
        instance.default_llm = spec
        instance.save()


# ---------------------------------------------------------------------------
# Structured extraction (data_extract_tasks)
# ---------------------------------------------------------------------------


class ExtractModelResolutionTests(RetargetingTestCase):
    """``_aresolve_extract_model`` walks the full chain.

    Before #2078 this was ``model_override or DEFAULT_EXTRACT_MODEL``, so the
    constant outranked every configured tier and extraction could never be
    retargeted at all.
    """

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user(
            username="extract-retarget", password="x"  # nosec B106 - test fixture
        )
        self.corpus = Corpus.objects.create(title="Retarget", creator=self.user)

    @staticmethod
    def _resolve(model_override=None, corpus_id=None) -> str:
        from opencontractserver.tasks.data_extract_tasks import (
            _aresolve_extract_model,
        )

        return asyncio.run(_aresolve_extract_model(model_override, corpus_id))

    def test_unconfigured_install_keeps_the_legacy_default(self):
        """Nothing configured anywhere → byte-identical to the old behaviour."""
        self.assertEqual(self._resolve(), DEFAULT_EXTRACT_MODEL)

    def test_install_default_retargets_extraction(self):
        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(self._resolve(), RETARGET_SPEC)

    def test_corpus_preference_outranks_install_default(self):
        self.set_install_default(RETARGET_SPEC)
        self.corpus.preferred_llm = OTHER_SPEC
        self.corpus.save()
        self.assertEqual(self._resolve(corpus_id=self.corpus.pk), OTHER_SPEC)

    def test_explicit_override_outranks_everything(self):
        self.set_install_default(RETARGET_SPEC)
        self.corpus.preferred_llm = OTHER_SPEC
        self.corpus.save()
        self.assertEqual(
            self._resolve(model_override="openai:gpt-4o", corpus_id=self.corpus.pk),
            "openai:gpt-4o",
        )

    @override_settings(DEFAULT_LLM=RETARGET_SPEC)
    def test_django_default_llm_outranks_the_extraction_constant(self):
        """``DEFAULT_LLM`` is an install-wide statement of intent.

        It sits above ``DEFAULT_EXTRACT_MODEL``, which is only the terminal
        fallback for an install that has configured nothing.
        """
        self.assertEqual(self._resolve(), RETARGET_SPEC)

    def test_missing_corpus_falls_through_without_raising(self):
        """A datacell whose document has no corpus path resolves cleanly."""
        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(self._resolve(corpus_id=None), RETARGET_SPEC)

    def test_temperature_guard_tracks_the_retargeted_family(self):
        """Retargeting to Claude must also flip the temperature guard.

        ``_resolve_extract_temperature`` returns ``None`` for Anthropic so
        the downstream ``temperature=0`` override engages (issue #1381). That
        only works if the family it inspects is the *resolved* model, not the
        hardcoded constant.
        """
        from opencontractserver.tasks.data_extract_tasks import (
            _resolve_extract_temperature,
        )

        self.set_install_default(RETARGET_SPEC)
        self.assertIsNone(_resolve_extract_temperature(self._resolve()))


# ---------------------------------------------------------------------------
# Memory curation (memory_tasks)
# ---------------------------------------------------------------------------


class MemoryCurationModelResolutionTests(RetargetingTestCase):
    """Curation used to read ``get_default_config().model_name``.

    That is ``settings.OPENAI_MODEL`` — so an install retargeted to Anthropic
    kept billing OpenAI (and failed outright when no OpenAI key was present).
    """

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user(
            username="memory-retarget", password="x"  # nosec B106 - test fixture
        )
        self.corpus = Corpus.objects.create(
            title="Memory", creator=self.user, memory_enabled=True
        )

    def _run_curation(self) -> list[str]:
        """Run the curation task far enough to capture the resolved spec."""
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.tasks.memory_tasks import (
            _curate_corpus_memory_async,
        )

        conversation = Conversation.objects.create(
            title="c",
            creator=self.user,
            chat_with_corpus=self.corpus,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        for i in range(12):
            ChatMessage.objects.create(
                conversation=conversation,
                creator=self.user,
                msg_type="HUMAN" if i % 2 == 0 else "LLM",
                content=f"message {i}",
            )

        specs: list[str] = []

        async def _capture(spec):
            specs.append(spec)
            return spec

        agent = MagicMock()
        agent.run = AsyncMock(return_value=MagicMock(output="{}"))

        with patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            side_effect=_capture,
        ), patch(
            "opencontractserver.llms.agents.pydantic_ai_factory."
            "make_pydantic_ai_agent",
            return_value=agent,
        ):
            asyncio.run(_curate_corpus_memory_async(conversation.pk))

        return specs

    def test_curation_uses_the_install_default(self):
        self.set_install_default(RETARGET_SPEC)
        specs = self._run_curation()
        self.assertTrue(specs, "curation never reached the model-build seam")
        self.assertEqual(specs[0], RETARGET_SPEC)

    def test_corpus_preference_outranks_install_default(self):
        self.set_install_default(RETARGET_SPEC)
        self.corpus.preferred_llm = OTHER_SPEC
        self.corpus.save()
        specs = self._run_curation()
        self.assertTrue(specs, "curation never reached the model-build seam")
        self.assertEqual(specs[0], OTHER_SPEC)


# ---------------------------------------------------------------------------
# Enrichment citation extraction (llm_citation_extractor)
# ---------------------------------------------------------------------------


class CitationExtractorModelResolutionTests(RetargetingTestCase):
    """``_abuild_model`` passed ``settings_default=None``, skipping the singleton."""

    def _resolve(self, model=None) -> str:
        from opencontractserver.enrichment.llm_citation_extractor import (
            LLMCitationExtractor,
        )

        captured: list[str] = []

        async def _capture(spec):
            captured.append(spec)
            return spec

        with patch(
            "opencontractserver.enrichment.llm_citation_extractor.abuild_agent_model",
            side_effect=_capture,
        ):
            asyncio.run(LLMCitationExtractor(model=model)._abuild_model())

        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_install_default_is_honoured(self):
        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(self._resolve(), RETARGET_SPEC)

    def test_explicit_model_still_wins(self):
        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(self._resolve(model=OTHER_SPEC), OTHER_SPEC)


# ---------------------------------------------------------------------------
# Authority web locator (agentic_web_locator_provider)
# ---------------------------------------------------------------------------


class WebLocatorModelResolutionTests(RetargetingTestCase):
    """``resolve_model_spec(explicit=None)`` skipped the singleton tier."""

    def test_install_default_is_honoured(self):
        from opencontractserver.pipeline.authority_source_providers.agentic_web_locator_provider import (  # noqa: E501
            AgenticWebLocatorProvider,
            _LocatorOutput,
        )

        self.set_install_default(RETARGET_SPEC)

        captured: list[str] = []

        async def _capture(spec):
            captured.append(spec)
            return spec

        agent = MagicMock()
        agent.run = AsyncMock(
            return_value=MagicMock(
                output=_LocatorOutput(
                    found=False,
                    source_url="",
                    heading="",
                    text="",
                    confidence=0.0,
                )
            )
        )

        with patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            side_effect=_capture,
        ), patch(
            "opencontractserver.llms.agents.pydantic_ai_factory."
            "make_pydantic_ai_agent",
            return_value=agent,
        ):
            asyncio.run(
                AgenticWebLocatorProvider()._run_agent(
                    citation="15 U.S.C. § 78j", jurisdiction="us"
                )
            )

        self.assertEqual(captured, [RETARGET_SPEC])


# ---------------------------------------------------------------------------
# One-shot completions (completions.agenerate_text)
# ---------------------------------------------------------------------------


class CompletionsModelResolutionTests(RetargetingTestCase):
    """The infra-completion helper (conversation titles, …) follows the chain."""

    def _resolve(self, **kwargs) -> str:
        from opencontractserver.llms.completions import agenerate_text

        captured: list[str] = []

        async def _capture(spec):
            captured.append(spec)
            return spec

        agent = MagicMock()
        agent.run = AsyncMock(return_value=MagicMock(output="title"))

        with patch(
            "opencontractserver.llms.model_factory.abuild_agent_model",
            side_effect=_capture,
        ), patch(
            "opencontractserver.llms.agents.pydantic_ai_factory."
            "make_pydantic_ai_agent",
            return_value=agent,
        ):
            asyncio.run(agenerate_text("hi", **kwargs))

        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_install_default_is_honoured(self):
        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(self._resolve(), RETARGET_SPEC)

    def test_corpus_preference_outranks_install_default(self):
        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(self._resolve(corpus_preferred=OTHER_SPEC), OTHER_SPEC)


# ---------------------------------------------------------------------------
# Hot-swap semantics: a second retarget must be seen without a restart
# ---------------------------------------------------------------------------


class HotSwapTests(RetargetingTestCase):
    """Two retargets in one process resolve to two different models.

    This is the actual ask in #2078: the singleton is cached (Django cache,
    5-minute TTL) and so are the decrypted provider credentials
    (``model_factory._CREDENTIAL_CACHE``, keyed on
    ``PipelineSettings.modified``). Both must invalidate on write, or the
    first model a worker resolves is the only one it will ever use.
    """

    def test_successive_retargets_take_effect_in_process(self):
        from opencontractserver.pipeline.utils import get_default_llm_spec

        self.set_install_default(RETARGET_SPEC)
        self.assertEqual(get_default_llm_spec(), RETARGET_SPEC)

        self.set_install_default(OTHER_SPEC)
        self.assertEqual(get_default_llm_spec(), OTHER_SPEC)

        # Clearing it falls back through the chain rather than sticking.
        self.set_install_default("")
        self.assertEqual(get_default_llm_spec(), "")

    def test_credential_cache_invalidates_on_provider_key_rotation(self):
        """A rotated api_key is picked up without clearing any cache by hand."""
        from opencontractserver.llms.model_factory import (
            _get_db_credentials,
            invalidate_credential_cache,
        )
        from opencontractserver.pipeline.registry import (
            get_llm_provider_by_key_cached,
        )

        invalidate_credential_cache()
        self.addCleanup(invalidate_credential_cache)

        defn = get_llm_provider_by_key_cached("anthropic")
        assert defn is not None

        instance = PipelineSettings.get_instance()
        instance.set_secrets({defn.class_name: {"api_key": "key-one"}})
        instance.save()
        self.assertEqual(_get_db_credentials("anthropic").get("api_key"), "key-one")

        instance = PipelineSettings.get_instance()
        instance.set_secrets({defn.class_name: {"api_key": "key-two"}})
        instance.save()
        self.assertEqual(_get_db_credentials("anthropic").get("api_key"), "key-two")


# ---------------------------------------------------------------------------
# Context-window coverage for every model the UI offers
# ---------------------------------------------------------------------------


class ContextWindowCoverageTests(TestCase):
    """Retargeting to a small-window model must not silently disable compaction.

    ``get_context_window_for_model`` falls back to 128K for unknown names. For
    a hosted model that is a harmless under-estimate, but for a 32K local model
    it is an *over*-estimate: compaction never fires and the run dies on a hard
    context overflow. Every model the provider registry offers therefore needs
    an explicit entry (exact or prefix).
    """

    def test_every_supported_model_has_a_context_window(self):
        from opencontractserver.constants.context_guardrails import (
            DEFAULT_CONTEXT_WINDOW,
            MODEL_CONTEXT_WINDOWS,
        )
        from opencontractserver.llms.context_guardrails import (
            get_context_window_for_model,
        )
        from opencontractserver.pipeline.registry import (
            get_all_llm_providers_cached,
        )

        missing: list[str] = []
        for definition in get_all_llm_providers_cached():
            provider_cls = definition.component_class
            if provider_cls is None:
                continue
            for model in getattr(provider_cls, "supported_models", ()):
                spec = f"{provider_cls.provider_key}:{model}"
                window = get_context_window_for_model(spec)
                matched = any(
                    model.startswith(prefix) for prefix in MODEL_CONTEXT_WINDOWS
                )
                if not matched and window == DEFAULT_CONTEXT_WINDOW:
                    missing.append(spec)

        self.assertEqual(
            missing,
            [],
            "These offered models fall back to DEFAULT_CONTEXT_WINDOW. Add an "
            "entry to MODEL_CONTEXT_WINDOWS (issue #2078): "
            f"{missing}",
        )
