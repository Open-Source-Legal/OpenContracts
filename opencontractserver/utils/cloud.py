from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def maybe_add_cloud_run_auth(
    url: str, headers: dict[str, str | bytes], force: bool = False
) -> dict[str, str | bytes]:
    """
    Attach an Authorization bearer with a Google Cloud Run identity token when applicable.
    Args:
        url: The service URL we are calling (used to derive target audience).
        headers: Existing headers to be augmented.
        force: If True, force adding IAM auth regardless of the domain.
    Returns:
        A possibly augmented headers dict. If token acquisition fails, returns original headers.
    """
    try:
        parsed = urlparse(url)
        is_cloud_run = parsed.scheme == "https" and parsed.netloc.endswith(".run.app")
        if not (is_cloud_run or force):
            return headers

        audience = f"{parsed.scheme}://{parsed.netloc}"

        # Lazy import to avoid hard dependency in non-GCP environments
        import google.auth.transport.requests
        import google.oauth2.id_token

        request = google.auth.transport.requests.Request()
        id_token = google.oauth2.id_token.fetch_id_token(request, audience)
        if id_token:
            headers["Authorization"] = f"Bearer {id_token}"
            logger.debug(
                f"Attached Google Cloud Run IAM id_token to request headers for {audience}"
            )
        else:
            logger.warning(
                f"Failed to obtain Google Cloud Run IAM id_token for {audience}"
            )
    except Exception as e:
        logger.warning(f"Cloud Run IAM auth header not added for {url}: {e}")
    return headers
