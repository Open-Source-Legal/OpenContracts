"""
Optimized file field resolvers to minimize storage backend overhead.

Key optimizations:
1. Lazy evaluation - only build URLs when actually accessed
2. Request-level memoization - avoid regenerating the same URL multiple times in one request
3. Minimal processing - quick returns for null/empty fields
"""

from typing import Any, Callable


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

        # Request-level memoization to avoid regenerating URLs
        # This is safe because URLs are valid for the request duration
        if not hasattr(info.context, "_file_url_cache"):
            info.context._file_url_cache = {}

        cache_key = f"{self.id}:{field_name}"
        if cache_key in info.context._file_url_cache:
            return info.context._file_url_cache[cache_key]

        # Generate the URL (this is where the overhead occurs)
        try:
            url = info.context.build_absolute_uri(field_value.url)
            info.context._file_url_cache[cache_key] = url
            return url
        except Exception:
            # If URL generation fails, return empty string rather than error
            return ""

    return resolver


# Pre-create resolvers for all file fields to avoid function creation overhead
resolve_pdf_file_optimized = create_file_resolver("pdf_file")
resolve_icon_optimized = create_file_resolver("icon")
resolve_txt_extract_file_optimized = create_file_resolver("txt_extract_file")
resolve_md_summary_file_optimized = create_file_resolver("md_summary_file")
resolve_pawls_parse_file_optimized = create_file_resolver("pawls_parse_file")
