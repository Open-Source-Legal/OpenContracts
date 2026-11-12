- Retry documents when a parsing or conversion service answers 408 or 429
  instead of failing them permanently. Services behind an autoscaler commonly
  answer 429 when they are at their instance limit, so a bulk upload could
  fail documents on the first attempt with no retry. The Docling, Docxodus,
  warp-ingest and Gotenberg clients now share
  `opencontractserver/pipeline/base/exceptions.py::is_transient_http_status`;
  the busy statuses live in `TRANSIENT_HTTP_CLIENT_ERROR_STATUSES`
  (`constants/document_processing.py`). Other 4xx stay permanent.
