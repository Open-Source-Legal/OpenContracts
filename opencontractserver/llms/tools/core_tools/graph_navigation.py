"""Read-only *navigation* tools over the materialised reference graph.

The enrichment engine (``opencontractserver/enrichment/``) already resolves the
citations inside contracts into a real cross-document / cross-corpus /
external-law graph: ``CorpusReference`` edges, authority corpuses (one
``Document`` per statute section keyed by ``custom_meta.canonical_key``),
``DocumentRelationship`` rollups, and the assembled ``GovernanceGraphService``.

Every *existing* enrichment agent tool (``scan_corpus_references``,
``apply_corpus_reference_enrichment``, ``discover_authorities``,
``crawl_authorities``…) *builds* that graph. This module adds the missing
half: read-only primitives that let an agent **walk** the graph one hop at a
time, mid-reasoning — the "contracts-as-codebase" loop::

    similarity_search          → find the relevant clause          (existing)
    get_document_references     → what laws/contracts does it cite?
    read_reference_target       → open the cited statute/contract, read it
    find_documents_citing       → who else relies on this authority/document?
    get_reference_neighborhood  → orient: the local governance map

All tools are **read-only** (no approval gate) and route exclusively through the
permission-aware service layer, so they inherit
``MIN(document_permission, corpus_permission)`` visibility for free (CLAUDE.md
rule #7 — no inline ``visible_to_user``). ``corpus_id`` / ``document_id`` /
``user_id`` are injected from agent context and hidden from the LLM in a
*document* agent; in a *corpus* agent ``document_id`` becomes an LLM-supplied
target and the service's ``visible_to_user`` filter is the IDOR guard.
"""

from __future__ import annotations

from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C

from ._helpers import _db_sync_to_async, clamp_limit, get_user_or_none


# --------------------------------------------------------------------------- #
# Serialisation helpers                                                        #
# --------------------------------------------------------------------------- #
def _snippet(annotation) -> str:
    """The citing clause text, bounded to ``NAV_SNIPPET_MAX_CHARS``."""
    if annotation is None:
        return ""
    text = (annotation.raw_text or "").strip()
    if len(text) > C.NAV_SNIPPET_MAX_CHARS:
        return text[: C.NAV_SNIPPET_MAX_CHARS].rstrip() + "…"
    return text


def _serialize_outbound(ref) -> dict:
    """A citation *this* document makes (outbound edge)."""
    src = ref.source_annotation
    return {
        "reference_type": ref.reference_type,
        "canonical_key": ref.canonical_key,
        "resolution_status": ref.resolution_status,
        "jurisdiction": ref.jurisdiction,
        "authority_type": ref.authority_type,
        "citing_annotation_id": src.pk if src else None,
        "citing_page": getattr(src, "page", None),
        "citing_text": _snippet(src),
        "target_document_id": ref.target_document_id,
        "target_corpus_id": ref.target_corpus_id,
        "target_document_title": (
            ref.target_document.title if ref.target_document_id else None
        ),
    }


def _serialize_inbound(ref) -> dict:
    """A citation made *to* this document by some other document (inbound edge)."""
    src = ref.source_annotation
    src_doc = src.document if src else None
    return {
        "reference_type": ref.reference_type,
        "canonical_key": ref.canonical_key,
        "resolution_status": ref.resolution_status,
        "citing_corpus_id": ref.corpus_id,
        "citing_document_id": src_doc.pk if src_doc else None,
        "citing_document_title": src_doc.title if src_doc else None,
        "citing_annotation_id": src.pk if src else None,
        "citing_text": _snippet(src),
    }


def _read_document_text(doc: Document) -> str:
    """Plain text of a target document (text extract, or PDF token layer)."""
    from opencontractserver.utils.files import read_field_file_text

    if doc.txt_extract_file:
        # errors="replace": a few undecodable bytes must not crash a read hop.
        return read_field_file_text(doc.txt_extract_file, errors="replace")
    if doc.pawls_parse_file:
        import json

        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        with doc.pawls_parse_file.open("r") as f:
            tokens = expand_pawls_pages(json.load(f))
        return build_translation_layer(tokens).doc_text
    return ""


# --------------------------------------------------------------------------- #
# Tool 1 — what does this document cite? (see the imports)                      #
# --------------------------------------------------------------------------- #
def get_document_references(
    *,
    corpus_id: int,
    user_id: int,
    document_id: int | None = None,
    direction: str = "both",
    limit: int | None = None,
) -> dict:
    """List the references a document makes and receives (read-only).

    Like reading the import list and the callers of a source file. ``outbound``
    are the laws / contracts / sections THIS document cites (with the citing
    clause text, the resolved ``target_document_id`` when known, and
    ``resolution_status``); ``inbound`` are other documents that cite THIS one.

    A citation whose target has not yet been ingested shows
    ``resolution_status="EXTERNAL"`` and a ``canonical_key`` (e.g. ``dgcl:145``)
    with no ``target_document_id`` — read it with ``read_reference_target`` or
    surface it via ``list_wanted_authorities``.
    """
    from opencontractserver.enrichment.services import CorpusReferenceService

    if document_id is None:
        return {
            "error": (
                "get_document_references needs a document_id. In a corpus agent, "
                "pass the id of the document whose references you want."
            ),
            "outbound": [],
            "inbound": [],
        }

    user = get_user_or_none(user_id)
    limit = clamp_limit(limit, C.NAV_DEFAULT_MAX_REFERENCES, C.NAV_MAX_REFERENCES)
    if direction not in ("outbound", "inbound", "both"):
        direction = "both"

    base = CorpusReferenceService.visible_to_user(user)
    result: dict = {
        "document_id": document_id,
        "corpus_id": corpus_id,
        "direction": direction,
        "outbound": [],
        "inbound": [],
    }

    if direction in ("outbound", "both"):
        out_qs = (
            base.filter(source_annotation__document_id=document_id)
            .select_related("source_annotation", "target_document")
            .order_by("-detection_confidence", "id")[:limit]
        )
        result["outbound"] = [_serialize_outbound(r) for r in out_qs]

    if direction in ("inbound", "both"):
        in_qs = (
            base.filter(target_document_id=document_id)
            .select_related("source_annotation", "source_annotation__document")
            .order_by("-detection_confidence", "id")[:limit]
        )
        result["inbound"] = [_serialize_inbound(r) for r in in_qs]

    result["outbound_count"] = len(result["outbound"])
    result["inbound_count"] = len(result["inbound"])
    return result


# --------------------------------------------------------------------------- #
# Tool 2 — open the cited authority / contract and read it (open the file)      #
# --------------------------------------------------------------------------- #
def read_reference_target(
    *,
    corpus_id: int,
    user_id: int,
    canonical_key: str | None = None,
    target_document_id: int | None = None,
    char_offset: int = 0,
    max_chars: int | None = None,
) -> dict:
    """Resolve a citation to its target document and read its text (read-only).

    The "open the file" hop. Pass a ``canonical_key`` (e.g. ``dgcl:145`` — a law
    citation surfaced by ``get_document_references``) or a ``target_document_id``
    (another contract / exhibit). Follows subsection→section fallbacks and
    cross-namespace equivalences (``exchange-act:10(b)`` → the USC document).

    Returns a bounded window of the target's text (``char_offset`` /
    ``max_chars`` for paging). If the target is an external authority not yet
    ingested, ``resolved`` is ``False`` — try ``list_wanted_authorities`` /
    ``discover_authorities`` to bring it in.
    """
    from opencontractserver.enrichment.authorities import find_authority_target

    if not canonical_key and target_document_id is None:
        return {
            "resolved": False,
            "error": "Provide either canonical_key or target_document_id.",
        }

    user = get_user_or_none(user_id)
    max_chars = clamp_limit(
        max_chars, C.NAV_TARGET_TEXT_MAX_CHARS, C.NAV_TARGET_TEXT_MAX_CHARS
    )

    doc: Document | None = None
    if target_document_id is not None:
        doc = (
            Document.objects.visible_to_user(user).filter(pk=target_document_id).first()
        )
    if doc is None and canonical_key:
        doc = find_authority_target(canonical_key, user)

    if doc is None:
        return {
            "resolved": False,
            "canonical_key": canonical_key,
            "target_document_id": target_document_id,
            "message": (
                "No visible target document for this reference. It may be an "
                "external authority not yet ingested (see list_wanted_authorities "
                "/ discover_authorities) or a document you cannot read."
            ),
        }

    text = _read_document_text(doc)
    offset = max(0, int(char_offset or 0))
    chunk = text[offset : offset + max_chars]
    meta = doc.custom_meta if isinstance(doc.custom_meta, dict) else {}
    return {
        "resolved": True,
        "document_id": doc.pk,
        "document_title": doc.title,
        "canonical_key": meta.get("canonical_key", canonical_key),
        "authority": meta.get("authority"),
        "char_offset": offset,
        "returned_chars": len(chunk),
        "total_chars": len(text),
        "has_more": (offset + max_chars) < len(text),
        "text": chunk,
    }


# --------------------------------------------------------------------------- #
# Tool 3 — who else relies on this authority / document? (find the callers)     #
# --------------------------------------------------------------------------- #
def find_documents_citing(
    *,
    corpus_id: int,
    user_id: int,
    canonical_key: str | None = None,
    document_id: int | None = None,
    limit: int | None = None,
) -> dict:
    """Find the documents that cite a given authority or document (read-only).

    "Find the callers." Anchor on a ``canonical_key`` (e.g. ``dgcl:145`` — every
    contract that relies on that statute) or a ``document_id`` (every document
    that references that document / exhibit). Results are grouped by citing
    document and ranked by mention volume, with a few sample citing clauses each.

    Only documents you can read appear. In a document agent, ``document_id``
    defaults to the current document ("who cites me?"); a ``canonical_key``
    overrides it.
    """
    from opencontractserver.enrichment.services import CorpusReferenceService

    if not canonical_key and document_id is None:
        return {
            "error": "Provide either canonical_key or document_id.",
            "citing_documents": [],
        }

    user = get_user_or_none(user_id)
    limit = clamp_limit(limit, C.NAV_DEFAULT_MAX_CITING, C.NAV_MAX_CITING)

    base = CorpusReferenceService.visible_to_user(user)
    # canonical_key wins when both are supplied (the more specific anchor).
    qs = (
        base.filter(canonical_key=canonical_key)
        if canonical_key
        else base.filter(target_document_id=document_id)
    )
    qs = qs.select_related("source_annotation", "source_annotation__document").order_by(
        "id"
    )

    by_doc: dict[int, dict] = {}
    for ref in qs:
        src = ref.source_annotation
        src_doc = src.document if src else None
        if src_doc is None:
            continue  # structural-annotation source: no citing document to list
        entry = by_doc.setdefault(
            src_doc.pk,
            {
                "document_id": src_doc.pk,
                "document_title": src_doc.title,
                "corpus_id": ref.corpus_id,
                "mention_count": 0,
                "sample_citations": [],
            },
        )
        entry["mention_count"] += 1
        if len(entry["sample_citations"]) < C.NAV_MAX_SAMPLE_CITATIONS:
            entry["sample_citations"].append(
                {
                    "annotation_id": src.pk,
                    "canonical_key": ref.canonical_key,
                    "text": _snippet(src),
                }
            )

    citing = sorted(
        by_doc.values(), key=lambda d: (-d["mention_count"], d["document_id"])
    )[:limit]
    return {
        "anchor": {"canonical_key": canonical_key, "document_id": document_id},
        "citing_document_count": len(citing),
        "citing_documents": citing,
    }


# --------------------------------------------------------------------------- #
# Tool 4 — orient: the local governance map (see the module graph)              #
# --------------------------------------------------------------------------- #
def _restrict_to_neighborhood(graph: dict, focus_pk: int, depth: int) -> dict:
    """Keep only nodes/edges within ``depth`` undirected hops of the focus doc."""
    depth = max(0, min(int(depth or 1), C.NAV_NEIGHBORHOOD_MAX_DEPTH))
    edges = graph.get("edges", [])

    def _ep(endpoint):
        # GovernanceGraphService emits ("doc", pk) / ("key", key) tuples.
        return tuple(endpoint) if isinstance(endpoint, list) else endpoint

    adjacency: dict = {}
    for edge in edges:
        s, t = _ep(edge["source"]), _ep(edge["target"])
        adjacency.setdefault(s, set()).add(t)
        adjacency.setdefault(t, set()).add(s)

    start = ("doc", focus_pk)
    seen = {start}
    frontier = {start}
    for _ in range(depth):
        nxt: set = set()
        for node in frontier:
            for neighbour in adjacency.get(node, ()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    nxt.add(neighbour)
        frontier = nxt

    kept_docs = {val for kind, val in seen if kind == "doc"}
    kept_keys = {val for kind, val in seen if kind == "key"}
    return {
        **graph,
        "doc_nodes": [n for n in graph["doc_nodes"] if n["doc_pk"] in kept_docs],
        "ghost_nodes": [n for n in graph["ghost_nodes"] if n["key"] in kept_keys],
        "edges": [
            e for e in edges if _ep(e["source"]) in seen and _ep(e["target"]) in seen
        ],
        "focus_in_graph": any(n["doc_pk"] == focus_pk for n in graph["doc_nodes"]),
        "depth": depth,
    }


def get_reference_neighborhood(
    *,
    corpus_id: int,
    user_id: int,
    focus_document_id: int | None = None,
    depth: int = 1,
    node_cap: int | None = None,
) -> dict:
    """Return the corpus governance graph, or a document's neighbourhood (read-only).

    Orientation before traversal: nodes are documents (filings, exhibits,
    statute sections) plus "ghost" nodes for cited authorities with no visible
    target yet; edges are ``LAW`` (resolved citation → statute),
    ``LAW_EXTERNAL`` (citation → ghost) and ``DOCUMENT`` (document-to-document
    rollups), weighted by mention count.

    Omit ``focus_document_id`` for the whole (degree-capped) corpus graph, or
    pass one to get just that document's neighbourhood out to ``depth`` hops.
    """
    from opencontractserver.enrichment.services import GovernanceGraphService

    user = get_user_or_none(user_id)
    node_cap = clamp_limit(
        node_cap,
        C.NAV_NEIGHBORHOOD_DEFAULT_NODE_CAP,
        C.NAV_NEIGHBORHOOD_MAX_NODE_CAP,
    )

    graph = GovernanceGraphService.build(user, corpus_id, node_cap)
    if graph is None:
        return {
            "corpus_id": corpus_id,
            "visible": False,
            "message": "Corpus not found or not readable.",
        }

    if focus_document_id is not None:
        graph = _restrict_to_neighborhood(graph, focus_document_id, depth)

    graph["corpus_id"] = corpus_id
    graph["focus_document_id"] = focus_document_id
    return graph


# --------------------------------------------------------------------------- #
# Async wrappers (production tools MUST be async — CLAUDE.md agent-tool rule)   #
# --------------------------------------------------------------------------- #
async def aget_document_references(
    *,
    corpus_id: int,
    user_id: int,
    document_id: int | None = None,
    direction: str = "both",
    limit: int | None = None,
) -> dict:
    return await _db_sync_to_async(get_document_references)(
        corpus_id=corpus_id,
        user_id=user_id,
        document_id=document_id,
        direction=direction,
        limit=limit,
    )


async def aread_reference_target(
    *,
    corpus_id: int,
    user_id: int,
    canonical_key: str | None = None,
    target_document_id: int | None = None,
    char_offset: int = 0,
    max_chars: int | None = None,
) -> dict:
    return await _db_sync_to_async(read_reference_target)(
        corpus_id=corpus_id,
        user_id=user_id,
        canonical_key=canonical_key,
        target_document_id=target_document_id,
        char_offset=char_offset,
        max_chars=max_chars,
    )


async def afind_documents_citing(
    *,
    corpus_id: int,
    user_id: int,
    canonical_key: str | None = None,
    document_id: int | None = None,
    limit: int | None = None,
) -> dict:
    return await _db_sync_to_async(find_documents_citing)(
        corpus_id=corpus_id,
        user_id=user_id,
        canonical_key=canonical_key,
        document_id=document_id,
        limit=limit,
    )


async def aget_reference_neighborhood(
    *,
    corpus_id: int,
    user_id: int,
    focus_document_id: int | None = None,
    depth: int = 1,
    node_cap: int | None = None,
) -> dict:
    return await _db_sync_to_async(get_reference_neighborhood)(
        corpus_id=corpus_id,
        user_id=user_id,
        focus_document_id=focus_document_id,
        depth=depth,
        node_cap=node_cap,
    )
