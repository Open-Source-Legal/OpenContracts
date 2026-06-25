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
FROM openvino/ubuntu24_runtime:latest
USER root
WORKDIR /app

ARG ACCEL=auto

# Service deps + OpenVINO-backed sentence-transformers (covers Intel GPU/NPU/CPU).
RUN pip install --no-cache-dir \
      flask gunicorn numpy "Pillow>=10" python-decouple requests \
      "sentence-transformers[openvino]>=3"

# Select the torch wheel for the chosen accelerator family. CPU is the safe
# default; the others pull vendor wheels that bundle their own runtime.
RUN set -eux; \
    case "${ACCEL}" in \
      cuda)  IDX="https://download.pytorch.org/whl/cu124" ;; \
      rocm)  IDX="https://download.pytorch.org/whl/rocm6.2" ;; \
      xpu)   IDX="https://download.pytorch.org/whl/xpu" ;; \
      *)     IDX="https://download.pytorch.org/whl/cpu" ;; \
    esac; \
    echo "ACCEL=${ACCEL} -> torch index ${IDX}"; \
    pip install --no-cache-dir --force-reinstall torch --index-url "${IDX}"

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

COPY embedder/embeddings.py embedder/main.py embedder/ov_npu.py /app/

ENV OV_MODEL_DIR=/models/ov-embedder \
    EMBED_ACCEL=auto \
    PORT=8000 \
    GUNICORN_WORKERS=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000
ENTRYPOINT ["/opt/accel/entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn --bind :${PORT} --workers ${GUNICORN_WORKERS} --threads 1 --timeout 0 main:app"]
