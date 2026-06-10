"""Import EDGARx2 corpus-export zips INLINE and enrich each one.

Run inside the Django container:

    docker compose -f local.yml run --rm django python manage.py shell -c \
        "exec(open('/app/demo/import_edgar_corpora.py').read())"

Zips are read from /app/demo/import_zips/ (copy them into ./demo/import_zips
on the host first).

The import task runs synchronously in this process (calling the celery task
function directly) rather than via the worker: the local celeryworker
auto-restarts on file changes, which kills in-flight imports and strands them
in redis' unacked set for the visibility timeout. Inline = deterministic.
Enrichment (annotations + document-graph edges + cross-corpus law links) runs
right after each import.
"""

import pathlib

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.enrichment.service import EnrichmentService
from opencontractserver.tasks.import_tasks import import_corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
USER = User.objects.get(pk=1)
ZIP_DIR = pathlib.Path("/app/demo/import_zips")
ZIP_NAMES: list[str] = sorted(p.name for p in ZIP_DIR.glob("*.zip"))

for zip_name in ZIP_NAMES:
    print(f"\n=== {zip_name} ===", flush=True)
    zip_bytes = (ZIP_DIR / zip_name).read_bytes()

    corpus = Corpus.objects.create(title=f"Importing {zip_name}", creator=USER)
    set_permissions_for_obj_to_user(USER, corpus, [PermissionTypes.CRUD])
    handle = TemporaryFileHandle.objects.create()
    handle.file = ContentFile(zip_bytes, name=f"import_{zip_name}")
    handle.save()

    # Call the task function directly — synchronous, in-process.
    import_corpus(handle.id, USER.id, corpus.id, reingest_and_remap=False)

    corpus.refresh_from_db()
    n_docs = corpus._get_active_documents().count()
    print(
        f"  imported: corpus {corpus.id} | {corpus.title!r} | {n_docs} docs", flush=True
    )
    if n_docs == 0:
        print("  WARNING: no documents imported — skipping enrichment")
        continue

    out = EnrichmentService().apply(corpus_id=corpus.id, creator_id=USER.id)
    print(
        f"  enriched: {out['references_created']} refs "
        f"(+{out['document_relationships_created']} doc edges, "
        f"{out['law_references_linked']} law links) "
        f"from {out['total_candidates']} candidates",
        flush=True,
    )

print("\nAll done.", flush=True)
