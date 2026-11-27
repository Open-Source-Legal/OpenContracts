# LiteParse Parser (OCRia-nano)

`LiteParseParser` is an optional PDF parser backed by an in-repo microservice that runs
LlamaIndex's [LiteParse](https://github.com/run-llama/liteparse) (Apache-2.0) with the
[OCRia-nano-1](https://huggingface.co/llamaindex/OCRia-nano-1) OCR and layout models.

- **Text-layer pages** use the PDF's own text (PDFium); nothing is OCR'd and a page parses in
  roughly 0.1 s.
- **Scanned pages** are OCR'd with OCRia-nano (CPU only, ONNX Runtime). Each word comes back
  with its own box and an OCR confidence.
- LiteParse's layout blocks become structural annotations: `Section Header` (heading levels
  build the parent hierarchy, across pages), `Paragraph`, `List Item`, `Table`, `Figure`,
  `Code Block`, `Page Header`, `Page Footer`. Unknown future block kinds become `Text Block`.

## Licence — read this first

The OCRia-nano weights are **not** covered by OpenContracts' MIT licence. They ship under
the "OCRia-nano-1 Model License" (Open RAIL-M based). The weights are free for research,
personal use, and organisations under $2M annual revenue **and** $2M total funding. You need a
commercial licence above those thresholds, and at any size for a document
parsing/OCR/extraction product that competes with LlamaParse or LlamaCloud. Read the full
licence on the model card.

Because of this, the service is **opt-in** and **built locally**:

- It is not in the default stack, not in `compose/compose.images.yml`, and no image is
  published.
- The image build fails (printing `compose/liteparse/OCRIA_NANO_LICENSE_NOTICE.txt`) unless
  you set `OCRIA_NANO_ACCEPT_LICENSE=yes`. Whoever builds it downloads the weights and accepts
  the licence.
- Pushing your own build to a *private* registry for your own deployment (e.g. Cloud Run) is
  fine. Publishing it is not. Licence compliance is the deployer's responsibility.

## Enable it

```bash
# 1. Build and start the service (accepting the model licence)
OCRIA_NANO_ACCEPT_LICENSE=yes docker compose -f local.yml --profile liteparse up -d --build liteparse

# 2. Point PDFs at it: System Settings → parser for application/pdf →
#    "LiteParse Parser (OCRia-nano, REST)", or set PDF_PARSER=liteparse in the django env.
```

Use `production.yml` the same way. Django and Celery reach the service at
`http://liteparse:8000/parse` over the docker bridge (it has no host port).

## Settings

- **Parser** (`opencontractserver/pipeline/parsers/liteparse_parser.py::LiteParseParser.Settings`):
  `LITEPARSE_PARSER_SERVICE_URL`, `LITEPARSE_API_KEY`, `LITEPARSE_PARSER_TIMEOUT`,
  `LITEPARSE_USE_CLOUD_RUN_IAM_AUTH`, `LITEPARSE_MAX_FILE_SIZE_MB`. These are seeded into
  PipelineSettings by `migrate_pipeline_settings`.
- **Service** (`compose/liteparse/liteparse_service/runtime.py::load_config`):
  `LITEPARSE_API_KEY` (required; compose feeds both sides from the same host variable, default
  `abc123` for local use), `LITEPARSE_POOL_SIZE`, `LITEPARSE_OCR_WORKERS`,
  `LITEPARSE_PARSE_TIMEOUT_SECONDS`, `LITEPARSE_MAX_PAGES`, `LITEPARSE_MAX_UPLOAD_MB`.

The service refuses to start if the pinned model isn't installed. Without this check,
text-layer PDFs would keep parsing and scanned ones would fail later. Versions are pinned in
`compose/liteparse/requirements.txt` (LiteParse) and the Dockerfile's
`OCRIA_NANO_MODEL_VERSION`. If you bump either, re-record
`opencontractserver/tests/fixtures/liteparse/*.json`, and bump
`LITEPARSE_RESPONSE_SCHEMA_VERSION` if the response shape changed.

## How it works

The service (`compose/liteparse/liteparse_service/`) returns a fixed JSON projection of
LiteParse's result: page sizes in PDF points, text items with word boxes, and layout blocks
(`projection.py`). `liteparse_conversion.py::liteparse_response_to_export` turns that into
PAWLs tokens and annotations on the Django side, so Django never imports `liteparse`. The whole
document goes in one request, with no page-range chunking, so heading hierarchies that span
pages stay intact.

## Limits

- PDF only. Office files are converted to PDF upstream by Gotenberg when it's configured.
- Documents over `LITEPARSE_MAX_PAGES` (default 2000) are rejected with a 413. LiteParse would
  otherwise silently truncate them.
- No image tokens or multimodal image extraction yet.
- The remote-ingest worker (`scripts/remote_ingest/`) doesn't offer this parser yet.
  `LiteParseParser.parse_pdf_bytes` is the database-free entry point it would use.

End-to-end check: `docs/test_scripts/liteparse_parser_smoke_test.md`.
