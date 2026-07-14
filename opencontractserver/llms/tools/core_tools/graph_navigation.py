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
    from opencontractserver.utils.files import read_document_plain_text

    return read_document_plain_text(doc)


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

    NOTE: results are **visibility-scoped, not corpus-scoped** — every reference
    whose source (and resolved target) the caller may read is returned, even
    when it crosses into another corpus (a citation legitimately points at an
    authority corpus). ``corpus_id`` is agent context, not a filter; do not
    "fix" this into a ``corpus_id`` filter or cross-corpus authority lookups
    would silently narrow. ``CorpusReferenceService.visible_to_user`` is the
    guard.
    """
    from opencontractserver.enrichment.services import CorpusReferenceService
    from opencontractserver.shared.services.base import BaseService

    # Normalize direction up front so every return (error and happy path alike)
    # reports the same value the query actually uses.
    if direction not in ("outbound", "inbound", "both"):
        direction = "both"

    if document_id is None:
        return {
            "error": (
                "get_document_references needs a document_id. In a corpus agent, "
                "pass the id of the document whose references you want."
            ),
            "document_id": None,
            "corpus_id": corpus_id,
            "direction": direction,
            "outbound": [],
            "inbound": [],
            "outbound_count": 0,
            "inbound_count": 0,
        }

    user = get_user_or_none(user_id)

    # IDOR-safe existence/visibility check via the shared service layer
    # (CLAUDE.md rule #7) — mirrors read_reference_target's target_document_id
    # lookup. Without this, a bad/unrelated document_id (e.g. an agent passing
    # a corpus_id where a document_id was expected) silently resolves to an
    # empty-but-"successful" envelope instead of surfacing the mistake, which
    # has caused agents to confidently report "no such citation" when the
    # citation actually exists under the correct document_id.
    if BaseService.get_or_none(Document, document_id, user) is None:
        return {
            "error": (
                f"document_id {document_id} was not found (or is not visible to "
                "you). Use similarity_search to find a valid document_id first."
            ),
            "document_id": document_id,
            "corpus_id": corpus_id,
            "direction": direction,
            "outbound": [],
            "inbound": [],
            "outbound_count": 0,
            "inbound_count": 0,
        }

    limit = clamp_limit(limit, C.NAV_DEFAULT_MAX_REFERENCES, C.NAV_MAX_REFERENCES)

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
    from opencontractserver.shared.services.base import BaseService

    if not canonical_key and target_document_id is None:
        return {
            "resolved": False,
            "error": "Provide either canonical_key or target_document_id.",
            "canonical_key": canonical_key,
            "target_document_id": target_document_id,
        }

    user = get_user_or_none(user_id)
    max_chars = clamp_limit(
        max_chars, C.NAV_TARGET_TEXT_MAX_CHARS, C.NAV_TARGET_TEXT_MAX_CHARS
    )

    doc: Document | None = None
    if target_document_id is not None:
        # IDOR-safe single-object READ lookup via the shared service layer
        # (CLAUDE.md rule #7) — same MIN(document, corpus) visibility, no inline
        # Tier-0 call.
        doc = BaseService.get_or_none(Document, target_document_id, user)
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

    NOTE: like ``get_document_references``, this is **visibility-scoped, not
    corpus-scoped** — a document in another readable corpus that cites the same
    authority is returned. ``corpus_id`` is agent context, not a filter.
    """
    from opencontractserver.enrichment.services import CorpusReferenceService

    if not canonical_key and document_id is None:
        return {
            "error": "Provide either canonical_key or document_id.",
            "anchor": {"canonical_key": None, "document_id": None},
            "citing_document_count": 0,
            "citing_documents": [],
        }

    user = get_user_or_none(user_id)
    limit = clamp_limit(limit, C.NAV_DEFAULT_MAX_CITING, C.NAV_MAX_CITING)

    from django.db.models import Count, Min

    from opencontractserver.enrichment.authorities import candidate_keys
    from opencontractserver.shared.services.base import BaseService

    # Same IDOR-safe existence check get_document_references applies: a
    # document_id anchor that doesn't resolve to a visible document must error,
    # not return a false-empty "nobody cites this" envelope (an agent passing a
    # corpus_id where a document_id belongs would otherwise be misled).
    #
    # Only the document_id anchor is guarded — and deliberately so. A
    # canonical_key is a semantic key, not an object id: an empty result for a
    # well-formed key is a legitimate "no visible document cites this authority"
    # answer (there is no registry of valid keys to check against, and zero
    # citers is a normal outcome). candidate_keys() below only normalizes /
    # expands the key string (underscore→hyphen, subsection→section root); it
    # does not validate the key, so no analogous existence error is raised here.
    if (
        not canonical_key
        and BaseService.get_or_none(Document, document_id, user) is None
    ):
        return {
            "error": (
                f"document_id {document_id} was not found (or is not visible to "
                "you). Use similarity_search to find a valid document_id first."
            ),
            "anchor": {"canonical_key": None, "document_id": document_id},
            "citing_document_count": 0,
            "citing_documents": [],
        }

    base = CorpusReferenceService.visible_to_user(user)
    # canonical_key wins when both are supplied (the more specific anchor).
    # Route through candidate_keys() — the same helper find_authority_target
    # uses — so an underscore-typo'd or subsection-precise key still finds the
    # documents citing the real (hyphenated / section-root) key, instead of
    # only matching an exact string.
    anchored = (
        base.filter(canonical_key__in=candidate_keys(canonical_key))
        if canonical_key
        else base.filter(target_document_id=document_id)
    ).filter(source_annotation__document__isnull=False)

    # Rank citing documents by mention volume IN THE DB, bounded to `limit` — a
    # widely-cited authority must not pull its whole reference set into memory.
    # corpus_id is derived in the SAME bounded aggregate (Min over the citing
    # reference rows, deterministic), so it never depends on the separate,
    # capped sample scan below — a top-ranked document can't end up with a
    # null corpus_id just because its id sorts past the sample budget.
    ranked = list(
        anchored.values("source_annotation__document_id")
        .annotate(mention_count=Count("id"), corpus_id=Min("corpus"))
        .order_by("-mention_count", "source_annotation__document_id")[:limit]
    )
    doc_ids = [r["source_annotation__document_id"] for r in ranked]
    # Route the title lookup through the service layer too (defense-in-depth):
    # doc_ids is already permission-filtered via ``anchored``, but a raw
    # ``Document.objects`` call here would be a latent Tier-0 leak if a future
    # edit ever seeded doc_ids from an unfiltered source. E001 does not scan
    # this package, so keep it service-routed.
    titles = dict(
        BaseService.filter_visible(Document, user)
        .filter(pk__in=doc_ids)
        .values_list("pk", "title")
    )

    # Bounded second pass: a few citing-clause previews for the ranked
    # documents. NAV_CITING_SAMPLE_SCAN caps TOTAL rows read for snippets, so
    # this is a per-document-fairness trade-off, not just a volume bound: rows
    # are ordered by (document_id, id), so if the lowest-pk ranked document
    # alone has more mentions than the budget, later ranked documents can get
    # empty ``sample_citations``. This ONLY affects the illustrative snippet —
    # ``mention_count`` and ``corpus_id`` are exact DB aggregates on the ranked
    # query above and are unaffected by this scan's budget.
    samples: dict[int, list] = {}
    for ref in (
        anchored.filter(source_annotation__document_id__in=doc_ids)
        .select_related("source_annotation")
        .order_by("source_annotation__document_id", "id")[: C.NAV_CITING_SAMPLE_SCAN]
    ):
        src = ref.source_annotation
        did = src.document_id
        bucket = samples.setdefault(did, [])
        if len(bucket) < C.NAV_MAX_SAMPLE_CITATIONS:
            bucket.append(
                {
                    "annotation_id": src.pk,
                    "canonical_key": ref.canonical_key,
                    "text": _snippet(src),
                }
            )

    citing = [
        {
            "document_id": r["source_annotation__document_id"],
            "document_title": titles.get(r["source_annotation__document_id"]),
            "corpus_id": r["corpus_id"],
            "mention_count": r["mention_count"],
            "sample_citations": samples.get(r["source_annotation__document_id"], []),
        }
        for r in ranked
    ]
    return {
        "anchor": {"canonical_key": canonical_key, "document_id": document_id},
        "citing_document_count": len(citing),
        "citing_documents": citing,
    }


# --------------------------------------------------------------------------- #
# Tool 4 — orient: the local governance map (see the module graph)              #
# --------------------------------------------------------------------------- #
def _cap_nodes_by_degree(
    graph: dict, node_cap: int, always_keep: tuple | None = None
) -> dict:
    """Cap a graph's node/edge lists to the top ``node_cap`` nodes by degree.

    Applied to the *restricted* neighbourhood so ``node_cap`` bounds what is
    RETURNED, not which documents were eligible to be found (see the focus
    branch of :func:`get_reference_neighborhood`).

    ``always_keep`` (an ``("doc", pk)`` / ``("key", key)`` endpoint) is force-
    retained even if it ranks below the cap — used to guarantee the focus
    document is never evicted from its own neighbourhood by a higher-GLOBAL-
    degree neighbour (a corpus-wide hub). It reserves one slot, so the returned
    count still respects ``node_cap``.
    """
    docs = graph["doc_nodes"]
    ghosts = graph["ghost_nodes"]
    if len(docs) + len(ghosts) <= node_cap:
        return graph

    ranked_eps = [
        ep
        for ep, _w in sorted(
            [(("doc", n["doc_pk"]), n["degree"]) for n in docs]
            + [(("key", n["key"]), n["degree"]) for n in ghosts],
            key=lambda t: -t[1],
        )
    ]
    kept_eps = ranked_eps[:node_cap]
    # Force-keep the focus node: if it exists in the graph but fell below the
    # cap, swap out the lowest-ranked kept node to make room for it.
    if (
        always_keep is not None
        and always_keep in ranked_eps
        and always_keep not in kept_eps
    ):
        kept_eps = kept_eps[: node_cap - 1] + [always_keep]
    kept = set(kept_eps)
    kept_docs = {v for k, v in kept if k == "doc"}
    kept_keys = {v for k, v in kept if k == "key"}

    def _ep(endpoint):
        return tuple(endpoint) if isinstance(endpoint, list) else endpoint

    return {
        **graph,
        "doc_nodes": [n for n in docs if n["doc_pk"] in kept_docs],
        "ghost_nodes": [n for n in ghosts if n["key"] in kept_keys],
        "edges": [
            e
            for e in graph["edges"]
            if _ep(e["source"]) in kept and _ep(e["target"]) in kept
        ],
        "truncated": True,
    }


def _restrict_to_neighborhood(graph: dict, focus_pk: int, depth: int) -> dict:
    """Keep only nodes/edges within ``depth`` undirected hops of the focus doc."""
    # ``1 if depth is None else …`` (not ``depth or 1``) so an explicit
    # ``depth=0`` — "just the focus node, no hops" — is honoured rather than
    # silently bumped to 1.
    depth = 1 if depth is None else int(depth)
    depth = max(0, min(depth, C.NAV_NEIGHBORHOOD_MAX_DEPTH))
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

    # In focus mode, build the FULL corpus graph first: build() truncates its
    # output to the top-node_cap nodes by GLOBAL degree, which would drop a
    # low-degree focus document before the neighbourhood BFS ever runs — the
    # exact use case focus_document_id exists for. Building the whole graph is
    # no costlier (build scans all references regardless of cap; the cap only
    # slices the output). We then restrict to the neighbourhood and cap the
    # RESULT to node_cap so the bound applies to what is returned.
    build_cap = (
        C.NAV_NEIGHBORHOOD_FULL_BUILD_CAP if focus_document_id is not None else node_cap
    )
    graph = GovernanceGraphService.build(user, corpus_id, build_cap)
    if graph is None:
        return {
            "corpus_id": corpus_id,
            "visible": False,
            "message": "Corpus not found or not readable.",
        }

    if focus_document_id is not None:
        graph = _restrict_to_neighborhood(graph, focus_document_id, depth)
        graph = _cap_nodes_by_degree(
            graph, node_cap, always_keep=("doc", focus_document_id)
        )
        # Recompute AFTER the cap: _restrict_to_neighborhood set focus_in_graph
        # from the pre-cap nodes, but the cap could (absent always_keep) have
        # dropped the focus — the returned flag must reflect the final node set,
        # never the pre-cap one. A focus with no edges yields False honestly.
        graph["focus_in_graph"] = any(
            n["doc_pk"] == focus_document_id for n in graph["doc_nodes"]
        )

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
