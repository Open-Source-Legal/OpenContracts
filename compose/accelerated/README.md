# Hardware-accelerated parser + embedder (Intel XPU/NPU · CUDA · ROCm)

Locally-built, **auto-detecting** replacements for the `docling-parser` and
`vector-embedder` microservices. The common image can fall back to CPU; the
vector-embedder vendor overlays require their selected accelerator so a broken
GPU runtime fails readiness instead of silently losing performance.

Measured on the Intel **Lunar Lake** reference host (Core Ultra 7 258V, Arc 140V
iGPU + NPU):

| Service | Best device | Measured | Verdict |
|---|---|---|---|
| `vector-embedder` | Intel **GPU** (OpenVINO) | **49.13×** vs the production CPU image at batch 100 / concurrency 3; minimum cosine `0.9999989` | **Deploy it.** Accelerator-sized inference, cross-request coalescing, and batched relationship embeddings remove the measured ingest bottleneck. |
| `docling-parser` | Intel iGPU (XPU) | **~1.05× (a wash)** + ~338 s kernel cold-start | **Keep on CPU here.** Docling is batch-1 CV inference; the *integrated* GPU's per-inference overhead cancels the compute gain. |

> **The Docling "wash" is iGPU-specific, NOT a general result.** A small,
> shared-memory integrated GPU doesn't help batch-1 detection/table inference. On
> a **discrete** GPU Docling accelerates a lot — Docling's own technical report
> (arXiv:2408.09869, NVIDIA L4) measures **14× layout, 8× EasyOCR, 4.3× table**,
> and the docs report **~5–6× end-to-end** (RTX 5090). Discrete AMD via ROCm
> shows batch-1 CV gains too (AMD's ROCm blog: 3.5× ResNet-152, 2.3× ViT at
> batch=1 on Instinct MI210 with `torch.compile` reduce-overhead). Levers on a
> real GPU: raise Docling's `layout_batch_size` / `ocr_batch_size` (default 4 →
> e.g. 64) to amortize per-inference overhead; OCR is the dominant cost (~60%)
> and the biggest GPU win. Caveats: GPU OCR under ROCm is the weak link (Docling
> docs: only RapidOCR+torch is "known to work" on GPU — EasyOCR-on-ROCm is
> unvalidated), and the table stage is not GPU-batched. **Build for your
> accelerator (`ACCEL=cuda`/`rocm`) and run the parse benchmark to get the real
> number** (see "Benchmarking your host"). Don't extrapolate the iGPU result.

The embedder prefers the GPU for throughput. The NPU remains an explicit option
when the GPU must be reserved for Docling or another workload.

## Why two images, not one

A single image cannot contain CUDA **and** ROCm **and** XPU torch — they are
mutually-exclusive `torch` wheels. So the **accelerator family** is chosen at
*build* time with `--build-arg ACCEL=`; the **device within that family** is
auto-selected at *run* time and degrades to CPU. This mirrors how PyTorch / vLLM
ship per-accelerator images.

```
ACCEL=auto|cpu  -> CPU torch     (embedder still gets Intel GPU/NPU via OpenVINO)
ACCEL=xpu       -> Intel-GPU torch
ACCEL=cuda      -> NVIDIA torch
ACCEL=rocm      -> AMD torch
```

The **embedder** always bundles OpenVINO, so every embedder variant supports
Intel GPU/NPU + CPU regardless of `ACCEL` — `ACCEL` only governs its (rarely
used) torch fallback path. The **docling** image is torch-only (docling has no
OpenVINO path), so its `ACCEL` directly selects the GPU it uses.

## Auto-detection

`accel_detect.py` probes the runtime and routes:

| Host | Embedder | Docling |
|---|---|---|
| Intel (NPU+GPU) | `openvino:GPU` | `xpu` |
| Intel (GPU only) | `openvino:GPU` | `xpu` |
| NVIDIA | `torch:cuda` | `cuda` |
| AMD (ROCm) | `torch:cuda` | `cuda` |
| Apple | `torch:mps` | `mps` |
| none | `openvino:CPU` / `torch:cpu` | `cpu` |

The container `entrypoint.sh` runs the detector once, assigns its allow-listed
device variables without evaluating shell code, then execs the service. Override
with `EMBED_ACCEL` / `DOCLING_ACCEL` (`auto` | `cpu` | `xpu` | `cuda` | `rocm`;
the embedder also accepts `npu` and fully-qualified values such as
`openvino:GPU`, `openvino:NPU`, `torch:cuda:1`, or `torch:xpu`). Invalid values
fail startup instead of silently selecting another device.

Inspect a host's routing without running a service:

```bash
docker run --rm --device /dev/dri --device /dev/accel/accel0 \
  --group-add "$(stat -c '%g' /dev/dri/renderD128)" \
  oc-embedder:auto python3 /opt/accel/accel_detect.py
```

> `--device /dev/accel/accel0` is the **Intel NPU** (Lunar Lake-class SoCs).
> Hosts without an NPU — including discrete Intel Arc, NVIDIA, and AMD — have no
> such node and Docker errors with "no such file or directory"; drop that
> `--device` and keep only `--device /dev/dri`.

## The NPU embedder (static-shape engine)

The Intel NPU requires a **fully static** compute graph; sentence-transformers'
dynamic `encode()` won't compile on it. `ov_npu.py` loads the pre-exported
OpenVINO IR, reshapes it to a fixed `[batch, seq]`, compiles on the NPU, and
reimplements encode (fixed-length tokenize → infer → mean-pool → L2-normalize).
Output is **numerically equivalent** to the sentence-transformers reference.
Tunable via `NPU_BATCH` (default 32) / `NPU_SEQ_LEN` (default 512); keeping the
full sequence length avoids the long-text truncation of the earlier 128-token
prototype.

## Best target: a discrete Intel Arc (Battlemage) workstation GPU

The iGPU result above is the *floor*. A **discrete Intel Arc Pro B-series**
(Battlemage / Xe2 — e.g. Arc Pro B70: 32 Xe2 cores, 256 XMX engines, 32 GB GDDR6
@ 608 GB/s, 367 INT8 TOPS) is the same architecture this stack already targets,
but with dedicated VRAM and ~10× the compute — exactly what flips Docling out of
the iGPU "wash" into the discrete-GPU regime, and a great host for the
[remote-ingest worker](../../scripts/remote_ingest/README.md). Docling uses the
XPU torch build while the embedder uses OpenVINO (discrete Arc has **no NPU**, so
the embedder routes to `openvino:GPU` — the 32 GB VRAM easily hosts both services
on one card; with several cards, dedicate or scale out). Then **benchmark it** —
don't trust the iGPU numbers:

```bash
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)
docker compose \
  -f local.yml \
  -f compose/accelerated/accel.override.yml \
  -f compose/accelerated/accel.intel.yml \
  build docling-parser vector-embedder
# parser GPU-vs-CPU on the real hardware:
docker build --build-arg ACCEL=xpu -f compose/accelerated/docling/Dockerfile -t oc-docling:xpu compose/accelerated
docker run -d --name dl-gpu -p 8014:8000 --device /dev/dri --group-add "$RENDER_GID" oc-docling:xpu
docker run -d --name dl-cpu -p 8015:8000 -e DOCLING_ACCEL=cpu oc-docling:xpu
python compose/accelerated/bench_parse.py sample.pdf --gpu-port 8014 --cpu-port 8015
```

Worth A/B-testing on the B-series: OpenVINO **INT8** for the embedder (the XMX
engines do 367 INT8 TOPS) and a higher Docling `layout_batch_size`/`ocr_batch_size`
to amortize per-page overhead across the big VRAM.

## Usage

The common override is intentionally CPU-safe and contains no device mounts.
Always merge the matching vendor overlay after it:

| Host | Required overlay | Host setup |
|---|---|---|
| CPU | `accel.cpu.yml` | none |
| Intel GPU | `accel.intel.yml` | set `RENDER_GID`; expose `/dev/dri` |
| Intel GPU + NPU | `accel.intel.yml` + `accel.intel-npu.yml` | same, plus `/dev/accel/accel0` |
| NVIDIA | `accel.nvidia.yml` | install/configure NVIDIA Container Toolkit |
| AMD ROCm | `accel.amd.yml` | set `VIDEO_GID` and `RENDER_GID`; expose `/dev/kfd` + `/dev/dri` |

Intel example:

```bash
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)

docker compose \
  -f local.yml \
  -f compose/accelerated/accel.override.yml \
  -f compose/accelerated/accel.intel.yml \
  up --build
```

If that Intel host has an NPU, append
`-f compose/accelerated/accel.intel-npu.yml` to expose it. The GPU remains the
default; set `EMBED_ACCEL=npu` to reserve the GPU for another workload.

NVIDIA example:

```bash
docker compose \
  -f local.yml \
  -f compose/accelerated/accel.override.yml \
  -f compose/accelerated/accel.nvidia.yml \
  up --build
```

AMD example:

```bash
export VIDEO_GID=$(stat -c '%g' /dev/kfd)
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)

docker compose \
  -f local.yml \
  -f compose/accelerated/accel.override.yml \
  -f compose/accelerated/accel.amd.yml \
  up --build
```

The vendor file selects the matching torch wheel family at build time. Runtime
auto-detection remains enabled. Set `EMBED_ACCEL` or `DOCLING_ACCEL` only when
you need to pin a particular visible device.

> **Security note (AMD ROCm only):** `accel.amd.yml` adds `cap_add: SYS_PTRACE`
> and `security_opt: seccomp=unconfined` to both `docling-parser` and
> `vector-embedder`. ROCm's profiling/debug tooling requires it; the
> Intel/NVIDIA overlays need neither. This is a real relaxation of container
> isolation relative to the other vendor overlays — weigh it accordingly if
> auditing the compose files for a shared or multi-tenant host.

## Benchmarking your host

Use the embedding benchmark for an alternating, paired baseline/candidate run.
It verifies backend metadata, fallback state, response shape, finite unit vectors,
and CPU/GPU cosine similarity before timing, then emits raw trials and a 25x gate:

```bash
python compose/accelerated/bench_embed.py \
  --baseline-url http://localhost:8015 \
  --candidate-url http://localhost:8014 \
  --candidate-expect-backend openvino \
  --candidate-expect-device GPU \
  --batch-sizes 100 --concurrencies 3 \
  --target-speedup 25 --fail-below-target \
  --json-out /tmp/embed-benchmark.json
```

The production CPU image has legacy readiness metadata, so add
`--allow-missing-backend-metadata` only when it is the baseline. Never use that
flag for the candidate: the benchmark must prove that the requested GPU served
the run.

### Parser benchmark

Whether the GPU helps **Docling** depends entirely on the hardware — measure it.
On a discrete AMD GPU (ROCm):

```bash
# build the ROCm docling image + a CPU baseline of the same image
docker build --build-arg ACCEL=rocm -f compose/accelerated/docling/Dockerfile -t oc-docling:rocm compose/accelerated

docker run -d --name dl-gpu -p 8014:8000 \
    --device /dev/kfd --device /dev/dri --group-add video --group-add render \
    --security-opt seccomp=unconfined oc-docling:rocm
docker run -d --name dl-cpu -p 8015:8000 -e DOCLING_ACCEL=cpu oc-docling:rocm

# confirm the GPU was selected, then time a real parse vs CPU
docker logs dl-gpu | grep -i "device"
python compose/accelerated/bench_parse.py some-sample.pdf --gpu-port 8014 --cpu-port 8015
```

On NVIDIA, build `ACCEL=cuda` and run with `--gpus all` (no `/dev/dri`). The
detector prints the chosen device in the container log on startup; `bench_parse.py`
reports the steady-state speedup and the one-time warmup separately. (If the GPU
is an `HSA_OVERRIDE_GFX_VERSION` case, set that env on the container — see ROCm
docs for your gfx target.)

## Files

Both Dockerfiles use **this directory** as their build context (`-f
{docling,embedder}/Dockerfile`), so the detector + entrypoint are a single shared
source — no per-image duplication.

| File | Purpose |
|---|---|
| `accel_detect.py` | hardware probe + device routing (shared by both images) |
| `entrypoint.sh` | applies allow-listed detector output and execs the service |
| `bench_embed.py` | correctness-gated CPU/GPU embedding throughput benchmark |
| `bench_parse.py` | benchmark a running docling-parser's `/parse/` on your hardware |
| `embedder/Dockerfile` | OpenVINO base + sentence-transformers + torch (by `ACCEL`); pre-exports the OV IR |
| `embedder/ov_npu.py` | static-shape NPU embedding engine (drop-in `.encode()`) |
| `embedder/{embeddings,main}.py` | the embedder service (vendored, with the device-select load path) |
| `embedder/batching.py` | coalesces concurrent HTTP requests into full accelerator batches |
| `docling/Dockerfile` | docling image + Intel GPU runtime + torch wheel (by `ACCEL`) |
| `docling/sitecustomize.py` | torch+XPU integrated-GPU `mem_get_info` shim (auto-imported) |
| `accel.override.yml` | common CPU-safe service build; contains no host devices |
| `accel.{cpu,intel,nvidia,amd}.yml` | vendor-specific image family and device passthrough |
| `accel.intel-npu.yml` | optional Intel NPU device passthrough, layered after `accel.intel.yml` |

## Validated on the reference host

* OpenVINO sees `['CPU','GPU','NPU']` in-container with `/dev/dri` + `/dev/accel`
  + render group (no privileged mode).
* The reproducible embedding gate (32/128-word deterministic legal text, batch
  100, concurrency 3, one warmup + five alternating trials) measured **817.59
  texts/s** on OpenVINO GPU versus **16.64 texts/s** on the production CPU
  image: **49.13×**. The minimum CPU/GPU cosine was **0.9999989** and the
  candidate reported `openvino/GPU` with no fallback.
* The earlier static NPU prototype measured 127.6 short texts/s. NPU is now
  opt-in and uses the full 512-token sequence length; benchmark it separately
  before choosing it over the GPU.
* `torch 2.6.0+xpu` in the docling image: `xpu available: True` (Intel Graphics);
  `decide_device(auto) -> xpu`.
