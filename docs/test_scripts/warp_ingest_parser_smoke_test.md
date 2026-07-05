# Test: Warp-Ingest PDF parser end-to-end smoke test

## Purpose

Verify that `WarpIngestParser` parses a real PDF end-to-end against the official
`ghcr.io/open-source-legal/warp-ingest` container and persists structural
annotations, relationships and PAWLS tokens via `process_document` — i.e. the
full ingestion path, not just a mocked HTTP call.

## Prerequisites

- The `warp-ingest` container running and reachable from the Django container.
  ```bash
  docker run -d --name warp-ingest -p 5001:5001 \
    -e WARP_API_KEY=smoke-test-key \
    ghcr.io/open-source-legal/warp-ingest:latest
  # health check
  curl -s http://localhost:5001/healthz
  # -> {"status":"ok","version":"...","ocr_available":true,...}
  ```
- A fixture PDF, e.g. `opencontractserver/tests/fixtures/files/doc_1_pdf_file.pdf`.
- Django test/local stack up (`docker compose -f test.yml ...` or `local.yml`).

## Steps

1. Confirm the service parses the fixture directly (sanity check of the
   `render_format=opencontracts` envelope):
   ```bash
   curl -s -H "X-API-Key: smoke-test-key" \
     -F "file=@opencontractserver/tests/fixtures/files/doc_1_pdf_file.pdf;type=application/pdf" \
     "http://localhost:5001/api/parse?render_format=opencontracts" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['result']; \
print('pages', r['page_count'], '| annotations', len(r['labelled_text']), \
'| relationships', len(r['relationships']))"
   # -> pages 9 | annotations 213 | relationships 64
   ```

2. Drive the parser through OpenContracts end-to-end. From the Django container
   (the running warp-ingest is reachable at `http://host.docker.internal:5001`
   or the compose hostname `http://warp-ingest:5001`):
   ```bash
   docker compose -f test.yml run --rm \
     -e WARP_INGEST_PARSER_SERVICE_URL=http://host.docker.internal:5001/api/parse \
     -e WARP_INGEST_API_KEY=smoke-test-key \
     django python manage.py shell -c "
   from django.contrib.auth import get_user_model
   from django.core.files.base import ContentFile
   from opencontractserver.documents.models import Document
   from opencontractserver.pipeline.parsers.warp_ingest_parser import WarpIngestParser
   from opencontractserver.annotations.models import Annotation

   User = get_user_model()
   user, _ = User.objects.get_or_create(username='warp_smoke')
   doc = Document.objects.create(title='Warp Smoke', file_type='pdf', creator=user)
   with open('opencontractserver/tests/fixtures/files/doc_1_pdf_file.pdf','rb') as fh:
       doc.pdf_file.save('smoke.pdf', ContentFile(fh.read()))

   parser = WarpIngestParser()
   parser.service_url = 'http://host.docker.internal:5001/api/parse'
   parser.api_key = 'smoke-test-key'
   result = parser.process_document(user.id, doc.id)

   doc.refresh_from_db()
   print('page_count', doc.page_count)
   print('export annotations', len(result['labelled_text']))
   print('persisted annotations', Annotation.objects.filter(document=doc).count())
   "
   ```

## Expected Results

- Step 1 prints non-zero page/annotation/relationship counts (9 / 213 / 64 for
  `doc_1_pdf_file.pdf`).
- Step 2 prints `page_count 9`, a matching export annotation count, and a
  **non-zero** persisted `Annotation` count — proving `save_parsed_data`
  imported the structural layer.

## Cleanup

```bash
docker rm -f warp-ingest
```
(The test `Document`/`Annotation` rows live only in the ephemeral test DB.)
