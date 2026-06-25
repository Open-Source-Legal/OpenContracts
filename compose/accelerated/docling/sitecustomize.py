"""
Transparent compatibility shim for torch+XPU on Intel INTEGRATED GPUs.

Auto-imported by CPython at startup (any sitecustomize on the path runs). On
Lunar Lake (and other iGPUs), the GPU driver does not expose the SYCL
``ext_intel_free_memory`` aspect, so ``torch.xpu.mem_get_info()`` raises. The
HuggingFace ``transformers`` model-load warmup (``caching_allocator_warmup``)
calls it unconditionally, which crashes docling's model loading on XPU even
though XPU compute itself works fine.

This shim wraps ``torch.xpu.mem_get_info`` to return a benign large value when
the underlying call raises, so model-load warmup succeeds and inference proceeds
on the iGPU. It is a no-op on discrete Arc GPUs (which DO report free memory) and
on non-XPU builds.
"""

try:  # never let the shim break interpreter startup
    import torch

    if hasattr(torch, "xpu") and hasattr(torch.xpu, "mem_get_info"):
        _orig_mem_get_info = torch.xpu.mem_get_info

        def _safe_mem_get_info(device=None):
            try:
                return _orig_mem_get_info(device)
            except Exception:
                # (free, total) — 8 GiB is a harmless stand-in; transformers
                # only uses it to size an allocation hint.
                return (8 * 1024**3, 8 * 1024**3)

        torch.xpu.mem_get_info = _safe_mem_get_info
except Exception:
    pass
