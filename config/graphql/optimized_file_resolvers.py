"""
Optimized file field resolvers to minimize storage backend overhead.

Key optimizations:
1. Lazy evaluation - only build URLs when actually accessed
2. Request-level memoization - avoid regenerating the same URL multiple times in one request
3. Cross-request shared cache - sign each blob at most once per TTL window
4. Minimal processing - quick returns for null/empty fields

Why the cross-request cache matters: S3/GCS media URLs are signed per object.
On GCS with IAM signBlob (Workload Identity, no local signing key), every
``FieldFile.url`` is a *network* round trip. A document-list edge selecting
``pdfFile``/``txtExtractFile``/``pawlsParseFile``/``icon`` therefore fans out
to N×4 signing calls (the multi-second corpus-folder query). The per-request
memo only dedupes the *same* (document, field) within one request, which never
repeats in a list query — so it doesn't help there. The shared cache keys on
the blob *name* (a signed URL is not user-specific) so a blob is signed once
per ``settings.FILE_URL_SHARED_CACHE_TTL`` window and then served from cache
for every subsequent request and user.
"""

from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache

# Shared-cache key prefix for signed media URLs (keyed by storage blob name).
_FILE_URL_CACHE_PREFIX = "oc:file_url:"


def create_file_resolver(field_name: str) -> Callable[[Any, Any], str]:
    """
    Factory function to create optimized file field resolvers.

    This avoids repetitive code while maintaining performance.
    """

    def resolver(self: Any, info: Any) -> str:
        # Fast path for empty fields
        field_value = getattr(self, field_name, None)
        if not field_value:
            return ""

        # Request-level memoization to avoid regenerating URLs for the same
        # (document, field) within a single request.
        req_cache = getattr(info.context, "_file_url_cache", None)
        if req_cache is None:
            req_cache = {}
            info.context._file_url_cache = req_cache

        memo_key = f"{self.id}:{field_name}"
        if memo_key in req_cache:
            return req_cache[memo_key]

        # Cross-request shared cache (Redis in prod). Disabled when TTL == 0
        # (LOCAL storage: URLs are relative + free). We cache the RAW storage
        # URL and apply ``build_absolute_uri`` per request so a cached entry
        # stays correct across hosts. Cache failures must never break URL
        # resolution, so they degrade to a fresh sign.
        shared_ttl = getattr(settings, "FILE_URL_SHARED_CACHE_TTL", 0)
        blob_name = getattr(field_value, "name", None)
        shared_key = (
            f"{_FILE_URL_CACHE_PREFIX}{blob_name}" if shared_ttl and blob_name else None
        )

        cached_raw = None
        if shared_key is not None:
            try:
                cached_raw = cache.get(shared_key)
            except Exception:
                cached_raw = None

        try:
            # The blob is only signed (the expensive GCS signBlob round trip)
            # on a cache miss.
            raw_url = field_value.url if cached_raw is None else cached_raw
            url = info.context.build_absolute_uri(raw_url)
        except Exception:
            # If URL generation fails, return empty string rather than error
            return ""

        if cached_raw is None and shared_key is not None:
            try:
                # Blob-keyed, not user-keyed: GCS signBlob URLs are bearer
                # tokens (valid for any holder, not scoped to a user), so the
                # raw signed URL is safe to share across users. This is ONLY
                # safe while signed URLs are not user-scoped — if STORAGE_BACKEND
                # ever switches to a mechanism that signs per-user URLs, this
                # cache would leak URLs across users and must be re-keyed.
                cache.set(shared_key, raw_url, shared_ttl)
            except Exception:
                pass

        req_cache[memo_key] = url
        return url

    return resolver


# Pre-create resolvers for all file fields to avoid function creation overhead
resolve_pdf_file_optimized = create_file_resolver("pdf_file")
resolve_icon_optimized = create_file_resolver("icon")
resolve_txt_extract_file_optimized = create_file_resolver("txt_extract_file")
resolve_md_summary_file_optimized = create_file_resolver("md_summary_file")
resolve_pawls_parse_file_optimized = create_file_resolver("pawls_parse_file")
