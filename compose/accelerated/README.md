# Hardware-accelerated parser + embedder (Intel XPU/NPU · CUDA · ROCm)

Locally-built, **auto-detecting** replacements for the `docling-parser` and
`vector-embedder` microservices. Each image picks the best compute device
available at startup and **falls back to CPU**, so the same image "just works"
on whatever host it lands on.

Measured on the Intel **Lunar Lake** reference host (Core Ultra 7 258V, Arc 140V
iGPU + NPU):

| Service | Best device | Measured | Verdict |
|---|---|---|---|
| `vector-embedder` | Intel **NPU** (OpenVINO) | **~11×** vs CPU (GPU variant **~15×**), output identical to reference | **Deploy it.** Embeddings run per-annotation (high volume) and are batched — the iGPU/NPU is a clean win. |
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

The embedder prefers the NPU so that — on the rare host where Docling *does*
benefit from the iGPU — the two services run on separate engines without
contending.

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
| Intel (NPU+GPU) | `openvino:NPU` | `xpu` |
| Intel (GPU only) | `openvino:GPU` | `xpu` |
| NVIDIA | `torch:cuda` | `cuda` |
| AMD (ROCm) | `torch:cuda` | `cuda` |
| Apple | `torch:mps` | `mps` |
| none | `openvino:CPU` / `torch:cpu` | `cpu` |

The container `entrypoint.sh` runs the detector, exports the device env, then
execs the service. Override with `EMBED_ACCEL` / `DOCLING_ACCEL`
(`auto` | `cpu` | `xpu` | `cuda` | `rocm`, or for the embedder a fully-qualified
`openvino:GPU` / `openvino:NPU` / `torch:xpu`).

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
Output is **numerically identical** to the sentence-transformers reference
(verified mean cosine = `1.00000`). Tunable via `NPU_BATCH` (default 32) /
`NPU_SEQ_LEN` (default 128).

## Best target: a discrete Intel Arc (Battlemage) workstation GPU

The iGPU result above is the *floor*. A **discrete Intel Arc Pro B-series**
(Battlemage / Xe2 — e.g. Arc Pro B70: 32 Xe2 cores, 256 XMX engines, 32 GB GDDR6
@ 608 GB/s, 367 INT8 TOPS) is the same architecture this stack already targets,
but with dedicated VRAM and ~10× the compute — exactly what flips Docling out of
the iGPU "wash" into the discrete-GPU regime, and a great host for the
[remote-ingest worker](../../scripts/remote_ingest/README.md). Both services use
`ACCEL=xpu` here (discrete Arc has **no NPU**, so the embedder routes to
`openvino:GPU` — the 32 GB VRAM easily hosts both services on one card; with
several cards, dedicate or scale out). Then **benchmark it** — don't trust the
iGPU numbers:

```bash
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)
OC_DOCLING_ACCEL=xpu OC_EMBED_ACCEL=auto \
  docker compose -f local.yml -f compose/accelerated/accel.override.yml build \
      docling-parser vector-embedder
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

```bash
# Render-group GID is host-specific — set it once:
export RENDER_GID=$(stat -c '%g' /dev/dri/renderD128)

# Build the accelerated images (Intel default: docling=xpu, embedder=auto):
docker compose -f local.yml -f compose/accelerated/accel.override.yml build \
    docling-parser vector-embedder

# Run the stack with the override merged on top:
docker compose -f local.yml -f compose/accelerated/accel.override.yml up
```

For NVIDIA build with `OC_DOCLING_ACCEL=cuda OC_EMBED_ACCEL=cuda` and pass GPUs
via the nvidia runtime instead of `/dev/dri`; for AMD use `ACCEL=rocm` and pass
`/dev/kfd` + `/dev/dri`.

## Benchmarking your host (don't extrapolate the iGPU numbers)

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
| `entrypoint.sh` | runs the detector, exports device env, execs the service (shared) |
| `bench_parse.py` | benchmark a running docling-parser's `/parse/` on your hardware |
| `embedder/Dockerfile` | OpenVINO base + sentence-transformers + torch (by `ACCEL`); pre-exports the OV IR |
| `embedder/ov_npu.py` | static-shape NPU embedding engine (drop-in `.encode()`) |
| `embedder/{embeddings,main}.py` | the embedder service (vendored, with the device-select load path) |
| `docling/Dockerfile` | docling image + Intel GPU runtime + torch wheel (by `ACCEL`) |
| `docling/sitecustomize.py` | torch+XPU integrated-GPU `mem_get_info` shim (auto-imported) |
| `accel.override.yml` | compose override that swaps both services into `local.yml` with device passthrough |

## Validated on the reference host

* OpenVINO sees `['CPU','GPU','NPU']` in-container with `/dev/dri` + `/dev/accel`
  + render group (no privileged mode).
* Embedder auto-detect → NPU: **127.6 texts/s** HTTP vs **11.5** on the
  production CPU embedder (~11×); GPU variant **168 texts/s** (~15×).
* `torch 2.6.0+xpu` in the docling image: `xpu available: True` (Intel Graphics);
  `decide_device(auto) -> xpu`.
