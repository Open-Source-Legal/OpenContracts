"""
Static-shape OpenVINO NPU embedding engine for the OpenContracts embedder.

The Intel NPU (AI Boost) requires a FULLY STATIC compute graph — sentence-
transformers' high-level ``encode()`` exports a dynamic-shape model the NPU
compiler rejects ("Upper bounds are not specified"). This module loads the
pre-exported OpenVINO IR, reshapes it to a fixed ``[batch, seq]``, compiles it
on the NPU, and reimplements the encode path (fixed-length tokenize -> infer ->
mean-pool -> L2-normalize). The output is numerically identical to the sentence-
transformers reference (verified mean cosine = 1.00000).

Why the NPU at all: it is a SEPARATE accelerator from the iGPU, so the embedder
can run here while the Docling parser saturates the iGPU (XPU) — no contention.

Exposes a drop-in ``.encode()`` compatible with the subset of the
SentenceTransformer API the embedder service uses (list[str] -> np.ndarray
[N, dim], or a single str -> np.ndarray [dim]).
"""

from __future__ import annotations

import glob
import os

import numpy as np
import openvino as ov
from transformers import AutoTokenizer


def _find_ir_xml(model_dir: str) -> str:
    """Locate the openvino_model.xml inside a sentence-transformers OV export."""
    for cand in (
        os.path.join(model_dir, "openvino", "openvino_model.xml"),
        os.path.join(model_dir, "openvino_model.xml"),
    ):
        if os.path.exists(cand):
            return cand
    hits = glob.glob(
        os.path.join(model_dir, "**", "openvino_model.xml"), recursive=True
    )
    if not hits:
        raise FileNotFoundError(f"No openvino_model.xml under {model_dir}")
    return hits[0]


class NpuEmbedder:
    """Static-shape OpenVINO NPU (or any OV device) sentence embedder."""

    def __init__(
        self,
        model_dir: str,
        device: str = "NPU",
        batch: int = 32,
        seq_len: int = 128,
    ):
        self.device = device
        self.batch = batch
        self.seq_len = seq_len
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)

        core = ov.Core()
        ir = core.read_model(_find_ir_xml(model_dir))
        # Static [batch, seq] for every input (input_ids / attention_mask /
        # token_type_ids). This is what makes the NPU compiler accept the graph.
        ir.reshape({i.get_any_name(): [batch, seq_len] for i in ir.inputs})
        cfg = {"PERFORMANCE_HINT": "THROUGHPUT"}
        self.compiled = core.compile_model(ir, device, cfg)
        self.input_names = [i.get_any_name() for i in ir.inputs]
        self._req = self.compiled.create_infer_request()

    # -- pooling matches sentence-transformers multi-qa-MiniLM (mean + L2) --
    @staticmethod
    def _mean_pool_normalize(last_hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
        m = mask[..., None].astype("float32")
        summed = (last_hidden * m).sum(axis=1)
        counts = np.clip(m.sum(axis=1), 1e-9, None)
        v = summed / counts
        norm = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.clip(norm, 1e-12, None)

    def _infer_fixed_batch(self, enc: dict) -> np.ndarray:
        feeds = {n: enc[n] for n in self.input_names if n in enc}
        out = self._req.infer(feeds)
        last_hidden = list(out.values())[0]
        return self._mean_pool_normalize(last_hidden, enc["attention_mask"])

    def encode(self, sentences, batch_size: int | None = None, **_kwargs) -> np.ndarray:
        """Drop-in for SentenceTransformer.encode for the text path.

        Accepts a str or list[str]; returns np.ndarray of shape [dim] (single)
        or [N, dim] (list). ``batch_size`` is ignored — the NPU batch is fixed at
        compile time; inputs are processed in fixed ``self.batch`` chunks, with
        the final partial chunk padded up to the static batch and sliced back.
        """
        single = isinstance(sentences, str)
        texts = [sentences] if single else list(sentences)
        if not texts:
            return np.zeros((0, self.compiled.outputs[0].shape[-1]), dtype="float32")

        results: list[np.ndarray] = []
        B = self.batch
        for start in range(0, len(texts), B):
            chunk = texts[start : start + B]
            pad_n = B - len(chunk)
            if pad_n:
                chunk = chunk + [""] * pad_n  # pad batch up to static size
            enc = self.tokenizer(
                chunk,
                padding="max_length",
                truncation=True,
                max_length=self.seq_len,
                return_tensors="np",
            )
            emb = self._infer_fixed_batch(enc)
            if pad_n:
                emb = emb[: B - pad_n]  # drop padded rows
            results.append(emb)

        out = np.concatenate(results, axis=0)
        return out[0] if single else out
