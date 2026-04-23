"""Pass-through reranker used as a safe default and in tests.

Returns the original ordering verbatim. Useful when you want the reranking
plumbing to be exercised without actually changing result quality (e.g.
integration tests or benchmarks that need a control condition).
"""

from __future__ import annotations

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.reranker import BaseReranker, RerankResult


class NoopReranker(BaseReranker):
    """Identity reranker. Returns candidates in their original order."""

    title = "No-op Reranker"
    description = (
        "Pass-through reranker that preserves the first-stage retrieval order. "
        "Used as a safe default and as a control condition in benchmarks."
    )
    author = "OpenContracts"
    dependencies: list[str] = []
    # File-type support is informational for rerankers (they operate on text
    # extracted from any document type).
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT, FileTypeEnum.DOCX]

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        # Score = n-i so the original ordering is preserved after the
        # base class's sort-by-score-descending pass.
        n = len(passages)
        return [RerankResult(index=i, score=float(n - i)) for i in range(n)]
