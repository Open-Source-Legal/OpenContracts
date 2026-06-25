#!/usr/bin/env bash
# Auto-detect the best available accelerator, export the service's device env,
# then exec the real service command. Idempotent + CPU-safe: if no accelerator
# is visible (or detection fails), the service runs on CPU.
#
# Honor explicit overrides: set EMBED_ACCEL / DOCLING_ACCEL to force a choice
# (e.g. EMBED_ACCEL=openvino:NPU, DOCLING_ACCEL=cpu). "auto" (default) detects.
set -euo pipefail

DETECT="${ACCEL_DETECT:-/opt/accel/accel_detect.py}"

if [ -f "$DETECT" ]; then
    echo "[entrypoint] detecting accelerators..."
    python3 "$DETECT" || true            # human-readable report to logs
    # Apply the detector's choice unless the caller pinned the values already.
    if eval "$(python3 "$DETECT" --export 2>/dev/null)"; then
        echo "[entrypoint] EMBED_BACKEND=${EMBED_BACKEND:-} EMBED_DEVICE=${EMBED_DEVICE:-} DOCLING_ACCELERATOR_DEVICE=${DOCLING_ACCELERATOR_DEVICE:-}"
    else
        echo "[entrypoint] detection failed; using CPU defaults" >&2
    fi
else
    echo "[entrypoint] no detector at $DETECT; using preset env" >&2
fi

exec "$@"
