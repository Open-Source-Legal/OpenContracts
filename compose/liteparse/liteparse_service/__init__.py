"""HTTP wrapper around LiteParse with the OCRia-nano OCR backend.

See ``docs/pipelines/liteparse_parser.md``. ``projection`` and ``runtime`` are
pure Python (no ``liteparse`` / ``fastapi`` import) so their tests run in the
OpenContracts CI image; ``app`` wires them to the real library.
"""
