"""Serve the pre-built React SPA from Django for the desktop build.

The docker-compose / production topology serves the frontend from its own
container (nginx). The single-user desktop build has no such container: Daphne
serves both the API and the SPA. This catch-all serves everything under
``settings.OC_DESKTOP_SPA_ROOT`` (the built ``dist/``): a real file at the
requested path (a hashed JS/CSS asset) is streamed directly, and any other path
falls back to ``index.html`` so client-side routes (deep links) resolve.
WhiteNoise is only configured against Django's own ``STATIC_ROOT`` (admin/DRF
static), NOT the SPA dir, so asset requests are handled here, not by WhiteNoise.
It is only wired into ``urls.py`` when ``OC_DESKTOP_SPA_ROOT`` is set (i.e. the
desktop profile), so other deployments are unaffected.
"""

import logging
import os

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.utils._os import safe_join

logger = logging.getLogger(__name__)


def spa_fallback(request, resource_path: str = ""):
    """Return a static file under the SPA root, else ``index.html``.

    WhiteNoise normally serves the hashed assets before the request reaches
    Django, so in practice this view mostly returns ``index.html`` for
    client-side routes. It still resolves real files defensively (traversal is
    blocked by ``safe_join``) so the desktop build works even if WhiteNoise is
    disabled.
    """
    root = getattr(settings, "OC_DESKTOP_SPA_ROOT", "")
    if not root:
        raise Http404("SPA serving is not enabled")

    if resource_path:
        try:
            candidate = safe_join(root, resource_path)
        except (ValueError, SuspiciousFileOperation):
            candidate = None
        if candidate and os.path.isfile(candidate):
            return FileResponse(open(candidate, "rb"))

    index_path = os.path.join(root, "index.html")
    if not os.path.isfile(index_path):
        logger.error("SPA index.html not found under %s", root)
        raise Http404("SPA index.html not found")
    return FileResponse(open(index_path, "rb"), content_type="text/html")
