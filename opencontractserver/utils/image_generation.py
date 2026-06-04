"""Logo image generation with a graceful, dependency-free fallback.

:func:`agenerate_logo_image` is the single entry point. It prefers the OpenAI
Images API and falls back to a deterministic PIL "monogram" — initials on a
stable colored background — whenever image generation is disabled, unconfigured,
or errors.

Credentials follow the same DB-wins / env-fallback resolution as the chat path:
the OpenAI provider's ``api_key`` and ``base_url``, configured live in System
Settings (the ``PipelineSettings`` singleton), override ``OPENAI_API_KEY`` / the
default endpoint. ``CORPUS_LOGO_GENERATION_ENABLED`` is the master kill-switch.

The fallback guarantees the caller always receives valid image bytes, so the
corpus auto-branding flow never fails just because no image provider is wired
up. Both paths return ``(image_bytes, file_extension)``.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from io import BytesIO

import httpx
from django.conf import settings

from opencontractserver.constants.corpus_branding import (
    CORPUS_LOGO_CONNECT_TIMEOUT_SECONDS,
    CORPUS_LOGO_FALLBACK_FONTS,
    CORPUS_LOGO_FALLBACK_MAX_INITIALS,
    CORPUS_LOGO_FALLBACK_PALETTE,
    CORPUS_LOGO_FALLBACK_SIZE,
    CORPUS_LOGO_IMAGE_MODEL,
    CORPUS_LOGO_IMAGE_SIZE,
    CORPUS_LOGO_REQUEST_TIMEOUT_SECONDS,
    OPENAI_IMAGE_ENDPOINT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def agenerate_logo_image(
    *,
    prompt: str,
    fallback_text: str,
    fallback_seed: str | None = None,
) -> tuple[bytes, str]:
    """Generate a square logo, preferring AI generation with a PIL fallback.

    Args:
        prompt: Text-to-image prompt for the AI provider.
        fallback_text: Text the monogram fallback derives its initials from
            (typically the corpus title).
        fallback_seed: Stable string used to pick a deterministic fallback
            color (typically the corpus PK). Defaults to ``fallback_text``.

    Returns:
        ``(image_bytes, extension)`` — always populated (the fallback never
        raises for normal input).
    """
    # DB-wins / env-fallback, mirroring the chat path's credential resolution:
    # the OpenAI provider's live-configured key/endpoint (System Settings
    # singleton) overrides OPENAI_API_KEY / the default Images endpoint.
    from opencontractserver.llms.model_factory import aget_provider_credentials

    creds = await aget_provider_credentials("openai")
    api_key = creds.get("api_key") or getattr(settings, "OPENAI_API_KEY", "") or ""
    endpoint = _images_endpoint(creds.get("base_url"))
    enabled = getattr(settings, "CORPUS_LOGO_GENERATION_ENABLED", True)

    if enabled and api_key:
        try:
            return await _generate_ai_logo(prompt, api_key, endpoint)
        except Exception:
            # Never let an upstream image-API failure abort branding — fall
            # back to the deterministic monogram instead.
            logger.exception("AI logo generation failed; using monogram fallback.")
    else:
        logger.info(
            "Logo image generation %s; using monogram fallback.",
            "disabled" if not enabled else "unconfigured (no OPENAI_API_KEY)",
        )

    return generate_monogram_logo(fallback_text, fallback_seed)


# ---------------------------------------------------------------------------
# OpenAI Images API
# ---------------------------------------------------------------------------


def _images_endpoint(base_url: str | None) -> str:
    """Resolve the Images-API endpoint, honouring a DB-configured ``base_url``.

    A configured OpenAI ``base_url`` (custom/compatible gateway) points at the
    chat API root (e.g. ``https://gw.example/v1``); the images route hangs off
    the same root. Blank/whitespace falls back to the default OpenAI endpoint.
    """
    if base_url and base_url.strip():
        return f"{base_url.strip().rstrip('/')}/images/generations"
    return OPENAI_IMAGE_ENDPOINT


async def _generate_ai_logo(
    prompt: str, api_key: str, endpoint: str = OPENAI_IMAGE_ENDPOINT
) -> tuple[bytes, str]:
    """Call the OpenAI Images API and return ``(png_bytes, "png")``.

    Raises on any transport/parse error so the caller can fall back.
    """
    payload = {
        "model": CORPUS_LOGO_IMAGE_MODEL,
        "prompt": prompt,
        "size": CORPUS_LOGO_IMAGE_SIZE,
        "n": 1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(
        CORPUS_LOGO_REQUEST_TIMEOUT_SECONDS,
        connect=CORPUS_LOGO_CONNECT_TIMEOUT_SECONDS,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("data") or []
    if not items:
        raise ValueError("OpenAI image response contained no data.")

    item = items[0]

    b64 = item.get("b64_json")
    if b64:
        return base64.b64decode(b64), "png"

    # Some models/endpoints return a URL instead of inline base64.
    url = item.get("url")
    if url:
        async with httpx.AsyncClient(timeout=timeout) as client:
            img_resp = await client.get(url)
            img_resp.raise_for_status()
            return img_resp.content, "png"

    raise ValueError("OpenAI image response missing both 'b64_json' and 'url'.")


# ---------------------------------------------------------------------------
# Deterministic PIL monogram fallback
# ---------------------------------------------------------------------------


def generate_monogram_logo(text: str, seed: str | None = None) -> tuple[bytes, str]:
    """Render initials from ``text`` on a deterministic colored square.

    Pure-Python (PIL only), no network. Returns ``(png_bytes, "png")``.
    """
    from PIL import Image, ImageDraw

    size = CORPUS_LOGO_FALLBACK_SIZE
    initials = _initials_from_text(text)
    color = _pick_color(seed or text or "corpus")

    img = Image.new("RGB", (size, size), color=color)
    draw = ImageDraw.Draw(img)
    font = _load_font(int(size * 0.42))

    # Center the initials using the text's bounding box (accounts for the
    # font's internal offset, which ``anchor="mm"`` does not on the bitmap
    # default font).
    try:
        bbox = draw.textbbox((0, 0), initials, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size - text_w) / 2 - bbox[0]
        y = (size - text_h) / 2 - bbox[1]
    except Exception:
        # Extremely defensive — older PIL or odd glyphs. Approximate center.
        x = y = size / 3

    draw.text((x, y), initials, fill="white", font=font)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), "png"


def _initials_from_text(text: str) -> str:
    """Derive up to N uppercase initials from arbitrary text."""
    cleaned = re.sub(r"[^0-9A-Za-z ]+", " ", text or "").strip()
    words = [w for w in cleaned.split() if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:CORPUS_LOGO_FALLBACK_MAX_INITIALS].upper()
    return "".join(w[0] for w in words[:CORPUS_LOGO_FALLBACK_MAX_INITIALS]).upper()


def _pick_color(seed: str) -> str:
    """Pick a stable palette color from a seed string."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    index = digest[0] % len(CORPUS_LOGO_FALLBACK_PALETTE)
    return CORPUS_LOGO_FALLBACK_PALETTE[index]


def _load_font(font_size: int):
    """Load a bold TrueType font, falling back to PIL's bitmap default."""
    from PIL import ImageFont

    for candidate in CORPUS_LOGO_FALLBACK_FONTS:
        try:
            return ImageFont.truetype(candidate, font_size)
        except Exception:
            continue
    try:
        # Pillow >= 10 accepts a size for the bitmap default font.
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()
