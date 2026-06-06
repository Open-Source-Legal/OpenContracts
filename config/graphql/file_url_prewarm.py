"""Concurrent pre-warming of document file URLs.

On GCS with IAM signBlob (Workload Identity, no local signing key) every
``FieldFile.url`` is a network round trip. graphene resolves a connection's
nodes — and each node's ``pdfFile``/``icon`` — sequentially, so a page of N
documents signs its file URLs one-at-a-time (N×~150ms ⇒ multi-second paint).

This middleware intercepts the *resolved* ``documents`` connection, signs the
whole page's requested file URLs in a thread pool, and warms
``info.context._file_url_cache`` so the per-node resolvers in
``optimized_file_resolvers`` return from cache instead of signing serially.

It is a wall-time optimization (the same number of signBlob calls, run
concurrently) and composes with the cross-request shared cache: cache hits
skip signing entirely, and freshly-signed URLs are written back to the shared
cache. It is a no-op unless signing is actually expensive
(``settings.FILE_URL_SHARED_CACHE_TTL > 0``), so LOCAL storage / tests are
unchanged.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.core.cache import cache

from config.graphql.custom_resolvers import _selection_set_iter
from config.graphql.optimized_file_resolvers import _FILE_URL_CACHE_PREFIX

logger = logging.getLogger(__name__)

# GraphQL (camelCase) field name -> Django model field name for the Document
# file fields exposed via ``optimized_file_resolvers``.
_GQL_TO_MODEL_FILE_FIELD = {
    "pdfFile": "pdf_file",
    "icon": "icon",
    "txtExtractFile": "txt_extract_file",
    "pawlsParseFile": "pawls_parse_file",
    "mdSummaryFile": "md_summary_file",
}


def _requested_document_file_fields(info: Any) -> set[str]:
    """Model field names of the Document file URLs requested under edges→node.

    Only pre-warm what the client actually selected — signing unrequested
    fields would *add* signBlob calls, not save them.
    """
    fragments = getattr(info, "fragments", {}) or {}
    requested: set[str] = set()
    for field_node in info.field_nodes or ():
        for edges in _selection_set_iter(field_node, fragments):
            if edges.name.value != "edges":
                continue
            for node in _selection_set_iter(edges, fragments):
                if node.name.value != "node":
                    continue
                for child in _selection_set_iter(node, fragments):
                    model_field = _GQL_TO_MODEL_FILE_FIELD.get(child.name.value)
                    if model_field:
                        requested.add(model_field)
    return requested


def _is_document_connection(info: Any) -> bool:
    """True only for a connection field whose node model is ``Document``.

    Mirrors ``PermissionAnnotatingMiddleware``'s return-type introspection:
    connection types expose ``_meta.node``; a bare node type does not — so this
    fires once on the connection field, not per edge/node.
    """
    return_type = getattr(info, "return_type", None)
    graphene_type = getattr(return_type, "graphene_type", None)
    meta = getattr(graphene_type, "_meta", None)
    node = getattr(meta, "node", None)
    if node is None:
        return False
    model = getattr(getattr(node, "_meta", None), "model", None)
    if model is None:
        return False
    from opencontractserver.documents.models import Document

    return model is Document


def _extract_document_nodes(result: Any) -> list[Any]:
    """Pull the page's node instances out of a resolved relay connection.

    Returns ``[]`` for anything that isn't an already-materialized connection
    (e.g. a Promise) so pre-warming degrades to the per-node lazy path.
    """
    edges = getattr(result, "edges", None)
    if not edges:
        return []
    nodes = []
    for edge in edges:
        node = getattr(edge, "node", None)
        if node is not None:
            nodes.append(node)
    return nodes


class FileUrlPrewarmMiddleware:
    """Pre-sign a Document connection page's file URLs concurrently."""

    def resolve(self, next, root, info, **kwargs):  # noqa: A002 (graphene API)
        result = next(root, info, **kwargs)
        try:
            if _is_document_connection(info):
                self._prewarm(result, info)
        except Exception:  # never break resolution over a perf optimization
            logger.debug("file-url pre-warm skipped", exc_info=True)
        return result

    @staticmethod
    def _prewarm(result: Any, info: Any) -> None:
        ttl = getattr(settings, "FILE_URL_SHARED_CACHE_TTL", 0)
        if not ttl:
            return  # signing is cheap/free (LOCAL) — nothing to parallelize

        fields = _requested_document_file_fields(info)
        if not fields:
            return

        nodes = _extract_document_nodes(result)
        if len(nodes) < 2:
            return  # one (or zero) sign — the per-node path is already fine

        req_cache = getattr(info.context, "_file_url_cache", None)
        if req_cache is None:
            req_cache = {}
            info.context._file_url_cache = req_cache

        # Build the work list of cache misses: (memo_key, blob_name, FieldFile).
        work: list[tuple[str, str | None, Any]] = []
        for doc in nodes:
            doc_id = getattr(doc, "id", None)
            if doc_id is None:
                continue
            for field in fields:
                field_value = getattr(doc, field, None)
                if not field_value:
                    continue
                memo_key = f"{doc_id}:{field}"
                if memo_key in req_cache:
                    continue
                work.append((memo_key, getattr(field_value, "name", None), field_value))

        if not work:
            return

        def resolve_raw(item):
            _memo_key, blob_name, field_value = item
            if blob_name:
                try:
                    cached = cache.get(f"{_FILE_URL_CACHE_PREFIX}{blob_name}")
                except Exception:
                    cached = None
                if cached is not None:
                    return (_memo_key, blob_name, cached, True)
            try:
                raw = field_value.url  # the expensive signBlob round trip
            except Exception:
                return None
            return (_memo_key, blob_name, raw, False)

        # Sign the first item on the main thread so the storage client / bucket
        # initialize once, then fan the rest out — avoids a thundering-herd
        # client init across worker threads.
        results = [resolve_raw(work[0])]
        rest = work[1:]
        if rest:
            max_workers = min(
                getattr(settings, "FILE_URL_SIGN_CONCURRENCY", 16), len(rest)
            )
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                results.extend(executor.map(resolve_raw, rest))

        for res in results:
            if res is None:
                continue
            memo_key, blob_name, raw, was_cached = res
            try:
                url = info.context.build_absolute_uri(raw)
            except Exception:
                continue
            req_cache[memo_key] = url
            if not was_cached and blob_name:
                try:
                    cache.set(f"{_FILE_URL_CACHE_PREFIX}{blob_name}", raw, ttl)
                except Exception:
                    pass
