# OpenContracts vector embedder — auto-accelerated, "just works" local image.
#
# ONE image picks the best device available at RUNTIME (CUDA / ROCm / Intel
# XPU+OpenVINO / NPU / CPU) and falls back to CPU. The accelerator FAMILY for the
# torch wheel is chosen at BUILD time via --build-arg ACCEL=... because torch's
# cuda/rocm/xpu/cpu wheels are mutually exclusive. OpenVINO is ALWAYS present, so
# every variant supports Intel GPU/NPU + CPU regardless of ACCEL.
#
#   ACCEL=auto|cpu  -> CPU torch  (+ OpenVINO Intel GPU/NPU/CPU)        [default]
#   ACCEL=xpu       -> Intel-GPU torch (+ OpenVINO)
#   ACCEL=cuda      -> NVIDIA torch (+ OpenVINO Intel/CPU)
#   ACCEL=rocm      -> AMD torch    (+ OpenVINO Intel/CPU)
#
# Build:  docker build --build-arg ACCEL=auto -t oc-embedder:auto .
# Run  :  docker run --device /dev/dri --group-add "$(stat -c '%g' /dev/dri/renderD128)" ...
#         (add --gpus all for CUDA; --device /dev/kfd --device /dev/dri for ROCm)
FROM openvino/ubuntu24_runtime@sha256:3eab9bc3f643e27526f347dd6fba15e95eee2c07257570bf988314dd37301aa0
USER root
WORKDIR /app

ARG ACCEL=auto
ARG TORCH_VERSION=2.6.0

# Install the one torch wheel for the chosen accelerator family first. Doing
# this before sentence-transformers prevents pip from temporarily installing a
# second, multi-gigabyte CUDA wheel from PyPI into every image variant.
RUN set -eux; \
    case "${ACCEL}" in \
      cuda)  IDX="https://download.pytorch.org/whl/cu124" ;; \
      rocm)  IDX="https://download.pytorch.org/whl/rocm6.2.4" ;; \
      xpu)   IDX="https://download.pytorch.org/whl/xpu" ;; \
      auto|cpu) IDX="https://download.pytorch.org/whl/cpu" ;; \
      *) echo "Unsupported ACCEL=${ACCEL}; expected auto, cpu, xpu, cuda, or rocm" >&2; exit 2 ;; \
    esac; \
    echo "ACCEL=${ACCEL} -> torch index ${IDX}"; \
    pip install --no-cache-dir "torch==${TORCH_VERSION}" --index-url "${IDX}"

# Service deps + OpenVINO-backed sentence-transformers (covers Intel GPU/NPU/CPU).
RUN pip install --no-cache-dir \
      flask gunicorn numpy "Pillow>=10" python-decouple requests \
      "sentence-transformers[openvino]==5.6.0" \
      "transformers==4.57.6" \
      "optimum-intel[openvino]==1.27.0"; \
    pip check

ENV EMBEDDING_MODEL=multi-qa-MiniLM-L6-cos-v1 \
    TOKENIZER_MODEL=sentence-transformers/multi-qa-MiniLM-L6-cos-v1 \
    HF_HOME=/models/hf

# Pre-export the model to OpenVINO IR at BUILD time (CPU; no device needed) so
# the torch->IR export + weight download are baked in, not paid on every boot.
RUN python3 -c "import os; from sentence_transformers import SentenceTransformer; \
m=SentenceTransformer(os.environ['EMBEDDING_MODEL'], backend='openvino'); \
m.save_pretrained('/models/ov-embedder'); print('exported OpenVINO IR')"

# Detector + entrypoint (shared, single source at the build-context root).
COPY accel_detect.py /opt/accel/accel_detect.py
COPY entrypoint.sh /opt/accel/entrypoint.sh
RUN chmod +x /opt/accel/entrypoint.sh

COPY embedder/batching.py embedder/embeddings.py embedder/main.py embedder/ov_npu.py embedder/service_runtime.py /app/

# GUNICORN_WORKERS must stay 1: DynamicBatcher and SerializedModelOwner
# (embedder/batching.py, embedder/service_runtime.py) are per-process
# singletons. Raising worker count silently defeats request coalescing and
# loads a duplicate copy of the model per worker (GPU OOM risk on
# constrained VRAM). Scale GUNICORN_THREADS instead.
ENV OV_MODEL_DIR=/models/ov-embedder \
    EMBED_ACCEL=auto \
    PORT=8000 \
    GUNICORN_WORKERS=1 \
    GUNICORN_THREADS=8 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000
ENTRYPOINT ["/opt/accel/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn --bind :${PORT} --workers ${GUNICORN_WORKERS} --threads ${GUNICORN_THREADS} --timeout 0 main:app"]
