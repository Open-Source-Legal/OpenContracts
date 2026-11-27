"""Shared HTTP helpers for REST parser clients that POST a whole PDF to a service.

Used by :class:`~opencontractserver.pipeline.parsers.warp_ingest_parser.WarpIngestParser`
and :class:`~opencontractserver.pipeline.parsers.liteparse_parser.LiteParseParser`.
Each client keeps its own ``requests.post`` call (so its tests patch its own
module); these helpers turn the outcome into a classified
:class:`DocumentParsingError` with one consistent message format.
"""

import logging
import re
from typing import Any, Optional

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.pipeline.base.exceptions import (
    DocumentParsingError,
    is_transient_http_status,
)

logger = logging.getLogger(__name__)

# How much of an error response body is quoted into the error message.
_ERROR_BODY_PREVIEW_CHARS = 500


def safe_pdf_filename(title: Optional[str], doc_id: int) -> str:
    """Build a safe multipart filename ending in ``.pdf``.

    ``document.title`` is user-controlled and flows into the multipart
    part's ``Content-Disposition`` header, so strip CR/LF, other control
    characters, quotes and path separators that could smuggle header-like
    content into that MIME part (defense-in-depth; modern urllib3 also
    guards this). Falls back to ``doc_{id}.pdf`` when the title is empty or
    sanitizes to nothing.
    """
    raw = (title or "").strip()
    # Replace control chars (incl. CR/LF via \x00-\x1f), DEL, quotes and
    # path separators — anything that could break out of the header value.
    cleaned = re.sub(r'[\x00-\x1f\x7f"\\/]+', "_", raw).strip("_ ").strip()
    if not cleaned:
        cleaned = f"doc_{doc_id}"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned


def parser_service_request_error(
    error: RequestException,
    *,
    service_name: str,
    service_url: str,
    timeout: int,
    doc_id: int,
) -> DocumentParsingError:
    """Classify a failed parser-service request; returns (does not raise) the error.

    Timeouts and connection failures are transient. HTTP errors are permanent
    for 4xx except 408/429 (service busy), transient for 5xx. A
    ``RequestException`` with no response attached is treated as transient.
    """
    if isinstance(error, Timeout):
        msg = (
            f"Request to {service_name} parser service timed out after "
            f"{timeout}s for document {doc_id}"
        )
        is_transient = True
    elif isinstance(error, ConnectionError):
        msg = (
            f"Failed to connect to {service_name} parser service at "
            f"{service_url} for document {doc_id}"
        )
        is_transient = True
    else:
        is_transient = True
        status_code = None
        response_text = ""
        response = getattr(error, "response", None)
        if response is not None:
            status_code = response.status_code
            response_text = response.text[:_ERROR_BODY_PREVIEW_CHARS]
            is_transient = is_transient_http_status(status_code)

        msg = (
            f"Request to {service_name} parser service failed for document "
            f"{doc_id}: {error}"
        )
        if status_code:
            msg += f" (status={status_code})"
        if response_text:
            msg += f" - Response: {response_text}"

    logger.error(msg)
    return DocumentParsingError(msg, is_transient=is_transient)


def decode_parser_service_json(
    response: requests.Response, *, service_name: str, doc_id: int
) -> Any:
    """Decode a parser service's JSON body.

    A 200 with a truncated/corrupt body would otherwise raise a raw,
    unclassified ``JSONDecodeError``; wrap it as a transient
    :class:`DocumentParsingError` like every other failure path.
    """
    try:
        return response.json()
    except ValueError as e:
        msg = (
            f"{service_name} returned a malformed (non-JSON) response for "
            f"document {doc_id}: {e}"
        )
        logger.error(msg)
        raise DocumentParsingError(msg, is_transient=True)
