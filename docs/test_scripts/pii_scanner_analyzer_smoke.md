# Test: PII Scanner Analyzer (`pii_scanner_privacy_filter`)

## Purpose

End-to-end smoke test that the new task-based analyzer:

1. Gets auto-registered as an `Analyzer` row by either the initial
   `migrate` (migration `0009_auto_load_doc_analyzers`) or the
   `sync_analyzers_on_startup` hook / `sync_doc_analyzers` management
   command on subsequent runs.
2. Produces correctly-typed annotations when invoked on a text document
   (SPAN_LABEL) and a PDF document (TOKEN_LABEL).
3. Uses the same label text + color + icon as the agent tool
   `scan_and_annotate_pii` (matching `ENTITY_GROUP_LABELS`).
4. Surfaces the `min_score` knob from the input schema.

## Prerequisites

- Local stack up: `docker compose -f local.yml up`.
- Migrations applied at least through `analyzer.0009_auto_load_doc_analyzers`.
- A superuser exists (default `admin`).
- For the live-service variant: a running `privacy-filter` service on
  `PRIVACY_FILTER_URL`. For the mocked variant (recommended in this
  script), `adetect_pii` is patched in the Django shell to avoid the
  network dependency.

## Steps

### 1. Confirm the analyzer is registered

```bash
docker compose -f local.yml run --rm django python manage.py sync_doc_analyzers
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.analyzer.models import Analyzer
qs = Analyzer.objects.filter(
    task_name='opencontractserver.tasks.doc_analysis_tasks.pii_scanner_privacy_filter'
)
print('count:', qs.count())
a = qs.first()
print('id:', a.id)
print('input_schema:', a.input_schema)
"
```

**Expected**: `count: 1`, `id` equal to the task path, `input_schema`
contains a `min_score` property.

### 2. Smoke a text document

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
import asyncio
from unittest.mock import patch, AsyncMock
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    SPAN_LABEL, Annotation, AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools._privacy_filter_client import Detection
from opencontractserver.tasks.doc_analysis_tasks import pii_scanner_privacy_filter

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()

corpus = Corpus.objects.create(title='PII Smoke', creator=user)
doc = Document.objects.create(
    title='Smoke TXT', creator=user, file_type='text/plain',
)
doc.txt_extract_file.save('s.txt', ContentFile(b'My email is alice@example.com.'))
doc, *_ = corpus.add_document(document=doc, user=user)

analyzer = Analyzer.objects.get(
    task_name='opencontractserver.tasks.doc_analysis_tasks.pii_scanner_privacy_filter'
)
analysis = Analysis.objects.create(
    analyzer=analyzer, analyzed_corpus=corpus, creator=user,
)

fake = [Detection(entity_group='private_email', score=0.99,
                  start=12, end=29, text='alice@example.com')]
with patch(
    'opencontractserver.tasks.doc_analysis_tasks.adetect_pii',
    new=AsyncMock(return_value=fake),
):
    result = pii_scanner_privacy_filter.si(
        doc_id=doc.id, analysis_id=analysis.id, corpus_id=corpus.id,
    ).apply().get()

print('result:', result)
print('annotation count:', Annotation.objects.filter(analysis=analysis).count())
ann = Annotation.objects.filter(analysis=analysis).first()
print('ann.json:', ann.json, 'raw_text:', ann.raw_text,
      'type:', ann.annotation_type)
label = ann.annotation_label
print('label:', label.text, label.color, label.icon)
assert label.text == 'PII: Email'
assert label.color == '#1f77b4'
assert label.icon == 'mail'
assert ann.annotation_type == SPAN_LABEL
assert ann.json == {'start': 12, 'end': 29}
print('TEXT SMOKE OK')
"
```

**Expected**: `TEXT SMOKE OK` printed, no assertions failed.

### 3. Smoke a PDF document

Repeat the above with a PDF document. Use any small PDF that already has
a PAWLS parse on disk (e.g. one created by uploading through the UI
once). Adjust the offsets in the `Detection` to fall inside the parsed
text:

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
import asyncio
from unittest.mock import patch, AsyncMock
from django.contrib.auth import get_user_model
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import TOKEN_LABEL, Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools._privacy_filter_client import Detection
from opencontractserver.tasks.doc_analysis_tasks import pii_scanner_privacy_filter

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
doc = Document.objects.filter(file_type='application/pdf').first()
assert doc and doc.pawls_parse_file, 'need a PDF doc with PAWLS'
corpus = Corpus.objects.create(title='PII Smoke PDF', creator=user)
doc, *_ = corpus.add_document(document=doc, user=user)
analyzer = Analyzer.objects.get(
    task_name='opencontractserver.tasks.doc_analysis_tasks.pii_scanner_privacy_filter'
)
analysis = Analysis.objects.create(
    analyzer=analyzer, analyzed_corpus=corpus, creator=user,
)
with doc.txt_extract_file.open('r') as f:
    txt = f.read()
# find a real character range to annotate
idx = txt.lower().find(' the ')
fake = [Detection(entity_group='private_email', score=0.99,
                  start=idx, end=idx + 4, text=txt[idx:idx+4])]
with patch(
    'opencontractserver.tasks.doc_analysis_tasks.adetect_pii',
    new=AsyncMock(return_value=fake),
):
    result = pii_scanner_privacy_filter.si(
        doc_id=doc.id, analysis_id=analysis.id, corpus_id=corpus.id,
    ).apply().get()
ann = Annotation.objects.filter(analysis=analysis).first()
print('PDF annotation_type:', ann.annotation_type)
assert ann.annotation_type == TOKEN_LABEL
print('PDF SMOKE OK')
"
```

**Expected**: `PDF SMOKE OK` printed, `annotation_type == TOKEN_LABEL`.

### 4. Confirm `min_score` filtering

Re-run step 2 with `analysis_input_data={'min_score': 0.999}` and a
detection of `score=0.5` — assert `Annotation.objects.count() == 0`.

## Expected Results

- Step 1: One Analyzer row, input_schema includes `min_score`.
- Step 2: One SPAN_LABEL annotation with PII label styling.
- Step 3: One TOKEN_LABEL annotation on the PDF.
- Step 4: No annotation when score < min_score.

## Cleanup

Delete the test Corpus + Analysis + Document objects via the admin or
shell, or drop the `test_db` if working in a throwaway database.
