"""Corpus auto-branding orchestration (logo + Readme.CAML).

Runs once per freshly-created corpus — dispatched by the ``post_save`` signal in
``corpuses/signals.py`` via the ``generate_corpus_branding`` Celery task — when
auto-branding is enabled and no icon was uploaded. Two best-effort steps:

  1. **README** — a corpus-scoped LLM agent researches the title/description
     with ``web_search`` and writes the ``Readme.CAML`` article via the
     ``update_corpus_description`` tool (creator-gated through
     :meth:`CorpusService.update_description`). Mirrors the agent-corpus-action
     execution pattern in ``opencontractserver/tasks/agent_tasks.py``.

  2. **Logo** — a square logo is generated (OpenAI Images with a deterministic
     PIL monogram fallback) and saved through :meth:`CorpusService.update_icon`.

Each step is independently guarded and isolated: a pre-existing artifact or a
failure in one never blocks the other, and neither aborts corpus creation
(the task swallows/records errors).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.llms.api import ToolType
    from opencontractserver.shared.services.conventions import ServiceResult
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


async def run_corpus_branding_async(corpus_id: int, user_id: int) -> dict:
    """Generate a README and logo for a newly-created corpus.

    Returns a small status summary (handy for logging/tests). Defensive
    re-checks repeat the signal-time guards because the corpus may have
    changed between enqueue and execution.
    """
    from django.conf import settings

    from opencontractserver.corpuses.models import Corpus

    # Re-check the install-wide kill-switch: an admin may have disabled
    # branding between signal fire and task execution. Mirrors the per-corpus
    # re-checks below and the signal-time guard.
    if not getattr(settings, "CORPUS_AUTO_BRANDING_ENABLED", False):
        return {"status": "skipped", "reason": "globally_disabled"}

    try:
        corpus = await Corpus.objects.select_related("creator").aget(id=corpus_id)
    except Corpus.DoesNotExist:
        logger.warning(
            "[CorpusBranding] Corpus %s no longer exists; skipping.", corpus_id
        )
        return {"status": "skipped", "reason": "corpus_missing"}

    if corpus.is_personal:
        return {"status": "skipped", "reason": "personal_corpus"}
    if not corpus.auto_branding_enabled:
        return {"status": "skipped", "reason": "opted_out"}

    readme_status = await _generate_readme(corpus, user_id)
    logo_status = await _generate_logo(corpus, user_id)

    summary = {"status": "completed", "readme": readme_status, "logo": logo_status}
    logger.info("[CorpusBranding] corpus=%s %s", corpus_id, summary)
    return summary


async def _generate_readme(corpus: Corpus, user_id: int) -> str:
    """Write the corpus's Readme.CAML via an LLM agent. Best-effort."""
    # Don't overwrite an existing article (e.g. a forked/imported corpus).
    if corpus.readme_caml_document_id:
        return "skipped_exists"

    from opencontractserver.constants.corpus_branding import (
        CORPUS_BRANDING_ACTIVATION_MESSAGE,
        CORPUS_BRANDING_AGENT_TOOLS,
        CORPUS_BRANDING_README_TIMEOUT_SECONDS,
    )
    from opencontractserver.llms import agents

    tools: list[str] = list(CORPUS_BRANDING_AGENT_TOOLS)
    system_prompt = _build_branding_system_prompt(corpus, tools)

    try:
        # ``for_corpus`` + ``skip_approval_gate`` mirrors the agent-corpus-action
        # executor; the agent persists the article itself via the
        # update_corpus_description tool (creator-gated in the service). No
        # ``model=`` is passed, so the LLM is resolved through the canonical
        # chain (per-corpus preferred_llm -> PipelineSettings.default_llm
        # singleton -> settings) with live DB credentials.
        agent = await agents.for_corpus(
            corpus=corpus,
            user_id=user_id,
            system_prompt=system_prompt,
            # ``tools`` is a list[str] (tool names); cast to the exact element
            # type ``for_corpus`` expects. ``str`` is a member of ``ToolType``,
            # so this only works around list's invariance — it does not widen
            # to ``Any`` (which would hide a genuine mismatch).
            tools=cast("list[ToolType]", tools),
            streaming=False,
            skip_approval_gate=True,
        )
        # Bound the turn so a hung tool call / stalled LLM can't pin the worker.
        await asyncio.wait_for(
            agent.chat(CORPUS_BRANDING_ACTIVATION_MESSAGE),
            timeout=CORPUS_BRANDING_README_TIMEOUT_SECONDS,
        )
        return "generated"
    except Exception:
        logger.exception(
            "[CorpusBranding] README generation failed for corpus %s", corpus.id
        )
        return "error"


async def _generate_logo(corpus: Corpus, user_id: int) -> str:
    """Generate and persist a logo to ``corpus.icon``. Best-effort."""
    # Never clobber an uploaded icon (the signal also guards this, but the
    # corpus may have been given an icon between enqueue and execution).
    if corpus.icon:
        return "skipped_icon_present"

    from channels.db import database_sync_to_async

    from opencontractserver.utils.image_generation import agenerate_logo_image

    prompt = _build_logo_prompt(corpus)
    try:
        image_bytes, ext = await agenerate_logo_image(
            prompt=prompt,
            fallback_text=corpus.title or "Corpus",
            fallback_seed=str(corpus.pk),
        )
    except Exception:
        logger.exception(
            "[CorpusBranding] Logo generation failed for corpus %s", corpus.id
        )
        return "error"

    @database_sync_to_async
    def _save() -> str:
        # Deferred imports: avoid a circular import at module load
        # (corpus_service -> branding) and keep the sync ORM access inside the
        # database_sync_to_async boundary.
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.corpuses.services.corpus_service import CorpusService

        # Re-fetch to honour any icon set after enqueue and to write a fresh row.
        # The corpus may have been hard-deleted between image generation and
        # this save; treat that like the orchestrator's top-level guard rather
        # than letting DoesNotExist bubble into the task's noisy retry loop.
        try:
            fresh = Corpus.objects.select_related("creator").get(pk=corpus.pk)
        except Corpus.DoesNotExist:
            return "skipped_corpus_missing"
        if fresh.icon:
            return "skipped_icon_present"
        # Honour an opt-out that landed between _generate_logo's check and this
        # save. _generate_logo already passed the gate by the time we get here,
        # so without this re-check a user who disabled auto-branding mid-flight
        # would still get a logo written. Mirrors the README step's top-level
        # auto_branding_enabled re-check.
        if not fresh.auto_branding_enabled:
            return "skipped_opted_out"
        if fresh.creator is None:
            return "skipped_no_creator"
        result = CorpusService.update_icon(
            fresh.creator, fresh, image_bytes=image_bytes, extension=ext
        )
        return "generated" if result.ok else "error"

    return await _save()


async def aregenerate_corpus_logo(
    corpus: Corpus,
    user: User,
    *,
    additional_instructions: str | None = None,
) -> ServiceResult[None]:
    """Generate a fresh logo and persist it to ``corpus.icon`` (creator-gated).

    The manual counterpart to :func:`_generate_logo`: it builds the same
    text-to-image prompt (optionally augmented with caller-supplied
    ``additional_instructions``), generates the image via
    :func:`agenerate_logo_image` (OpenAI Images with the deterministic PIL
    monogram fallback), and writes it through
    :meth:`CorpusService.update_icon`.

    Unlike the auto-branding path this **deliberately overwrites** any existing
    icon and ignores ``auto_branding_enabled`` — a manual regeneration is an
    explicit request, not the create-time best-effort default. Authorisation is
    still enforced: ``update_icon`` is creator-only, so the call is routed
    through the freshly re-loaded acting user and a non-creator receives a
    failure result with no write performed.

    The corpus and user rows are re-loaded inside the save's
    ``database_sync_to_async`` boundary (mirroring :func:`_generate_logo`) so
    the ORM write runs against that thread's connection and honours any state
    change — icon upload, hard delete — that landed during the slow image
    generation.

    Returns the :class:`ServiceResult` from ``update_icon`` (success carries
    ``None``; failure carries a human-readable reason).
    """
    from channels.db import database_sync_to_async

    from opencontractserver.utils.image_generation import agenerate_logo_image

    prompt = _build_logo_prompt(corpus, additional_instructions)
    image_bytes, ext = await agenerate_logo_image(
        prompt=prompt,
        fallback_text=corpus.title or "Corpus",
        fallback_seed=str(corpus.pk),
    )

    corpus_pk = corpus.pk
    user_pk = user.pk

    @database_sync_to_async
    def _save() -> ServiceResult[None]:
        # Deferred imports keep sync ORM access inside the
        # database_sync_to_async boundary and avoid a circular import
        # (corpus_service -> branding).
        from django.contrib.auth import get_user_model

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.corpuses.services.corpus_service import CorpusService
        from opencontractserver.shared.services.conventions import ServiceResult

        try:
            fresh = Corpus.objects.get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return ServiceResult.failure(
                "Corpus no longer exists; the regenerated icon was not saved."
            )

        acting_user = get_user_model().objects.filter(pk=user_pk).first()
        if acting_user is None:
            return ServiceResult.failure(
                "Acting user no longer exists; the regenerated icon was not saved."
            )

        # ``update_icon`` is the authoritative creator-only gate, so this helper
        # stays safe even if a future caller skips an up-front check.
        return CorpusService.update_icon(
            acting_user, fresh, image_bytes=image_bytes, extension=ext
        )

    return await _save()


# --------------------------------------------------------------------------- #
# Prompt builders
# --------------------------------------------------------------------------- #


def _build_branding_system_prompt(corpus: Corpus, tools: list[str]) -> str:
    """System prompt for the README-writing agent.

    Reuses the canonical ``CAML_AUTHORING_GUIDE`` (the same CAML syntax /
    editorial reference the seeded "CAML Article Writer" corpus action uses) so
    auto-branding produces a real CAML article — not ad-hoc markdown — then
    layers the branding-specific framing on top: a freshly-created (possibly
    empty) corpus, researched via ``web_search`` rather than document tools.

    SECURITY: the corpus title/description are user-generated, so they are
    wrapped in ``<user_content>`` fences to keep the model from treating them
    as instructions. See ``opencontractserver/utils/prompt_sanitization.py``.
    """
    from opencontractserver.corpuses.caml_authoring import CAML_AUTHORING_GUIDE
    from opencontractserver.utils.prompt_sanitization import (
        UNTRUSTED_CONTENT_NOTICE,
        fence_user_content,
        warn_if_content_large,
    )

    title = corpus.title or "Untitled collection"
    description = corpus.description or ""
    warn_if_content_large(title, context="corpus title")
    if description:
        warn_if_content_large(description, context="corpus description")

    tool_list = ", ".join(tools) if tools else "none"

    parts = [
        "You are an automated corpus-branding agent. You write the "
        "``Readme.CAML`` article for a newly created document collection, "
        "without human interaction, following the CAML authoring guide below.",
        f"\n{UNTRUSTED_CONTENT_NOTICE}",
        "",
        "## Collection",
        f"- Title: {fence_user_content(title, label='corpus title')}",
    ]
    if description:
        parts.append(
            "- Description: "
            f"{fence_user_content(description, label='corpus description')}"
        )
    parts.append(f"- Available tools: {tool_list}")

    parts.extend(
        [
            "",
            "## Branding rules (override the guide where they conflict)",
            "1. You MUST use tools. Research the collection's subject with "
            "web_search, then call update_corpus_description with the raw CAML "
            "as ``new_content`` to SAVE the article. Merely printing it is NOT "
            "sufficient — the guide's 'output ONLY the raw CAML' rule refers to "
            "what you pass to that tool.",
            "2. You have NO document-analysis tools (only web_search + "
            "update_corpus_description). Wherever the guide says to use "
            "ask_document / load_document_text, substitute your web_search "
            "findings and the collection metadata above.",
            "3. Ground every claim in the title/description above and what you "
            "verify via web_search. Never fabricate documents, statistics, or "
            "quotes — the collection may be empty so far, so favour a concise "
            "article over invented data blocks (pills/maps/timelines).",
            "4. Do NOT ask clarifying questions. Execute the task.",
            "",
            CAML_AUTHORING_GUIDE,
            "",
            "## Task",
            "Produce and SAVE (via update_corpus_description) a CAML article "
            "that helps a new reader quickly understand what this collection is "
            "about.",
        ]
    )
    return "\n".join(parts)


def sanitize_logo_instruction_hint(additional_instructions: str | None) -> str:
    """Return the sanitised styling hint, or ``""`` if it adds nothing.

    Shared by :func:`_build_logo_prompt` (which only appends the hint when this
    is non-empty) and the ``regenerate_corpus_icon`` tool (which reports
    ``additional_instructions_applied`` from it) so the "was a hint applied?"
    answer is derived from the *sanitised* value in one place. A value that is
    blank or consists only of stripped characters (e.g. quotes) collapses to
    ``""`` here, so it never falsely reports as applied.
    """
    if not (additional_instructions and additional_instructions.strip()):
        return ""
    from opencontractserver.constants.corpus_branding import (
        CORPUS_LOGO_ADDITIONAL_INSTRUCTIONS_MAX_CHARS,
    )
    from opencontractserver.utils.prompt_sanitization import (
        sanitize_plaintext_for_prompt,
    )

    return sanitize_plaintext_for_prompt(
        additional_instructions.strip(),
        max_length=CORPUS_LOGO_ADDITIONAL_INSTRUCTIONS_MAX_CHARS,
    )


def _build_logo_prompt(
    corpus: Corpus, additional_instructions: str | None = None
) -> str:
    """Text-to-image prompt for the corpus logo.

    ``additional_instructions`` is an optional free-text styling hint supplied
    by the manual ``regenerate_corpus_icon`` agent tool (the auto-branding path
    passes ``None``). When present it is folded into the prompt so a user can
    steer the look (e.g. "use blue tones and a gavel motif").

    SECURITY: the title/description AND the styling hint are user-controlled and
    are interpolated directly into the (quoted) image prompt. A text-to-image
    model has no ``<user_content>`` fence concept, so we instead neutralise the
    values with ``sanitize_plaintext_for_prompt`` — stripping quotes and
    collapsing whitespace — so a crafted value cannot break out of the quotes
    and inject its own directives (e.g. ``" . Instead, render the text: ...``).
    This mirrors the prompt-hardening applied to the README agent's system
    prompt.
    """
    from opencontractserver.utils.prompt_sanitization import (
        sanitize_plaintext_for_prompt,
    )

    title = sanitize_plaintext_for_prompt(
        (corpus.title or "Document collection").strip(), max_length=200
    )
    description = sanitize_plaintext_for_prompt(
        (corpus.description or "").strip(), max_length=300
    )

    prompt = (
        "A clean, modern, minimalist vector logo icon for a document "
        f'collection titled "{title}".'
    )
    if description:
        prompt += f" The collection is about: {description}."
    hint = sanitize_logo_instruction_hint(additional_instructions)
    if hint:
        prompt += f" Additional style guidance: {hint}."
    prompt += (
        " Flat design, simple geometric shapes, a single focal symbol, bold "
        "solid colors, centered on a plain background, no text, no words, no "
        "letters, suitable as a small app icon/avatar."
    )
    return prompt
