"""In-process cross-encoder reranker (BGE / sentence-transformers).

Uses the ``sentence_transformers.CrossEncoder`` API to score ``(query, passage)``
pairs with an open-weights cross-encoder. The model is loaded lazily on first
use and cached per-model-name so subsequent calls are cheap.

This backend does NOT require any external services but DOES require the
``sentence-transformers`` and ``torch`` packages to be installed. Those are
optional dependencies; if they're missing the component raises a clear
``ImportError`` the first time :meth:`rerank` is called. Discovery of the
class itself never imports them, so environments without the packages can
still run (the cross-encoder will just fail closed if it's accidentally
selected).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.reranker import BaseReranker, RerankResult
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Model cache
# --------------------------------------------------------------------------- #
# sentence-transformers models are multi-hundred-MB objects; reloading them on
# every request is prohibitively expensive. Cache by ``(model_name, device)``
# so distinct configurations (CPU vs. GPU, different models) coexist. The
# cache is process-local, which is fine for gunicorn/uvicorn workers —
# reloading on fork is a non-issue because nothing is loaded until first use.
# --------------------------------------------------------------------------- #

_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_CACHE_LOCK = threading.Lock()


def _load_cross_encoder(model_name: str, device: str) -> Any:
    """Return a cached ``CrossEncoder`` instance, loading on first use."""
    key = (model_name, device)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    with _CACHE_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached

        try:
            # Import lazily so environments without sentence-transformers /
            # torch can still import this module.
            from sentence_transformers import CrossEncoder  # type: ignore
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ImportError(
                "CrossEncoderReranker requires the 'sentence-transformers' "
                "package (and 'torch'). Install with `pip install "
                "sentence-transformers` or configure a different reranker "
                "backend via PipelineSettings.default_reranker."
            ) from exc

        logger.info(
            "Loading CrossEncoder model '%s' on device '%s' (first use)",
            model_name,
            device,
        )
        device_arg = None if device in ("", "auto") else device
        model = CrossEncoder(model_name, device=device_arg)
        _MODEL_CACHE[key] = model
        return model


class CrossEncoderReranker(BaseReranker):
    """Rerank passages with an in-process cross-encoder model.

    Default model is ``BAAI/bge-reranker-v2-m3`` — open-weights, CPU-usable,
    ~300M parameters, multilingual, used as the reference reranker in issue
    #1349.
    """

    title = "Cross-Encoder Reranker (BGE)"
    description = (
        "Re-ranks candidate passages in-process using a sentence-transformers "
        "cross-encoder (default: BAAI/bge-reranker-v2-m3). Requires "
        "'sentence-transformers' and 'torch' to be installed."
    )
    author = "OpenContracts"
    dependencies = ["sentence-transformers", "torch"]
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT, FileTypeEnum.DOCX]

    @dataclass
    class Settings:
        """Configuration schema for :class:`CrossEncoderReranker`."""

        model_name: str = field(
            default="BAAI/bge-reranker-v2-m3",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "HuggingFace cross-encoder model identifier. Use any "
                        "sentence-transformers-compatible reranker."
                    ),
                    env_var="RERANKER_MODEL_NAME",
                )
            },
        )
        device: str = field(
            default="auto",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Torch device: 'cpu', 'cuda', 'cuda:0', 'mps', or "
                        "'auto' (let sentence-transformers choose)."
                    ),
                    env_var="RERANKER_DEVICE",
                )
            },
        )
        batch_size: int = field(
            default=32,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Number of (query, passage) pairs scored per forward "
                        "pass. Trade off throughput vs. memory."
                    ),
                    env_var="RERANKER_BATCH_SIZE",
                )
            },
        )
        max_length: int = field(
            default=512,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Maximum token length per (query, passage) pair. "
                        "Longer pairs are truncated by the tokenizer."
                    ),
                    env_var="RERANKER_MAX_LENGTH",
                )
            },
        )

    def _rerank_impl(
        self, query: str, passages: list[str], **all_kwargs
    ) -> list[RerankResult]:
        s = self.settings if self.settings is not None else self.Settings()

        model_name: str = all_kwargs.get("model_name", s.model_name)
        device: str = all_kwargs.get("device", s.device)
        batch_size: int = int(all_kwargs.get("batch_size", s.batch_size))
        max_length: int = int(all_kwargs.get("max_length", s.max_length))

        model = _load_cross_encoder(model_name, device)

        pairs = [(query, p or "") for p in passages]
        scores = model.predict(
            pairs,
            batch_size=batch_size,
            show_progress_bar=False,
            # Newer sentence-transformers versions accept max_length; older
            # versions ignore unknown kwargs on .predict() and warn instead.
            # We guard with try/except below for maximum compatibility.
        )

        # Some cross-encoders (activation=sigmoid) return 0D arrays per pair
        # or numpy floats — normalize to Python floats.
        try:
            score_list = [float(s) for s in scores]
        except TypeError:
            # Single-pair responses may come back as a scalar
            score_list = [float(scores)]

        if len(score_list) != len(passages):
            logger.warning(
                "CrossEncoder returned %d scores for %d passages; "
                "padding with -inf.",
                len(score_list),
                len(passages),
            )
            # Defensive: pad to match input length
            while len(score_list) < len(passages):
                score_list.append(float("-inf"))
            score_list = score_list[: len(passages)]

        # Use max_length to silence 'argument ignored' warnings on older
        # versions; newer versions pass it to the tokenizer.
        del max_length  # noqa: F841 (not used on this path; reserved for future)

        return [
            RerankResult(index=i, score=score_list[i]) for i in range(len(passages))
        ]
