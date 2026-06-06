"""Constants for the corpus auto-branding feature.

Auto-branding generates two artifacts for a freshly-created corpus that has no
uploaded icon:

  1. A ``Readme.CAML`` article, written by an LLM agent that researches the
     corpus title/description via web search.
  2. A square logo, generated via the OpenAI Images API with a deterministic
     PIL "monogram" fallback when image generation is disabled or unavailable.

Pure configuration lives here; orchestration logic lives in
``opencontractserver/corpuses/services/branding.py`` and the image-generation
primitive in ``opencontractserver/utils/image_generation.py``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# README agent
# ---------------------------------------------------------------------------
# Tools the branding agent is allowed to use when writing the Readme.CAML
# article. ``web_search`` lets it research the collection's subject; the agent
# persists the article through ``update_corpus_description`` (creator-gated,
# routed through ``CorpusService.update_description``).
CORPUS_BRANDING_AGENT_TOOLS: tuple[str, ...] = (
    "web_search",
    "update_corpus_description",
)

# Sent as the activation turn after the system prompt (which already carries the
# full task description). Mirrors the agent-corpus-action pattern.
CORPUS_BRANDING_ACTIVATION_MESSAGE = (
    "Research this collection with web_search, then write and save its "
    "Readme.CAML article using the update_corpus_description tool."
)

# Wall-clock ceiling for the README agent turn. Without it a stalled tool call
# or hung LLM holds the Celery worker indefinitely (the task's retries don't
# help a hang). Generous enough for a web_search + write round-trip.
CORPUS_BRANDING_README_TIMEOUT_SECONDS = 180.0

# Celery task time limits — backstop covering both branding steps so a hang in
# either (or the broader run) can never pin a worker forever. Soft fires first
# (raises ``SoftTimeLimitExceeded``, caught and retried); hard is the kill line.
CORPUS_BRANDING_SOFT_TIME_LIMIT_SECONDS = 300
CORPUS_BRANDING_HARD_TIME_LIMIT_SECONDS = 360

# ---------------------------------------------------------------------------
# Logo image generation (OpenAI Images API)
# ---------------------------------------------------------------------------
OPENAI_IMAGE_ENDPOINT = "https://api.openai.com/v1/images/generations"
CORPUS_LOGO_IMAGE_MODEL = "gpt-image-1"
# Square output suitable for an icon/avatar; the smallest gpt-image-1 size.
CORPUS_LOGO_IMAGE_SIZE = "1024x1024"
CORPUS_LOGO_REQUEST_TIMEOUT_SECONDS = 90.0
CORPUS_LOGO_CONNECT_TIMEOUT_SECONDS = 10.0

# Upper bound on the free-text styling hint an agent/user may pass to the manual
# ``regenerate_corpus_icon`` tool. The hint is sanitised
# (``sanitize_plaintext_for_prompt``) and capped at this length before being
# appended to the image prompt, so a long crafted value cannot dominate the
# prompt or break out of it.
CORPUS_LOGO_ADDITIONAL_INSTRUCTIONS_MAX_CHARS = 500

# ---------------------------------------------------------------------------
# PIL monogram fallback
# ---------------------------------------------------------------------------
# Edge length (px) of the square fallback logo.
CORPUS_LOGO_FALLBACK_SIZE = 512
# Max initials rendered in the monogram.
CORPUS_LOGO_FALLBACK_MAX_INITIALS = 2
# Deterministic background palette (chosen for legibility against white text).
# A stable hash of the corpus seed selects one entry, so the same corpus always
# renders the same fallback color.
CORPUS_LOGO_FALLBACK_PALETTE: tuple[str, ...] = (
    "#2563EB",  # blue-600
    "#7C3AED",  # violet-600
    "#DB2777",  # pink-600
    "#DC2626",  # red-600
    "#EA580C",  # orange-600
    "#16A34A",  # green-600
    "#0891B2",  # cyan-600
    "#4F46E5",  # indigo-600
    "#0D9488",  # teal-600
    "#9333EA",  # purple-600
)
# Candidate TrueType fonts tried in order before falling back to PIL's bitmap
# default. DejaVuSans ships with Pillow; the others are common on Linux images.
CORPUS_LOGO_FALLBACK_FONTS: tuple[str, ...] = (
    "DejaVuSans-Bold.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
)
