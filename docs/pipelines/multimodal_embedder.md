# Multimodal Microservice Embedder

The Multimodal Microservice Embedder generates embeddings for both text and images via an external microservice. It works with any embedding service that implements the standard API, enabling cross-modal similarity search where text and image embeddings exist in the same vector space.

## Features

- **Cross-modal search**: Find images similar to text queries and vice versa
- **Model-agnostic**: Works with any embedding service implementing the standard API
- **Configurable dimensions**: Support for different embedding models and vector sizes
- **Batch processing**: Embed multiple texts (up to 100) or images (up to 20) in one request
- **Cloud Run IAM auth**: Optional Google Cloud Run authentication

## Configuration

Configure the embedder via environment variables:

### Service Connection

```bash
# Option 1: Set host and port separately (recommended)
MULTIMODAL_EMBEDDER_HOST=multimodal-embedder  # Service hostname (default)
MULTIMODAL_EMBEDDER_PORT=8000                  # Service port (default)

# Option 2: Set full URL directly (overrides host:port)
MULTIMODAL_EMBEDDER_URL=http://multimodal-embedder:8000
```

### Vector Dimensions

The vector size must match the embedding model used by your microservice:

```bash
# Default (768) - works with CLIP ViT-L-14, many transformer models
MULTIMODAL_EMBEDDER_VECTOR_SIZE=768

# Other common dimensions
MULTIMODAL_EMBEDDER_VECTOR_SIZE=512   # CLIP ViT-B-32, smaller models
MULTIMODAL_EMBEDDER_VECTOR_SIZE=1024  # Larger models
MULTIMODAL_EMBEDDER_VECTOR_SIZE=1536  # OpenAI-compatible models
```

### Authentication

```bash
# API key for the microservice (optional)
MULTIMODAL_EMBEDDER_API_KEY=your-api-key
```

With `local.yml`, set this as a host variable rather than in `.envs/.local/.django`: compose forwards it to `django`, `celeryworker` and the embedder, and overrides the env file. It only seeds `PipelineSettings` on first boot, so to change a stored key use System Settings in the admin UI or `migrate_pipeline_settings --force --component <class>`. Without `--component`, `--force` overwrites every stored setting.

### Embedding Weights

When combining text and image embeddings for multimodal annotations:

```bash
# Weight for text component (default: 0.3)
MULTIMODAL_TEXT_WEIGHT=0.3

# Weight for image component (default: 0.7)
MULTIMODAL_IMAGE_WEIGHT=0.7
```

## Example Configurations

### Local Docker Compose (Default)

No configuration needed - uses defaults:
- Host: `multimodal-embedder`
- Port: `8000`
- Vector size: `768`

### External Cloud Service

```bash
MULTIMODAL_EMBEDDER_HOST=embeddings.example.com
MULTIMODAL_EMBEDDER_PORT=443
MULTIMODAL_EMBEDDER_URL=https://embeddings.example.com
MULTIMODAL_EMBEDDER_VECTOR_SIZE=768
MULTIMODAL_EMBEDDER_API_KEY=sk-your-api-key
```

### Google Cloud Run

```bash
MULTIMODAL_EMBEDDER_URL=https://embedder-abc123-uc.a.run.app
MULTIMODAL_EMBEDDER_VECTOR_SIZE=768
# IAM auth is auto-detected for Cloud Run URLs
```

### Custom Model with Different Dimensions

```bash
# Using a model with 512-dimensional embeddings
MULTIMODAL_EMBEDDER_VECTOR_SIZE=512
```

## API Specification

Any microservice implementing these endpoints will work with the embedder:

| Endpoint | Method | Description | Request | Response |
|----------|--------|-------------|---------|----------|
| `/embeddings` | POST | Single text | `{"text": "..."}` | `{"embeddings": [[...]]}` |
| `/embeddings/image` | POST | Single image | `{"image": "<base64>"}` | `{"embeddings": [[...]]}` |
| `/embeddings/batch` | POST | Batch text (max 100) | `{"texts": [...]}` | `{"embeddings": [[...], ...]}` |
| `/embeddings/image/batch` | POST | Batch images (max 20) | `{"images": [...]}` | `{"embeddings": [[...], ...]}` |

### Response Format

All endpoints return embeddings in the same format:

```json
{
  "embeddings": [
    [0.123, -0.456, 0.789, ...]  // Vector of configured dimension
  ]
}
```

For batch endpoints, the array contains one vector per input item.

## Usage in Code

```python
from opencontractserver.pipeline.embedders.multimodal_microservice import (
    CLIPMicroserviceEmbedder
)

embedder = CLIPMicroserviceEmbedder()

# Check configured vector size
print(f"Vector size: {embedder.vector_size}")

# Text embedding
text_vector = embedder.embed_text("contract clause about payment terms")

# Image embedding (base64-encoded)
image_vector = embedder.embed_image(base64_image_data)

# Batch operations
text_vectors = embedder.embed_texts_batch(["text1", "text2", "text3"])
image_vectors = embedder.embed_images_batch([base64_img1, base64_img2])
```

## Error Handling

The embedder distinguishes between retriable and non-retriable errors:

| Error Type | HTTP Status | Behavior |
|------------|-------------|----------|
| Client error | 4xx | Not retried (invalid input) |
| Server error | 5xx | Retried with backoff |
| Timeout | - | Not retried |
| Connection error | - | Not retried |

### Timeouts

- Single text/image: 30 seconds
- Batch text: 60 seconds
- Batch images: 120 seconds

## Supported File Types

- PDF
- TXT
- DOCX

## Building a Compatible Microservice

To build your own embedding microservice, implement the four endpoints above. Example using FastAPI:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class TextRequest(BaseModel):
    text: str

class ImageRequest(BaseModel):
    image: str  # base64

@app.post("/embeddings")
def embed_text(req: TextRequest):
    vector = your_model.encode_text(req.text)
    return {"embeddings": [vector.tolist()]}

@app.post("/embeddings/image")
def embed_image(req: ImageRequest):
    vector = your_model.encode_image(req.image)
    return {"embeddings": [vector.tolist()]}

# ... batch endpoints similarly
```

## See Also

- [Pipeline Overview](pipeline_overview.md)
- [Docling Parser](docling_parser.md) - Extracts images from PDFs
