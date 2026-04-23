"""HTTP reranker that delegates scoring to an external microservice.

Mirrors the shape of :class:`MicroserviceEmbedder` so operators can run the
reranker model as a separate container (e.g. an instance of ``bge-reranker``
behind a small FastAPI wrapper) and point OpenContracts at it via
``PipelineSettings``.

Expected service contract:

.. code-block:: http

    POST /rerank
    Content-Type: application/json
    X-API-Key: <optional>

    {
      "query": "...",
      "passages": ["...", "...", "..."],
      "top_k": 10          // optional; service may return all candidates
    }

    200 OK
    {
      "results": [
        {"index": 2, "score": 7.42},
        {"index": 0, "score": 3.01},
        ...
      ]
    }

The service MUST echo back each candidate's original ``index`` so the caller
can rebuild the reranked list without shipping payload metadata over the
wire.
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
from opencontractserver.utils.cloud import maybe_add_cloud_run_auth

logger = logging.getLogger(__name__)


class MicroserviceReranker(BaseReranker):
    """Reranker that delegates to an external HTTP microservice."""

    title = "Microservice Reranker"
    description = (
        "Re-ranks candidate passages by calling an external HTTP reranker "
        "service (e.g. a containerized BGE or Jina cross-encoder). Cheap to "
        "scale horizontally; degrades to first-stage ordering on failure."
    )
    author = "OpenContracts"
    dependencies = ["requests"]
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT, FileTypeEnum.DOCX]

    @dataclass
    class Settings:
        """Configuration schema for :class:`MicroserviceReranker`."""

        reranker_microservice_url: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="Base URL of the reranker microservice.",
                    env_var="RERANKER_MICROSERVICE_URL",
                )
            },
        )
        reranker_api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=False,
                    description="Optional API key for the reranker service.",
                    env_var="RERANKER_MICROSERVICE_API_KEY",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication.",
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

    def _get_service_config(self, all_kwargs: dict) -> tuple[str, dict, int]:
        s = self.settings if self.settings is not None else self.Settings()

        service_url = all_kwargs.get(
            "reranker_microservice_url", s.reranker_microservice_url
        )
        api_key = all_kwargs.get("reranker_api_key", s.reranker_api_key)
        use_cloud_run_iam_auth = bool(
            all_kwargs.get("use_cloud_run_iam_auth", s.use_cloud_run_iam_auth)
        )
        timeout = int(all_kwargs.get("timeout_seconds", s.timeout_seconds))

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        headers = maybe_add_cloud_run_auth(
            service_url, headers, force=use_cloud_run_iam_auth
        )
        return service_url, headers, timeout

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        service_url, headers, timeout = self._get_service_config(all_kwargs)

        if not service_url:
            logger.error("MicroserviceReranker has no URL configured; skipping rerank.")
            # Return identity scores so the base class preserves input order.
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        payload: dict[str, Any] = {"query": query, "passages": passages}
        # Forward the optional top_k hint if a caller passed it through
        # direct_kwargs. Upstream services can use it to short-circuit.
        if "top_k" in all_kwargs and all_kwargs["top_k"] is not None:
            payload["top_k"] = int(all_kwargs["top_k"])

        try:
            response = requests.post(
                f"{service_url.rstrip('/')}/rerank",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("MicroserviceReranker request failed: %s", exc)
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        if response.status_code != 200:
            logger.warning(
                "MicroserviceReranker returned status %s: %s",
                response.status_code,
                response.text[:200],
            )
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning("MicroserviceReranker returned non-JSON body: %s", exc)
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        raw_results = body.get("results")
        if not isinstance(raw_results, list):
            logger.warning(
                "MicroserviceReranker response missing 'results' list: keys=%s",
                list(body.keys()) if isinstance(body, dict) else type(body),
            )
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        out: list[RerankResult] = []
        for item in raw_results:
            try:
                idx = int(item["index"])
                score = float(item["score"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append(RerankResult(index=idx, score=score))

        if not out:
            # Fall through to identity ordering rather than wiping results.
            n = len(passages)
            return [RerankResult(index=i, score=float(n - i)) for i in range(n)]

        return out
