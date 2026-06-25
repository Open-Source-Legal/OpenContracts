- **Hardware-accelerated, auto-detecting parser + embedder images** for local /
  remote-worker deployments (`compose/accelerated/`). Each image picks the best
  compute device available at startup (CUDA · ROCm · Intel XPU · Intel NPU via
  OpenVINO · CPU) and falls back to CPU, so the same image "just works" on
  whatever host it lands on:
  - `compose/accelerated/accel_detect.py` — runtime hardware probe + device
    routing; `entrypoint.sh` applies it. Docling → torch device (cuda/xpu/cpu);
    embedder → OpenVINO (NPU preferred, then GPU) or torch, falling back to CPU.
  - `embedder/` — OpenVINO-backed sentence-transformers image with a static-shape
    **NPU engine** (`ov_npu.py`) whose output is numerically identical to the
    reference (mean cosine 1.0). The accelerator *family* for the torch fallback
    is a build-arg (`ACCEL=auto|cpu|xpu|cuda|rocm`).
  - `docling/` — Docling image rebuilt on the chosen torch wheel
    (`ACCEL=`), with an integrated-GPU `mem_get_info` compatibility shim
    (`sitecustomize.py`).
  - `accel.override.yml` — compose override that swaps both services into
    `local.yml` with GPU/NPU device passthrough.
  - `compose/accelerated/bench_parse.py` — measure the real Docling GPU-vs-CPU
    speedup on a given host.
  - `scripts/remote_ingest/remote_worker.accel.yml` — opt-in GPU override for the
    remote-ingest worker bundle, so the off-cluster workstation runs parse +
    embed on its GPU.
  Measured on an Intel Lunar Lake reference host: the embedder runs ~11× (NPU) /
  ~15× (iGPU) faster than the CPU service with identical output; Docling on the
  *integrated* GPU is a wash (~1.05×) — a discrete GPU (NVIDIA/AMD/Intel Arc
  Battlemage) is the right target for parser acceleration, so benchmark per host
  rather than assuming. See `compose/accelerated/README.md`.
