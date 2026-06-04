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

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)


async def run_corpus_branding_async(corpus_id: int, user_id: int) -> dict:
    """Generate a README and logo for a newly-created corpus.

    Returns a small status summary (handy for logging/tests). Defensive
    re-checks repeat the signal-time guards because the corpus may have
    changed between enqueue and execution.
    """
    from opencontractserver.corpuses.models import Corpus

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
    )
    from opencontractserver.llms import agents

    tools = list(CORPUS_BRANDING_AGENT_TOOLS)
    system_prompt = _build_branding_system_prompt(corpus, tools)

    try:
        # ``for_corpus`` + ``skip_approval_gate`` mirrors the agent-corpus-action
        # executor; the agent persists the article itself via the
        # update_corpus_description tool (creator-gated in the service).
        agent = await agents.for_corpus(
            corpus=corpus,
            user_id=user_id,
            system_prompt=system_prompt,
            tools=cast("list[Any]", tools),
            streaming=False,
            skip_approval_gate=True,
        )
        await agent.chat(CORPUS_BRANDING_ACTIVATION_MESSAGE)
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
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.corpuses.services.corpus_service import CorpusService

        # Re-fetch to honour any icon set after enqueue and to write a fresh row.
        fresh = Corpus.objects.select_related("creator").get(pk=corpus.pk)
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


# --------------------------------------------------------------------------- #
# Prompt builders
# --------------------------------------------------------------------------- #


def _build_branding_system_prompt(corpus: Corpus, tools: list[str]) -> str:
    """System prompt for the README-writing agent.

    SECURITY: the corpus title/description are user-generated, so they are
    wrapped in ``<user_content>`` fences to keep the model from treating them
    as instructions. See ``opencontractserver/utils/prompt_sanitization.py``.
    """
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
        "You are an automated corpus-branding agent. You write a concise, "
        "accurate README for a newly created document collection without human "
        "interaction.",
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
            "## Rules",
            "1. You MUST use tools. Use web_search to research the "
            "collection's subject, then call update_corpus_description to save "
            "the README. Describing what you would do is NOT sufficient.",
            "2. Do NOT ask clarifying questions. Execute the task.",
            "3. Ground the README in the title/description above and what you "
            "find via web_search. Do not fabricate documents or contents you "
            "cannot verify — the collection may be empty so far.",
            "4. Keep it concise and skimmable.",
            "",
            "## README format",
            "- Write GitHub-flavored markdown (a valid CAML article).",
            "- Start with a single H1 title.",
            "- Include a short overview paragraph, then sections such as "
            '"What\'s inside", "Key topics", and "How to use this '
            'collection".',
            "- Prefer bullet lists; link to authoritative sources you found.",
            "",
            "## Task",
            "Produce and SAVE (via update_corpus_description) a README that "
            "helps a new reader quickly understand what this collection is "
            "about.",
        ]
    )
    return "\n".join(parts)


def _build_logo_prompt(corpus: Corpus) -> str:
    """Text-to-image prompt for the corpus logo.

    SECURITY: the title/description are user-controlled and are interpolated
    directly into the (quoted) image prompt. A text-to-image model has no
    ``<user_content>`` fence concept, so we instead neutralise the values with
    ``sanitize_plaintext_for_prompt`` — stripping quotes and collapsing
    whitespace — so a crafted title cannot break out of the quotes and inject
    its own directives (e.g. ``" . Instead, render the text: ...``). This
    mirrors the prompt-hardening applied to the README agent's system prompt.
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
    prompt += (
        " Flat design, simple geometric shapes, a single focal symbol, bold "
        "solid colors, centered on a plain background, no text, no words, no "
        "letters, suitable as a small app icon/avatar."
    )
    return prompt
