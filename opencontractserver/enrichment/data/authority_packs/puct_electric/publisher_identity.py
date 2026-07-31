"""Publisher-specific identity derivation for PUCT Interchange records."""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from opencontractserver.pipeline.base.authority_html import stable_source_slug

_EXACT_FINAL_ORDER_TITLE_RE = re.compile(
    r"^Final Order"
    r"(?:\s+(?:in|on)\s+(?:Project|Docket|Control)"
    r"(?:\s+(?:No\.?|Number))?\s+\d+)?$",
    re.I,
)


def is_exact_puct_final_order_title(title: str) -> bool:
    """Recognize only an exact publisher final-order label.

    In particular, commentary titles such as ``Comments on Final Order`` and
    ``Memo Regarding Final Order`` are not agency orders.
    """

    normalized = " ".join(str(title).split())
    return _EXACT_FINAL_ORDER_TITLE_RE.fullmatch(normalized) is not None


def classify_puct_structured_document(
    *,
    publisher_document_type: object,
    publisher_author_role: object,
) -> tuple[str, bool]:
    """Normalize only explicit Interchange type/author-role fields."""

    document_type = " ".join(
        str(publisher_document_type or "").replace("_", " ").replace("-", " ").split()
    ).casefold()
    author_role = " ".join(
        str(publisher_author_role or "").replace("_", " ").replace("-", " ").split()
    ).casefold()
    document_kind = (
        "FINAL_ORDER"
        if document_type
        in {
            "final order",
            "commission final order",
            "final commission order",
        }
        else "FILING"
    )
    government_authored = author_role in {
        "agency",
        "commission",
        "puct",
        "public utility commission of texas",
    }
    return document_kind, government_authored


def puct_interchange_key_from_evidence(
    *,
    control_number: object,
    item_number: object = None,
    document_id: object = None,
    document_name: object = None,
    archive_member_name: object = None,
    title: object = "",
    publisher_document_type: object = None,
    publisher_author_role: object = None,
) -> str | None:
    """Derive an application key from raw Interchange listing fields."""

    control = str(control_number or "").strip()
    if not control.isdigit():
        return None
    item = str(item_number or "").strip() or None
    if item is not None and not item.isdigit():
        return None
    document = str(document_id or "").strip() or None
    filename = str(document_name or "").strip() or None
    archive_member = str(archive_member_name or "").strip() or None
    observed_title = str(title or "").strip()

    if item is not None:
        key = f"puct-project:{control}:item:{item}"
    else:
        key = f"puct-project:{control}"
    if document is not None:
        key = f"{key}:document:{stable_source_slug(document)}"
    elif item is not None and filename and PurePosixPath(filename).suffix:
        key = f"{key}:document:" f"{stable_source_slug(PurePosixPath(filename).stem)}"

    document_kind, government_authored = classify_puct_structured_document(
        publisher_document_type=publisher_document_type,
        publisher_author_role=publisher_author_role,
    )
    if document_kind == "FINAL_ORDER":
        if not government_authored or not is_exact_puct_final_order_title(
            observed_title
        ):
            # A structured type alone is not enough to promote an attachment to
            # an order.  Keep the ordinary project-item identity so discovery
            # can park and review the filing instead of silently dropping it.
            return key
        order_identity = document or item or observed_title
        key = f"puct-order:{control}:{stable_source_slug(order_identity)}"
    if archive_member is not None:
        member_digest = hashlib.sha256(archive_member.encode("utf-8")).hexdigest()[:16]
        key = f"{key}:member:{stable_source_slug(archive_member)}-{member_digest}"
    return key
