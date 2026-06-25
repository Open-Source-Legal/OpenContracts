import os

from decouple import config
from embeddings import (
    SUPPORTS_IMAGES,
    embed_image,
    embed_images_batch,
    embed_text,
    embed_texts_batch,
)
from flask import Flask, jsonify, request

app = Flask(__name__)

# Health check endpoints (no auth required)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "multi-qa-MiniLM-L6-cos-v1")


@app.route("/health", methods=["GET"])
def health():
    """Liveness probe - returns 200 if server is running."""
    return jsonify({"status": "ok"}), 200


@app.route("/health/ready", methods=["GET"])
def health_ready():
    """Readiness probe - confirms model backend is initialized."""
    import embeddings

    # Check for model/backend - works with both old (model) and new (backend) versions
    is_ready = (
        getattr(embeddings, "backend", None) is not None
        or getattr(embeddings, "model", None) is not None
    )

    if not is_ready:
        return jsonify({"status": "not_ready", "error": "Model not loaded"}), 503
    return (
        jsonify(
            {
                "status": "ready",
                "model": EMBEDDING_MODEL,
                "supports_images": SUPPORTS_IMAGES,
            }
        ),
        200,
    )


API_KEY = config("VECTOR_EMBEDDER_API_KEY", default="abc123")
MAX_TEXTS_PER_BATCH = config("MAX_TEXTS_PER_BATCH", default=100, cast=int)
MAX_IMAGES_PER_BATCH = config("MAX_IMAGES_PER_BATCH", default=20, cast=int)


@app.route("/embeddings", methods=["POST"])
def generate_embeddings():
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    text = request.json.get("text")
    if not text:
        return jsonify({"error": "Text is required"}), 400

    embeddings = embed_text(text)
    return jsonify({"embeddings": embeddings.tolist()}), 200


@app.route("/embeddings/batch", methods=["POST"])
def generate_embeddings_batch():
    """
    Batch endpoint for embedding multiple texts efficiently.

    Request body:
    {
        "texts": ["text1", "text2", ...]
    }

    Response:
    {
        "embeddings": [[...], [...], ...]
    }
    """
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    texts = request.json.get("texts")
    if not texts:
        return jsonify({"error": "texts array is required"}), 400

    if not isinstance(texts, list):
        return jsonify({"error": "texts must be an array"}), 400

    if len(texts) == 0:
        return jsonify({"error": "texts array cannot be empty"}), 400

    if len(texts) > MAX_TEXTS_PER_BATCH:
        error_msg = (
            f"Batch size {len(texts)} exceeds maximum of {MAX_TEXTS_PER_BATCH} texts "
            "per request. Split into multiple requests."
        )
        return jsonify({"error": error_msg}), 400

    # Filter out empty texts
    valid_texts = [t for t in texts if t and isinstance(t, str)]
    if len(valid_texts) != len(texts):
        return jsonify({"error": "All texts must be non-empty strings"}), 400

    embeddings_list = embed_texts_batch(valid_texts)
    return jsonify({"embeddings": [emb.tolist() for emb in embeddings_list]}), 200


@app.route("/embeddings/image", methods=["POST"])
def generate_image_embedding():
    """
    Generate embedding for a single image.

    Request body:
    {
        "image": "<base64-encoded-image>"
    }

    Response:
    {
        "embeddings": [[0.1, -0.2, ...]]
    }
    """
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    if not SUPPORTS_IMAGES:
        return (
            jsonify({"error": "Image embeddings not supported by current model"}),
            501,
        )

    image_base64 = request.json.get("image")
    if not image_base64:
        return jsonify({"error": "image (base64) is required"}), 400

    try:
        embeddings = embed_image(image_base64)
        return jsonify({"embeddings": embeddings.tolist()}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to process image: {str(e)}"}), 400


@app.route("/embeddings/image/batch", methods=["POST"])
def generate_image_embeddings_batch():
    """
    Generate embeddings for multiple images.

    Request body:
    {
        "images": ["<base64-img1>", "<base64-img2>", ...]
    }

    Response:
    {
        "embeddings": [[[...]], [[...]], ...]
    }
    """
    api_key = request.headers.get("X-API-Key")
    if api_key != API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    if not SUPPORTS_IMAGES:
        return (
            jsonify({"error": "Image embeddings not supported by current model"}),
            501,
        )

    images = request.json.get("images")
    if not images:
        return jsonify({"error": "images array is required"}), 400

    if not isinstance(images, list):
        return jsonify({"error": "images must be an array"}), 400

    if len(images) == 0:
        return jsonify({"error": "images array cannot be empty"}), 400

    if len(images) > MAX_IMAGES_PER_BATCH:
        error_msg = (
            f"Batch size {len(images)} exceeds maximum of {MAX_IMAGES_PER_BATCH} images "
            "per request. Split into multiple requests."
        )
        return jsonify({"error": error_msg}), 400

    # Validate all images are non-empty strings
    valid_images = [img for img in images if img and isinstance(img, str)]
    if len(valid_images) != len(images):
        return jsonify({"error": "All images must be non-empty base64 strings"}), 400

    try:
        embeddings_list = embed_images_batch(valid_images)
        return jsonify({"embeddings": [emb.tolist() for emb in embeddings_list]}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to process images: {str(e)}"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
