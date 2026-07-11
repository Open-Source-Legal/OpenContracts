#!/usr/bin/env bash
# Auto-detect the best available accelerator, export the service's device env,
# then exec the real service command. Idempotent + CPU-safe: if no accelerator
# is visible (or detection fails), the service runs on CPU.
#
# Honor explicit overrides: set EMBED_ACCEL / DOCLING_ACCEL to force a choice
# (e.g. EMBED_ACCEL=openvino:NPU, DOCLING_ACCEL=cpu). "auto" (default) detects.
set -euo pipefail

DETECT="${ACCEL_DETECT:-/opt/accel/accel_detect.py}"

use_cpu_defaults() {
    export EMBED_BACKEND="torch"
    export EMBED_DEVICE="cpu"
    export DOCLING_ACCELERATOR_DEVICE="cpu"
}

if [ -f "$DETECT" ]; then
    echo "[entrypoint] detecting accelerators..."
    set +e
    detected_env="$(python3 "$DETECT" --env)"
    detect_status=$?
    set -e

    if [ "$detect_status" -eq 0 ]; then
        detected_embed_backend=""
        detected_embed_device=""
        detected_docling_device=""
        while IFS='=' read -r key value; do
            case "$key" in
                EMBED_BACKEND) detected_embed_backend="$value" ;;
                EMBED_DEVICE) detected_embed_device="$value" ;;
                DOCLING_ACCELERATOR_DEVICE) detected_docling_device="$value" ;;
                "") ;;
                *)
                    echo "[entrypoint] detector returned unexpected key: $key" >&2
                    detect_status=1
                    ;;
            esac
        done <<< "$detected_env"

        if [ -z "$detected_embed_backend" ] || \
           [ -z "$detected_embed_device" ] || \
           [ -z "$detected_docling_device" ]; then
            echo "[entrypoint] detector returned an incomplete environment" >&2
            detect_status=1
        fi
    fi

    if [ "$detect_status" -eq 0 ]; then
        export EMBED_BACKEND="$detected_embed_backend"
        export EMBED_DEVICE="$detected_embed_device"
        export DOCLING_ACCELERATOR_DEVICE="$detected_docling_device"
        echo "[entrypoint] EMBED_BACKEND=$EMBED_BACKEND "\
"EMBED_DEVICE=$EMBED_DEVICE "\
"DOCLING_ACCELERATOR_DEVICE=$DOCLING_ACCELERATOR_DEVICE"
    elif [ "$detect_status" -eq 2 ]; then
        echo "[entrypoint] invalid accelerator configuration; refusing to start" >&2
        exit 2
    else
        echo "[entrypoint] detection failed; using CPU defaults" >&2
        use_cpu_defaults
    fi
else
    echo "[entrypoint] no detector at $DETECT; using CPU defaults" >&2
    use_cpu_defaults
fi

exec "$@"
