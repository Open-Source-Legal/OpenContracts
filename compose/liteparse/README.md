# LiteParse service (optional)

HTTP wrapper around [LiteParse](https://github.com/run-llama/liteparse) using
LlamaIndex's OCRia-nano OCR models, consumed by
`opencontractserver/pipeline/parsers/liteparse_parser.py::LiteParseParser`.

The image is built locally behind the `liteparse` compose profile and refuses to
build unless `OCRIA_NANO_ACCEPT_LICENSE=yes` (the model weights have their own
licence: `OCRIA_NANO_LICENSE_NOTICE.txt`). Setup, settings and limits:
`docs/pipelines/liteparse_parser.md`.
