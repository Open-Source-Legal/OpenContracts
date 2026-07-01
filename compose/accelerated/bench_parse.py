#!/usr/bin/env python3
"""
Benchmark a running docling-parser's /parse/ endpoint on a sample PDF.

Use it to measure the REAL accelerator speedup on YOUR hardware — the iGPU
result in the README does not generalize to discrete GPUs, so measure.

    # start the accelerated parser (e.g. ROCm on an AMD box). NOTE the build
    # context is compose/accelerated (the Dockerfile COPYs the shared detector +
    # entrypoint from there), selected with -f:
    #   docker build --build-arg ACCEL=rocm -f compose/accelerated/docling/Dockerfile \
    #     -t oc-docling:rocm compose/accelerated
    #   docker run -d --name dl-gpu -p 8014:8000 \
    #     --device /dev/kfd --device /dev/dri --group-add video \
    #     oc-docling:rocm
    # start a CPU baseline of the SAME image:
    #   docker run -d --name dl-cpu -p 8015:8000 -e DOCLING_ACCEL=cpu oc-docling:rocm

    python bench_parse.py path/to/sample.pdf --gpu-port 8014 --cpu-port 8015

Prints per-service warmup + steady-state parse time and the speedup. The first
parse on a GPU includes one-time model load / kernel compile — reported as
"warmup" separately from the steady-state average.
"""

import argparse
import base64
import json
import sys
import time
import urllib.request


def parse_once(port: int, payload: bytes, timeout: int = 1200) -> float:
    req = urllib.request.Request(
        f"http://localhost:{port}/parse/",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t = time.time()
    resp = urllib.request.urlopen(req, timeout=timeout)
    resp.read()
    return time.time() - t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--gpu-port", type=int, default=8014)
    ap.add_argument("--cpu-port", type=int, default=8015)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    pdf = open(args.pdf, "rb").read()
    payload = json.dumps(
        {
            "filename": "bench.pdf",
            "pdf_base64": base64.b64encode(pdf).decode(),
            "force_ocr": False,
            "roll_up_groups": True,
            "llm_enhanced_hierarchy": False,
        }
    ).encode()

    print(f"PDF: {args.pdf} ({len(pdf)} bytes), {args.runs} timed runs each\n")
    res = {}
    for name, port in [("GPU", args.gpu_port), ("CPU", args.cpu_port)]:
        try:
            warm = parse_once(port, payload)
            runs = [parse_once(port, payload) for _ in range(args.runs)]
            avg = sum(runs) / len(runs)
            res[name] = avg
            print(
                f"{name:4} warmup={warm:7.1f}s  steady avg={avg:6.2f}s  "
                f"runs={[round(x, 2) for x in runs]}"
            )
        except Exception as e:  # noqa: BLE001
            print(f"{name:4} FAILED: {str(e)[:160]}")

    if "GPU" in res and "CPU" in res and res["GPU"] > 0:
        print(f"\n=> GPU steady-state speedup: {res['CPU'] / res['GPU']:.2f}x")
        print("   (factor in the one-time GPU warmup for short-lived containers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
