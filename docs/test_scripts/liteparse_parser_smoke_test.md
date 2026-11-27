# Test: LiteParse (OCRia-nano) parser end-to-end smoke test

## Purpose

Verify that the licence-gated `compose/liteparse` image builds, starts only with the model
present, and that `LiteParseParser` parses real PDFs through it and persists structural
annotations via the normal `ingest_doc` path. This checks the whole path, not a mocked HTTP
call.

## Prerequisites

- Docker. The test stack project used below is `ocredact`
  (`test.yml` + `~/.claude/oc-tools/oc-test-override.yml`); any stack works if you substitute
  its network and run command.
- Fixtures: `opencontractserver/tests/fixtures/needs_ocr.pdf` (scanned page) and
  `opencontractserver/tests/fixtures/sample.pdf` (text layer + tables).

## Steps

1. The licence gate refuses an unaccepted build:
   ```bash
   env -u OCRIA_NANO_ACCEPT_LICENSE docker compose -f local.yml --profile liteparse build liteparse
   ```
2. Build with the licence accepted:
   ```bash
   OCRIA_NANO_ACCEPT_LICENSE=yes docker compose -f local.yml --profile liteparse build liteparse
   ```
3. The service refuses to start without the model:
   ```bash
   docker run --rm -e LITEPARSE_API_KEY=abc123 -e LITEPARSE_MODEL_DIR=/nonexistent opencontractserver_local_liteparse
   ```
4. Start it on the test stack's network under the `liteparse` alias:
   ```bash
   docker run -d --rm --name ocreg-liteparse --network ocredact_default --network-alias liteparse \
     -e LITEPARSE_API_KEY=abc123 opencontractserver_local_liteparse
   docker inspect -f '{{.State.Health.Status}}' ocreg-liteparse
   ```
5. Seed the parser's settings from the environment, then parse both fixtures directly and
   ingest one as a `Document`. Celery is eager in test settings, so ingestion runs on save.
   ```bash
   docker compose -f test.yml -f ~/.claude/oc-tools/oc-test-override.yml -p ocredact run --rm -T \
     -e LITEPARSE_API_KEY=abc123 django sh -c \
     "python manage.py migrate --noinput -v0 && \
      python manage.py migrate_pipeline_settings --component opencontractserver.pipeline.parsers.liteparse_parser.LiteParseParser && \
      python manage.py shell" <<'PY'
   from collections import Counter
   from django.contrib.auth import get_user_model
   from django.core.files.base import ContentFile
   from opencontractserver.documents.models import Document, PipelineSettings
   from opencontractserver.pipeline.parsers.liteparse_parser import LiteParseParser

   FIX = "opencontractserver/tests/fixtures/"
   for name in ("needs_ocr", "sample"):
       e = LiteParseParser().parse_pdf_bytes(open(FIX + name + ".pdf", "rb").read(), title=name)
       print(name, e["page_count"], sum(len(p["tokens"]) for p in e["pawls_file_content"]),
             dict(Counter(a["annotationLabel"] for a in e["labelled_text"])))

   ps = PipelineSettings.get_instance()
   ps.preferred_parsers = {**(ps.preferred_parsers or {}),
       "application/pdf": "opencontractserver.pipeline.parsers.liteparse_parser.LiteParseParser"}
   ps.save()
   user, _ = get_user_model().objects.get_or_create(username="lp-smoke")
   doc = Document(title="LiteParse smoke", creator=user, file_type="application/pdf")
   doc.pdf_file.save("needs_ocr.pdf", ContentFile(open(FIX + "needs_ocr.pdf", "rb").read()), save=False)
   doc.save()
   doc.refresh_from_db()
   anns = doc.structural_annotation_set.structural_annotations.all()
   child = anns.get(raw_text="Ondernemings- en vestigingsgegevens")
   print(doc.processing_status, anns.count(), child.parent.raw_text)
   PY
   ```

## Expected Results

- Step 1 fails, printing the OCRia-nano licence notice and
  `Build refused: OCRIA_NANO_ACCEPT_LICENSE is not 'yes'.`
- Step 2 succeeds, and the build log shows `Installing ocria-nano@1.0.0`.
- Step 3 exits non-zero with
  `ocria-nano 1.0.0 is not installed (or is incomplete) in LITEPARSE_MODEL_DIR; rebuild the image`.
- Step 4 reports `healthy`.
- Step 5 (observed 2026-11-27, LiteParse 2.21.3, ocria-nano 1.0.0):
  - `needs_ocr`: 1 page, 409 tokens, `Section Header` ×4, `Paragraph` ×30, `Page Footer` ×2, ~1.5 s.
  - `sample`: 9 pages, 4883 tokens, 4 `Table` annotations with tokens, ~1.5 s.
  - The ingested document reaches `processing_status == "completed"`. Its
    `structural_annotation_set` holds 36 structural annotations, and the
    `"Ondernemings- en vestigingsgegevens"` annotation's parent is `"KVK 14 Wijziging"`.

## Cleanup

```bash
docker stop ocreg-liteparse
docker compose -f test.yml -f ~/.claude/oc-tools/oc-test-override.yml -p ocredact down
```
