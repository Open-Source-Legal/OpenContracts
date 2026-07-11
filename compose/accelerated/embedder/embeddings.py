import base64
import io
import os

import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

# Load configuration (defaults unchanged for backward compatibility)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "multi-qa-MiniLM-L6-cos-v1")
TOKENIZER_MODEL = os.getenv(
    "TOKENIZER_MODEL", "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"
)
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE", "10485760"))  # 10MB default

print(f"Loading embedding model: {EMBEDDING_MODEL}")

# Auto-accelerated inference. The container entrypoint runs accel_detect.py and
# exports EMBED_BACKEND + EMBED_DEVICE for the best device available (CUDA / ROCm
# / Intel-XPU / Intel-GPU+NPU via OpenVINO / CPU). Both default to the CPU torch
# path so a bare `import` (e.g. tests, no entrypoint) still works unchanged.
#   EMBED_BACKEND=openvino  EMBED_DEVICE=GPU|NPU|CPU  -> OpenVINO (Intel)
#   EMBED_BACKEND=torch     EMBED_DEVICE=cuda|xpu|mps|cpu -> torch
# OV_MODEL_DIR points at a pre-exported OpenVINO IR baked into the image so the
# torch->IR export is not paid on boot. backend="openvino" carries the model's
# mean-pooling + L2-normalize, so output matches torch (FP16 cosine > 0.999).
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "torch").lower()
EMBED_DEVICE = os.getenv("EMBED_DEVICE", "cpu")
OV_MODEL_DIR = os.getenv("OV_MODEL_DIR", "").strip()
REQUIRE_ACCELERATOR = os.getenv("REQUIRE_ACCELERATOR", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


NPU_BATCH = int(os.getenv("NPU_BATCH", "32"))
NPU_SEQ_LEN = int(os.getenv("NPU_SEQ_LEN", "512"))


def _load_model():
    if EMBED_BACKEND == "openvino":
        src = OV_MODEL_DIR or EMBEDDING_MODEL
        if EMBED_DEVICE.upper().startswith("NPU"):
            # The NPU needs a fully-static graph; ST's dynamic encode() won't
            # compile on it. Use the static-shape engine (output verified
            # identical to ST, mean cosine 1.0). Runs on a SEPARATE accelerator
            # from the iGPU, so it doesn't contend with the Docling parser.
            from ov_npu import NpuEmbedder

            m = NpuEmbedder(
                src, device=EMBED_DEVICE, batch=NPU_BATCH, seq_len=NPU_SEQ_LEN
            )
            print(
                f"OpenVINO NPU engine ready ({EMBED_DEVICE}, batch={NPU_BATCH}, seq={NPU_SEQ_LEN})"
            )
            return m, "openvino", EMBED_DEVICE, None
        # GPU/CPU: ST's dynamic OpenVINO path (carries pooling + normalize). The
        # OV device goes in model_kwargs; the ST `device` is the torch device for
        # the cheap pooling modules (keep cpu — "GPU" is not a torch device).
        m = SentenceTransformer(
            src,
            backend="openvino",
            device="cpu",
            model_kwargs={"device": EMBED_DEVICE},
        )
        print(f"OpenVINO backend ready on device={EMBED_DEVICE} (source={src})")
        return m, "openvino", EMBED_DEVICE, None
    m = SentenceTransformer(EMBEDDING_MODEL, device=EMBED_DEVICE)
    print(f"torch backend ready on device={EMBED_DEVICE}")
    return m, "torch", EMBED_DEVICE, None


try:
    model, ACTIVE_BACKEND, ACTIVE_DEVICE, FALLBACK_REASON = _load_model()
except Exception as exc:  # hardware/driver dependent — never fail to start
    if REQUIRE_ACCELERATOR:
        raise RuntimeError(
            f"Required accelerator {EMBED_BACKEND}/{EMBED_DEVICE} failed to load"
        ) from exc
    print(
        f"{EMBED_BACKEND}/{EMBED_DEVICE} unavailable ({exc}); falling back to torch+cpu"
    )
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    ACTIVE_BACKEND = "torch"
    ACTIVE_DEVICE = "cpu"
    FALLBACK_REASON = str(exc)


def _is_accelerated(device: str) -> bool:
    # OpenVINO devices may carry an index suffix ("CPU.0") and torch devices a
    # colon suffix ("cuda:1"); compare the base device family so an indexed CPU
    # device never satisfies REQUIRE_ACCELERATOR.
    return device.upper().split(".", 1)[0].split(":", 1)[0] != "CPU"


ACCELERATED = _is_accelerated(ACTIVE_DEVICE)
if REQUIRE_ACCELERATOR and not ACCELERATED:
    raise RuntimeError(
        f"REQUIRE_ACCELERATOR is set but selected {ACTIVE_BACKEND}/{ACTIVE_DEVICE}"
    )

# SentenceTransformer already performs its own device batches. The old service
# split a 100-text HTTP request into separate eight-item encode() calls first,
# which discarded most GPU throughput and made the fixed-batch NPU pad 24 of 32
# rows on every call. Submit the complete flattened request once and let the
# backend use an accelerator-sized inference batch.
_configured_batch_size = os.getenv("INFERENCE_BATCH_SIZE") or os.getenv(
    "MAX_BATCH_SIZE"
)
if _configured_batch_size:
    INFERENCE_BATCH_SIZE = int(_configured_batch_size)
elif ACTIVE_DEVICE.upper().startswith("NPU"):
    INFERENCE_BATCH_SIZE = NPU_BATCH
elif ACTIVE_BACKEND == "openvino" and ACTIVE_DEVICE.upper().startswith("GPU"):
    # Measured best on the Intel Arc 140V reference host. Larger batches lose
    # throughput on the shared-memory iGPU; discrete torch GPUs have enough
    # bandwidth to use the 128-row default below.
    INFERENCE_BATCH_SIZE = 64
elif ACCELERATED:
    INFERENCE_BATCH_SIZE = 128
else:
    INFERENCE_BATCH_SIZE = 32
if INFERENCE_BATCH_SIZE < 1:
    raise ValueError("INFERENCE_BATCH_SIZE must be at least 1")

# Backwards-compatible module attribute for deployments that introspect it.
MAX_BATCH_SIZE = INFERENCE_BATCH_SIZE
backend = ACTIVE_BACKEND


def _check_image_support():
    """Check if model supports image encoding."""
    try:
        dummy = Image.new("RGB", (224, 224))
        model.encode(dummy)
        return True
    except Exception:
        return False


SUPPORTS_IMAGES = _check_image_support()
print(f"Image embedding support: {SUPPORTS_IMAGES}")

# Load tokenizer only for text-only models (needed for chunking)
# CLIP models don't need chunking - they handle text directly
tokenizer = None
if TOKENIZER_MODEL and not SUPPORTS_IMAGES:
    print(f"Loading tokenizer: {TOKENIZER_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_MODEL)


def decode_image(image_base64: str) -> Image.Image:
    """Decode base64 image string to PIL Image."""
    image_bytes = base64.b64decode(image_base64)
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise ValueError(f"Image exceeds maximum size of {MAX_IMAGE_SIZE} bytes")
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def embed_image(image_base64: str) -> np.ndarray:
    """Generate embedding for a base64-encoded image."""
    if not SUPPORTS_IMAGES:
        raise NotImplementedError("Current model does not support image embeddings")
    image = decode_image(image_base64)
    embedding = model.encode(image)
    return embedding.reshape(1, -1)


def embed_images_batch(images_base64: list[str]) -> list[np.ndarray]:
    """Generate embeddings for multiple images."""
    if not SUPPORTS_IMAGES:
        raise NotImplementedError("Current model does not support image embeddings")
    images = [decode_image(img) for img in images_base64]
    embeddings = model.encode(images)
    return [emb.reshape(1, -1) for emb in embeddings]


def chunk_by_transformers_tokens(
    content: str, max_token_length: int = 512, transformer_id: str = None
) -> list[str]:
    """
    Tokenizes a long string and splits it into substrings based on a specified maximum token length.

    Parameters:
    - content (str): The input text to be tokenized.
    - transformer_id (str): Model name for SentenceTransformer.
                            If None, uses the cached module-level tokenizer.
    - max_token_length (int): The maximum length for each chunk of tokens.

    Returns:
    - List[str]: List of substrings, each specified max tokens or fewer tokens.
    """
    # Use cached tokenizer if using default model, otherwise load specified one
    if transformer_id is None or transformer_id == TOKENIZER_MODEL:
        tok = tokenizer
    else:
        tok = AutoTokenizer.from_pretrained(transformer_id)

    if tok is None:
        # No tokenizer available (CLIP model) - return text as single chunk
        return [content]

    tokens = tok.tokenize(content)

    # Split the tokens into chunks
    tokenized_chunks = [
        tokens[i : i + max_token_length]
        for i in range(0, len(tokens), max_token_length)
    ]
    chunk_lengths = [len(" ".join(chunk)) for chunk in tokenized_chunks]

    chunks = []
    next_start = 0
    for index, length in enumerate(chunk_lengths):

        if index == len(chunk_lengths) - 1:
            chunk = content[next_start:]
        else:
            chunk = content[next_start : next_start + length]
            next_start += length

        if len(chunk) == 0 or chunk is None:
            print("Skipping empty chunk!")
            continue

        chunks.append(chunk)

    return chunks


def embed_text(text: str) -> np.ndarray:
    """Generate embedding for text."""
    # CLIP models: encode directly (no chunking needed, handles up to 77 tokens)
    # Text-only models: use chunking as before
    if SUPPORTS_IMAGES:
        # CLIP model - direct encoding (text truncated to ~77 tokens by model)
        embedding = model.encode(text)
        return embedding.reshape(1, -1)
    else:
        # Text-only model - use chunking
        return _embed_text_chunked(text)


def _embed_text_chunked(text: str) -> np.ndarray:
    """Embed text with chunking (for text-only models)."""
    window = 512  # Use full model capacity

    chunks = chunk_by_transformers_tokens(text, max_token_length=window)
    print(f"Initial chunk length: {len(chunks)}")

    # Limit to 5 chunks - benchmarks show 4-5 chunks optimal for throughput
    # while still capturing document semantics
    chunks = chunks[:5]
    print(f"\tFinal chunk length following truncation: {len(chunks)}")

    embeddings = model.encode(
        chunks,
        batch_size=INFERENCE_BATCH_SIZE,
        show_progress_bar=False,
    )
    avg_embedding: np.ndarray = np.mean(embeddings, axis=0, keepdims=True)
    return avg_embedding


def embed_texts_batch(texts: list[str], max_batch_size: int = None) -> list[np.ndarray]:
    """
    Embed multiple texts efficiently by batching model.encode() calls.

    Parameters:
    - texts: List of texts to embed
    - max_batch_size: Device inference batch size used by model.encode().
                      Defaults to a backend-aware value (32 on CPU, 128 on GPU,
                      or the NPU's compiled static batch size).

    Returns:
    - List of embedding arrays, one per input text
    """
    # CLIP models: encode directly without chunking
    if SUPPORTS_IMAGES:
        embeddings = model.encode(texts)
        return [emb.reshape(1, -1) for emb in embeddings]

    # Text-only models: use chunking
    if max_batch_size is None:
        max_batch_size = INFERENCE_BATCH_SIZE
    if max_batch_size < 1:
        raise ValueError("max_batch_size must be at least 1")
    window = 512  # Use full model capacity
    all_chunks = []
    chunk_boundaries = []  # Track which chunks belong to which text

    # Chunk all texts
    for text in texts:
        chunks = chunk_by_transformers_tokens(text, max_token_length=window)
        chunks = chunks[:5]  # Same limit as embed_text
        chunk_boundaries.append((len(all_chunks), len(all_chunks) + len(chunks)))
        all_chunks.extend(chunks)

    # One encode() call lets SentenceTransformer/OpenVINO schedule full device
    # batches and sort by sequence length. NpuEmbedder accepts the same argument
    # and internally fills its compiled fixed-size batches without outer padding.
    all_embeddings = model.encode(
        all_chunks,
        batch_size=max_batch_size,
        show_progress_bar=False,
    )

    # Average embeddings for each text
    results = []
    for start, end in chunk_boundaries:
        text_embeddings = np.array(all_embeddings[start:end])
        avg_embedding = np.mean(text_embeddings, axis=0, keepdims=True)
        results.append(avg_embedding)

    return results
