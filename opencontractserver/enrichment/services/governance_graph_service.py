"""Build the corpus-scoped governance graph (the in-app reference web).

Mirrors ``demo/export_governance_graph.py``, restricted to one source corpus
and enforced through the permission model:

* **nodes** — documents (filing primaries, exhibits, statute sections) plus
  "ghost" nodes for law citations with no *visible* target document.
* **edges** — resolved LAW links (possibly cross-corpus), EXTERNAL law
  citations (rolled up to their section root), ``DocumentRelationship`` rows,
  and verified canonical-key ``AuthorityRelationship`` rows — weighted by
  mention count.

Visibility rules:

* The source corpus must be READ-visible or the build returns ``None``.
* Reference rows are sourced via
  ``CorpusReferenceService.for_corpus_by_source`` — corpus READ plus a visible
  source document, with the resolved *target* deliberately NOT pre-filtered so
  this build can apply its own per-endpoint rule: invisible source documents
  drop their edges entirely; invisible target documents degrade to external
  ghost nodes so titles never leak. (The strict ``visible_to_user`` is reserved
  for surfaces that expose target FKs directly, e.g. the GraphQL
  ``corpusReferences`` query.)
* Only READ-visible target corpora are listed in ``corpora``.

The service returns plain data keyed by raw PKs / canonical keys; the GraphQL
resolver owns the relay global-id encoding. Node endpoints are ``("doc", pk)``
or ``("key", canonical_key)`` tuples.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from opencontractserver.annotations.models import (
    AuthorityFrontier,
    AuthorityRelationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.services import DocumentRelationshipService
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.corpus_reference_service import (
    CorpusReferenceService,
)
from opencontractserver.shared.services.base import BaseService

Endpoint = tuple[str, Any]  # ("doc", pk) | ("key", canonical_key)


class GovernanceGraphService:
    """Assemble the node-link governance graph for one corpus."""

    @classmethod
    def build(
        cls,
        user,
        corpus_pk: int,
        node_cap: int,
        *,
        request: Any = None,
    ) -> dict | None:
        """Return the graph as plain data, or ``None`` for an invisible corpus.

        Counts (``document_count`` / ``external_key_count`` / ``edge_count`` /
        ``mention_count``) describe the FULL visible graph; ``truncated``
        signals that the node/edge lists were capped to ``node_cap`` by
        degree rank.
        """
        from opencontractserver.enrichment.authorities import candidate_keys

        corpus = (
            BaseService.filter_visible(Corpus, user, request=request)
            .filter(id=corpus_pk)
            .first()
        )
        if corpus is None:
            return None

        ref_rows = list(
            CorpusReferenceService.for_corpus_by_source(user, corpus_pk)
            .filter(reference_type=C.REF_LAW)
            .exclude(canonical_key=None)
            .values_list(
                "source_annotation__document_id",
                "target_document_id",
                "target_corpus_id",
                "canonical_key",
            )
        )
        rel_rows = list(
            DocumentRelationshipService.get_visible_relationships(
                user, corpus_id=corpus_pk, request=request
            ).values_list("source_document_id", "target_document_id")
        )
        # Resolve canonical authority edges inside this request rather than
        # storing global Document caches on AuthorityRelationship. The same
        # pack may be installed into independently owned corpora, so key ->
        # Document resolution must be scoped by current paths and visibility.
        authority_source_rows = list(
            BaseService.filter_visible(Document, user, request=request)
            .filter(
                path_records__corpus_id=corpus_pk,
                path_records__is_current=True,
                path_records__is_deleted=False,
                custom_meta__canonical_key__isnull=False,
            )
            .values_list("id", "custom_meta")
            .distinct()
        )
        authority_source_docs_by_key: dict[str, list[int]] = defaultdict(list)
        for source_document_id, source_meta in authority_source_rows:
            if not isinstance(source_meta, dict):
                continue
            source_key = source_meta.get("canonical_key")
            if isinstance(source_key, str) and source_key:
                authority_source_docs_by_key[source_key].append(source_document_id)

        # Verification is the production-graph admission gate. Query only rows
        # whose source key has a visible current document in this corpus.
        authority_rel_rows = list(
            AuthorityRelationship.objects.filter(
                verified=True,
                source_key__in=authority_source_docs_by_key.keys(),
            )
            .exclude(target_key="")
            .values_list(
                "source_key",
                "target_key",
                "relationship_type",
            )
        )

        # Batch-resolve every target key to visible documents with active paths.
        # Corpus visibility is checked separately because Document visibility
        # alone must never reveal a target living only in an unreadable corpus.
        authority_target_keys = {
            target_key for _source_key, target_key, _rel_type in authority_rel_rows
        }
        visible_target_rows = list(
            BaseService.filter_visible(Document, user, request=request)
            .filter(
                custom_meta__canonical_key__in=authority_target_keys,
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
            .values_list("id", "custom_meta")
            .distinct()
        )
        target_key_by_document: dict[int, str] = {}
        for target_document_id, target_meta in visible_target_rows:
            if not isinstance(target_meta, dict):
                continue
            target_key = target_meta.get("canonical_key")
            if isinstance(target_key, str) and target_key in authority_target_keys:
                target_key_by_document[target_document_id] = target_key

        target_path_corpora: dict[int, set[int]] = defaultdict(set)
        if target_key_by_document:
            for target_document_id, target_corpus_id in DocumentPath.objects.filter(
                document_id__in=target_key_by_document,
                is_current=True,
                is_deleted=False,
            ).values_list("document_id", "corpus_id"):
                target_path_corpora[target_document_id].add(target_corpus_id)

        authority_target_corpus_ids = {
            target_corpus_id
            for corpus_ids in target_path_corpora.values()
            for target_corpus_id in corpus_ids
        }
        visible_authority_target_corpus_ids = {corpus.id} | set(
            BaseService.filter_visible(Corpus, user, request=request)
            .filter(id__in=authority_target_corpus_ids - {corpus.id})
            .values_list("id", flat=True)
        )

        target_candidates_by_key: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for target_document_id, target_key in target_key_by_document.items():
            for target_corpus_id in target_path_corpora.get(target_document_id, set()):
                if target_corpus_id in visible_authority_target_corpus_ids:
                    target_candidates_by_key[target_key].append(
                        (target_document_id, target_corpus_id)
                    )
        authority_target_by_key = {
            target_key: min(
                candidates,
                # Prefer a copy installed in the requested corpus, then pick a
                # stable readable corpus/document pair.
                key=lambda candidate: (
                    candidate[1] != corpus_pk,
                    candidate[1],
                    candidate[0],
                ),
            )
            for target_key, candidates in target_candidates_by_key.items()
            if candidates
        }

        # Every document surfaced as a node must itself be READ-visible.
        # (Relationship endpoints already are — the service enforces it.)
        candidate_doc_ids = {src for src, _t, _c, _k in ref_rows if src} | {
            tgt for _s, tgt, _c, _k in ref_rows if tgt
        }
        candidate_doc_ids |= {
            source_document_id
            for source_document_ids in authority_source_docs_by_key.values()
            for source_document_id in source_document_ids
        }
        candidate_doc_ids |= {
            target_document_id
            for target_document_id, _target_corpus_id in authority_target_by_key.values()
        }
        visible_doc_ids = set(
            BaseService.filter_visible(Document, user, request=request)
            .filter(id__in=candidate_doc_ids)
            .values_list("id", flat=True)
        )

        edge_weight: Counter = Counter()  # (src_endpoint, tgt_endpoint, type) -> w
        doc_corpus: dict[int, int | None] = {}
        target_corpus_ids: set[int] = set()

        for src, tgt, tgt_corpus, key in ref_rows:
            if not src or src not in visible_doc_ids:
                continue  # invisible source: no edge, no title leak
            doc_corpus.setdefault(src, corpus_pk)
            if tgt == src:
                continue  # self-citation ("this section") — no edge to draw
            if tgt and tgt in visible_doc_ids:
                edge_weight[(("doc", src), ("doc", tgt), C.GRAPH_EDGE_LAW)] += 1
                doc_corpus.setdefault(tgt, tgt_corpus)
                if tgt_corpus:
                    target_corpus_ids.add(tgt_corpus)
            else:
                # Unresolved — or resolved but invisible to this user: degrade
                # to a ghost keyed by the citation's section root so subsection
                # variants share one node.
                root = candidate_keys(key)[-1]
                edge_weight[
                    (("doc", src), ("key", root), C.GRAPH_EDGE_LAW_EXTERNAL)
                ] += 1

        for src, tgt in rel_rows:
            edge_weight[(("doc", src), ("doc", tgt), C.GRAPH_EDGE_DOCUMENT)] += 1
            doc_corpus.setdefault(src, corpus_pk)
            doc_corpus.setdefault(tgt, corpus_pk)

        for source_key, target_key, relationship_type in authority_rel_rows:
            target = authority_target_by_key.get(target_key)
            for src in authority_source_docs_by_key.get(source_key, []):
                if src not in visible_doc_ids:
                    continue  # defensive: source visibility was already scoped
                doc_corpus.setdefault(src, corpus_pk)
                if target is not None:
                    target_document_id, target_corpus_id = target
                    if target_document_id == src:
                        continue
                    edge_weight[
                        (
                            ("doc", src),
                            ("doc", target_document_id),
                            relationship_type,
                        )
                    ] += 1
                    doc_corpus.setdefault(target_document_id, target_corpus_id)
                    target_corpus_ids.add(target_corpus_id)
                else:
                    # No visible current (Document, Corpus) pair for the key:
                    # retain the verified relationship as a key-only ghost.
                    edge_weight[
                        (("doc", src), ("key", target_key), relationship_type)
                    ] += 1

        degree: Counter = Counter()
        for (src_ep, tgt_ep, _t), w in edge_weight.items():
            degree[src_ep] += w
            degree[tgt_ep] += w

        node_doc_ids = {val for kind, val in degree if kind == "doc"}
        ghost_keys = {val for kind, val in degree if kind == "key"}

        # values_list, not .only(): Document's default manager bakes in
        # select_related("parent", ...), and Django forbids deferring a field
        # that select_related traverses. Plain tuples also skip model
        # instantiation and the manager's guardian-permission prefetches —
        # these nodes are read only for title/custom_meta.
        docs = {
            pk: {"title": title, "custom_meta": meta}
            for pk, title, meta in BaseService.filter_visible(
                Document, user, request=request
            )
            .filter(id__in=node_doc_ids)
            .values_list("id", "title", "custom_meta")
        }

        # Corpora the graph reaches: the queried corpus plus READ-visible
        # resolved-target corpora. An invisible target corpus is never listed
        # (its documents degraded to ghosts above, so it has no nodes either).
        listed_corpora = {corpus.id: corpus}
        if target_corpus_ids - {corpus.id}:
            for c in BaseService.filter_visible(Corpus, user, request=request).filter(
                id__in=target_corpus_ids - {corpus.id}
            ):
                listed_corpora[c.id] = c

        corpora = [
            {
                "corpus_pk": c.id,
                "title": c.title,
                # A corpus cited by the graph's own references is an authority
                # (statutes citing statutes classify the queried corpus too).
                "kind": (
                    C.GRAPH_CORPUS_AUTHORITY
                    if c.id in target_corpus_ids
                    else C.GRAPH_CORPUS_FILING
                ),
            }
            for c in listed_corpora.values()
        ]

        # Doc nodes represent ingested documents, not frontier entries — discovery_state is None.
        doc_nodes = []
        for doc_pk in node_doc_ids:
            doc = docs.get(doc_pk)
            if doc is None:
                continue
            title = doc["title"]
            meta = doc["custom_meta"] if isinstance(doc["custom_meta"], dict) else {}
            if meta.get("canonical_key"):
                kind = C.GRAPH_NODE_STATUTE
            elif "exhibit" in (title or "").lower():
                kind = C.GRAPH_NODE_EXHIBIT
            else:
                kind = C.GRAPH_NODE_PRIMARY
            node_corpus = doc_corpus.get(doc_pk)
            authority = meta.get("authority")
            juris, atype = C.classify_prefix(authority) if authority else (None, None)
            doc_nodes.append(
                {
                    "doc_pk": doc_pk,
                    "title": title,
                    "kind": kind,
                    "corpus_pk": node_corpus if node_corpus in listed_corpora else None,
                    "authority": authority,
                    "jurisdiction": juris,
                    "authority_type": atype,
                    "degree": degree[("doc", doc_pk)],
                }
            )

        frontier_by_key = {
            f.canonical_key: f
            for f in AuthorityFrontier.objects.filter(
                canonical_key__in=ghost_keys
            ).only("canonical_key", "jurisdiction", "authority_type", "discovery_state")
        }
        ghost_nodes = []
        for key in sorted(ghost_keys):
            authority = key.split(":", 1)[0]
            juris, atype = C.classify_prefix(authority)
            f = frontier_by_key.get(key)
            ghost_nodes.append(
                {
                    "key": key,
                    "authority": authority,
                    "jurisdiction": (f.jurisdiction if f else juris),
                    "authority_type": (f.authority_type if f else atype),
                    "discovery_state": (f.discovery_state if f else None),
                    "degree": degree[("key", key)],
                }
            )

        # Full-graph stats, then degree-ranked truncation for the payload.
        document_count = len(doc_nodes)
        external_key_count = len(ghost_nodes)
        edge_count = len(edge_weight)
        mention_count = sum(edge_weight.values())

        truncated = (document_count + external_key_count) > node_cap
        if truncated:
            ranked: list[Endpoint] = [ep for ep, _w in degree.most_common()][:node_cap]
            kept = set(ranked)
            doc_nodes = [n for n in doc_nodes if ("doc", n["doc_pk"]) in kept]
            ghost_nodes = [n for n in ghost_nodes if ("key", n["key"]) in kept]
            edge_weight = Counter(
                {
                    (s, t, ty): w
                    for (s, t, ty), w in edge_weight.items()
                    if s in kept and t in kept
                }
            )

        edges = [
            {"source": src_ep, "target": tgt_ep, "edge_type": etype, "weight": w}
            for (src_ep, tgt_ep, etype), w in sorted(
                edge_weight.items(),
                # Endpoints mix int and str payloads — stringify for a stable,
                # type-safe ordering.
                key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2]),
            )
        ]

        return {
            "corpora": corpora,
            "doc_nodes": doc_nodes,
            "ghost_nodes": ghost_nodes,
            "edges": edges,
            "document_count": document_count,
            "external_key_count": external_key_count,
            "edge_count": edge_count,
            "mention_count": mention_count,
            "truncated": truncated,
        }
