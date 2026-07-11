# OpenContracts Docling parser — auto-accelerated, "just works" local image.
#
# Starts FROM the working docling image (docling + deps + pre-baked models) and
# (1) adds the Intel Arc GPU userspace runtime, (2) swaps torch for the wheel of
# the chosen accelerator family, (3) auto-selects the device at RUNTIME.
#
# Docling 2.67's decide_device("auto") already picks cuda > xpu > mps > cpu from
# whatever torch supports — so once the right torch wheel is installed, docling
# auto-accelerates. The torch FAMILY is a build-arg (wheels are exclusive):
#   ACCEL=auto|cpu -> CPU torch
#   ACCEL=xpu      -> Intel-GPU torch (+ Intel GPU runtime libs)   [proven here]
#   ACCEL=cuda     -> NVIDIA torch
#   ACCEL=rocm     -> AMD torch
#
# Build: docker build --build-arg ACCEL=xpu -t oc-docling:xpu .
# Run  : docker run --device /dev/dri --group-add "$(stat -c '%g' /dev/dri/renderD128)" ...
#        (--gpus all for CUDA; --device /dev/kfd --device /dev/dri for ROCm)
FROM jscrudato/docsling-local@sha256:c35131594c257611131f9bcfd0af4b3adcf6064c96620ee67f42c3396acfd46b
USER root

ARG ACCEL=auto

# Intel GPU compute runtime (only needed for ACCEL=xpu, but cheap + harmless
# otherwise). gnupg provides `gpg` (the base lacks it -> the earlier exit 127).
RUN set -eux; \
    if [ "${ACCEL}" = "xpu" ] || [ "${ACCEL}" = "auto" ]; then \
      apt-get update; \
      apt-get install -y --no-install-recommends gnupg wget ca-certificates; \
      wget -qO- https://repositories.intel.com/gpu/intel-graphics.key \
        | gpg --dearmor -o /usr/share/keyrings/intel-graphics.gpg; \
      echo "deb [arch=amd64 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu jammy client" \
        > /etc/apt/sources.list.d/intel-gpu-jammy.list; \
      apt-get update; \
      apt-get install -y --no-install-recommends \
        libze-intel-gpu1 libze1 intel-opencl-icd; \
      rm -rf /var/lib/apt/lists/*; \
    fi

# Swap torch for the chosen accelerator wheel (force over the base's cu124 wheel).
RUN set -eux; \
    case "${ACCEL}" in \
      cuda)  IDX="https://download.pytorch.org/whl/cu124" ;; \
      rocm)  IDX="https://download.pytorch.org/whl/rocm6.2.4" ;; \
      xpu)   IDX="https://download.pytorch.org/whl/xpu" ;; \
      auto|cpu) IDX="https://download.pytorch.org/whl/cpu" ;; \
      *) echo "Unsupported ACCEL=${ACCEL}; expected auto, cpu, xpu, cuda, or rocm" >&2; exit 2 ;; \
    esac; \
    echo "ACCEL=${ACCEL} -> torch index ${IDX}"; \
    pip install --no-cache-dir --force-reinstall \
      torch==2.6.0 torchvision==0.21.0 --index-url "${IDX}"

# Detector + entrypoint (shared, single source at the build-context root).
COPY accel_detect.py /opt/accel/accel_detect.py
COPY entrypoint.sh /opt/accel/entrypoint.sh
RUN chmod +x /opt/accel/entrypoint.sh

# torch+XPU iGPU compatibility shim (auto-imported via PYTHONPATH). Fixes
# transformers' mem_get_info warmup crash on integrated GPUs (Lunar Lake).
COPY docling/sitecustomize.py /opt/accel/sitecustomize.py
ENV PYTHONPATH=/opt/accel

ENV DOCLING_ACCEL=auto \
    OMP_NUM_THREADS=4

EXPOSE 8000
ENTRYPOINT ["/opt/accel/entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
