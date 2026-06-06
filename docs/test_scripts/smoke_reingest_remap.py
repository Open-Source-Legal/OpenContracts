"""Smoke test: opt-in reingest & remap V2 import against the real local stack.

Run inside the django container with a live celeryworker:

    docker compose -f local.yml up -d celeryworker
    docker compose -f local.yml run --rm django python manage.py shell \
        < docs/test_scripts/smoke_reingest_remap.py

Builds a tiny text corpus (2 docs + 1 cross-doc relationship), exports it,
re-imports with ``reingest_and_remap=True`` via the real service (async ->
celeryworker -> real text parser -> remap -> relationship fan-in), and polls
for completion. Prints PASS/FAIL for each invariant.
"""

import time
import uuid

from django.contrib.auth import get_user_model

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.document_imports.services import (
    import_corpus_export_for_user,
)
from opencontractserver.documents.models import (
    Document,
    PendingCorpusImport,
    PendingDocumentAnnotations,
)
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import UserExport
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

tag = uuid.uuid4().hex[:8]
CONTENT = (
    "This Master Agreement covers indemnification obligations of the parties. "
    "Section 4 governs the limitation of liability between them."
)
RAW = "indemnification obligations"

print(f"\n=== reingest-remap smoke [{tag}] ===")

user = User.objects.create_user(username=f"smoke_{tag}", password="x")
# Not the feature under test; just clear the corpus-import usage gate.
user.is_usage_capped = False
user.save()
labelset = LabelSet.objects.create(title=f"LS {tag}", creator=user)
tok = AnnotationLabel.objects.create(
    text="OC_CLAUSE", label_type=TOKEN_LABEL, creator=user
)
rel_label = AnnotationLabel.objects.create(
    text="relates_to", label_type=RELATIONSHIP_LABEL, creator=user
)
labelset.annotation_labels.add(tok, rel_label)
src = Corpus.objects.create(
    title=f"Smoke Source {tag}", creator=user, label_set=labelset
)
set_permissions_for_obj_to_user(user, src, [PermissionTypes.ALL])

anns = []
for i in (1, 2):
    doc, _status, _path = src.import_content(
        content=CONTENT.encode("utf-8"),
        user=user,
        filename=f"doc{i}.txt",
        title=f"Smoke Doc {i}",
        file_type="text/plain",
    )
    # Wait for the source doc's own pipeline to finish so it has a text layer
    # to export.
    for _ in range(60):
        doc.refresh_from_db()
        if not doc.backend_lock:
            break
        time.sleep(1)
    start = CONTENT.find(RAW)
    ann = Annotation.objects.create(
        document=doc,
        corpus=src,
        annotation_label=tok,
        raw_text=RAW,
        annotation_type=TOKEN_LABEL,
        json={"start": start, "end": start + len(RAW), "text": RAW},
        creator=user,
    )
    set_permissions_for_obj_to_user(user, ann, [PermissionTypes.ALL])
    anns.append(ann)

rel = Relationship.objects.create(
    corpus=src,
    document=anns[0].document,
    relationship_label=rel_label,
    structural=False,
    creator=user,
)
rel.source_annotations.set([anns[0]])
rel.target_annotations.set([anns[1]])
set_permissions_for_obj_to_user(user, rel, [PermissionTypes.ALL])
print(f"source corpus {src.id}: 2 docs, 1 relationship")

# Export.
export = UserExport.objects.create(backend_lock=True, creator=user)
package_corpus_export_v2(
    export_id=export.id, corpus_pk=src.id, include_conversations=False
)
export.refresh_from_db()
with export.file.open("rb") as fh:
    zip_bytes = fh.read()
print(f"exported {len(zip_bytes)} bytes")

# Re-import with reingest & remap (async -> celeryworker).
result = import_corpus_export_for_user(
    user=user, zip_source=zip_bytes, reingest_and_remap=True
)
assert result.corpus is not None, f"import service failed: {result.error}"
imported = result.corpus
print(f"dispatched reingest import into corpus {imported.id}; polling...")

# Poll for the fan-in to complete.
coord = None
for _ in range(180):
    coord = PendingCorpusImport.objects.filter(corpus=imported).first()
    if coord and coord.status in (
        PendingCorpusImport.Status.DONE,
        PendingCorpusImport.Status.FAILED,
    ):
        break
    time.sleep(1)


def check(label, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return ok


imported.refresh_from_db()
# The docs the feature actually processed are exactly those carrying a
# PendingDocumentAnnotations row for this run (excludes the auto-generated
# Readme.CAML document the corpus import always synthesizes).
rows = list(PendingDocumentAnnotations.objects.filter(corpus=imported))
docs = list(Document.objects.filter(pk__in=[r.document_id for r in rows]))
imported_annots = Annotation.objects.filter(
    corpus=imported, annotation_label__text="OC_CLAUSE", structural=False
)
imported_rels = Relationship.objects.filter(corpus=imported, structural=False)

print("--- results ---")
ok = True
ok &= check("2 documents imported", len(docs) == 2)
ok &= check("all docs reingested (unlocked)", all(not d.backend_lock for d in docs))
ok &= check(
    "all docs have a parser text layer",
    all(d.txt_extract_file and d.txt_extract_file.read() for d in docs),
)
ok &= check("2 pending-annotation rows", len(rows) == 2)
ok &= check(
    "all pending rows DONE",
    all(r.status == PendingDocumentAnnotations.Status.DONE for r in rows),
)
ok &= check("2 annotations re-anchored", imported_annots.count() == 2)
ok &= check(
    "coordination row DONE",
    coord is not None and coord.status == PendingCorpusImport.Status.DONE,
)
ok &= check("1 relationship wired by fan-in", imported_rels.count() == 1)
if imported_rels.count() == 1:
    r = imported_rels.get()
    s = r.source_annotations.first()
    t = r.target_annotations.first()
    ok &= check(
        "relationship spans two distinct docs",
        s is not None and t is not None and s.document_id != t.document_id,
    )

print(f"\n=== SMOKE {'PASSED' if ok else 'FAILED'} [{tag}] ===")
if coord:
    print(f"coord report: {coord.report}")
for r in rows:
    print(f"row doc={r.document_id} status={r.status} report={r.report}")
