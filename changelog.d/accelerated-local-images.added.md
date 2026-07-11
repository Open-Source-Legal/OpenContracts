- **Hardware-accelerated, auto-detecting parser + embedder images** for local /
  remote-worker deployments (`compose/accelerated/`). Each image picks the best
  compute device available at startup (CUDA · ROCm · Intel XPU · Intel NPU via
  OpenVINO · CPU). The common deployment remains CPU-safe, while vendor GPU
  overlays require the selected vector-embedder accelerator and make that
  service fail instead of silently degrading:
  - `compose/accelerated/accel_detect.py` — runtime hardware probe + device
    routing; `entrypoint.sh` applies it. Docling → torch device (cuda/xpu/cpu);
    embedder → OpenVINO GPU (then NPU) or vendor torch, falling back to CPU only
    in the common CPU-safe deployment.
  - `embedder/` — OpenVINO-backed sentence-transformers image with a static-shape
    **NPU engine** (`ov_npu.py`) whose output is numerically identical to the
    reference (mean cosine 1.0). The accelerator *family* for the torch fallback
    is a build-arg (`ACCEL=auto|cpu|xpu|cuda|rocm`).
  - `docling/` — Docling image rebuilt on the chosen torch wheel
    (`ACCEL=`), with an integrated-GPU `mem_get_info` compatibility shim
    (`sitecustomize.py`).
  - `accel.override.yml` plus explicit CPU, Intel, NVIDIA, and AMD overlays --
    vendor-correct image selection and device passthrough without editing YAML;
    Intel NPU passthrough is an optional additional overlay.
  - `compose/accelerated/bench_embed.py` — correctness-gated, reproducible
    baseline/candidate throughput benchmark with a configurable 25× gate;
    `bench_parse.py` measures Docling separately.
  - `scripts/remote_ingest/remote_worker.accel.yml` — opt-in GPU override for the
    remote-ingest worker bundle, so the off-cluster workstation runs parse +
    embed on its GPU.
  Measured on an Intel Lunar Lake reference host: the optimized OpenVINO GPU
  embedder reached 817.59 texts/s versus 16.64 texts/s for the production CPU
  image at batch 100 / concurrency 3 (49.13×, minimum cosine 0.9999989). Docling
  on the *integrated* GPU remains a wash (~1.05×), so benchmark parser and
  embedder performance separately. See `compose/accelerated/README.md`.
