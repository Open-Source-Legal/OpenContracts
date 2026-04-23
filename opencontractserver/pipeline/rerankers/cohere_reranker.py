"""Cohere Rerank API backend.

Uses Cohere's hosted reranker (``rerank-v3.5`` / ``rerank-multilingual-v3.0``).
Great quality, adds network latency and per-query cost. Requires a Cohere API
key configured as the secret ``cohere_api_key`` on :class:`PipelineSettings`
(or the ``COHERE_API_KEY`` environment variable at migration time).

We call the REST endpoint directly via ``requests`` instead of depending on
the ``cohere`` SDK, both to avoid pulling in a large optional dependency and
to keep the reranker's fault-tolerance semantics consistent with the other
backends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from opencontractserver.constants.document_processing import (
    RERANKER_REQUEST_TIMEOUT_SECONDS,
)
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.reranker import BaseReranker, RerankResult
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://api.cohere.com/v2/rerank"
_DEFAULT_MODEL = "rerank-v3.5"


class CohereReranker(BaseReranker):
    """Reranker backed by Cohere's hosted Rerank API."""

    title = "Cohere Reranker"
    description = (
        "Re-ranks candidate passages using Cohere's hosted Rerank API. "
        "Requires a Cohere API key. High quality but incurs latency and "
        "per-query cost."
    )
    author = "OpenContracts"
    dependencies = ["requests"]
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT, FileTypeEnum.DOCX]

    @dataclass
    class Settings:
        """Configuration schema for :class:`CohereReranker`."""

        cohere_api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=True,
                    description="Cohere API key.",
                    env_var="COHERE_API_KEY",
                )
            },
        )
        cohere_model: str = field(
            default=_DEFAULT_MODEL,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Cohere rerank model identifier (e.g. 'rerank-v3.5' "
                        "or 'rerank-multilingual-v3.0')."
                    ),
                    env_var="COHERE_RERANK_MODEL",
                )
            },
        )
        cohere_endpoint: str = field(
            default=_DEFAULT_ENDPOINT,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Cohere rerank endpoint URL.",
                    env_var="COHERE_RERANK_ENDPOINT",
                )
            },
        )
        timeout_seconds: int = field(
            default=RERANKER_REQUEST_TIMEOUT_SECONDS,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="HTTP request timeout in seconds.",
                    env_var="RERANKER_REQUEST_TIMEOUT_SECONDS",
                )
            },
        )

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        s = self.settings if self.settings is not None else self.Settings()

        api_key: str = all_kwargs.get("cohere_api_key", s.cohere_api_key)
        model: str = all_kwargs.get("cohere_model", s.cohere_model)
        endpoint: str = all_kwargs.get("cohere_endpoint", s.cohere_endpoint)
        timeout: int = int(all_kwargs.get("timeout_seconds", s.timeout_seconds))

        if not api_key:
            logger.error("CohereReranker has no API key configured; skipping rerank.")
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        payload: dict[str, Any] = {
            "model": model,
            "query": query,
            "documents": passages,
        }
        top_k = all_kwargs.get("top_k")
        if top_k is not None:
            # Cohere calls this ``top_n``.
            payload["top_n"] = int(top_k)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                endpoint, json=payload, headers=headers, timeout=timeout
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("CohereReranker request failed: %s", exc)
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        if response.status_code != 200:
            logger.warning(
                "CohereReranker returned status %s: %s",
                response.status_code,
                response.text[:200],
            )
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning("CohereReranker returned non-JSON body: %s", exc)
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        # Cohere's v2 rerank response shape:
        #   {"results": [{"index": 2, "relevance_score": 0.91}, ...], ...}
        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            logger.warning(
                "CohereReranker response missing 'results': keys=%s",
                list(body.keys()) if isinstance(body, dict) else type(body),
            )
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        out: list[RerankResult] = []
        for item in raw_results:
            try:
                idx = int(item["index"])
                score = float(item["relevance_score"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append(RerankResult(index=idx, score=score))

        if not out:
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]
        return out
