"""
Rebuild the object-storage vector index from the ``Embedding`` table.

Postgres is the source of truth for vectors; this command replays every
stored vector into its object-storage namespace (WAL batches) and compacts
each touched namespace into a fresh indexed generation. It is safe to run
while ``VECTOR_SEARCH_BACKEND`` is still ``pgvector`` — build the index
first, then flip the flag.
"""

from django.core.management.base import BaseCommand

from opencontractserver.annotations.models import Embedding
from opencontractserver.constants.search import (
    DIM_TO_FIELD_MAP,
    OBJECT_INDEX_REBUILD_BATCH_SIZE,
)
from opencontractserver.tasks.vector_index_tasks import PARENT_FK_TO_KIND
from opencontractserver.vector_search.router import (
    build_namespace,
    get_default_engine,
)


class Command(BaseCommand):
    help = (
        "Replay all Embedding vectors into the object-storage vector index "
        "and compact each namespace. Idempotent; run before enabling "
        "VECTOR_SEARCH_BACKEND=object_storage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--embedder-path",
            default=None,
            help="Only rebuild namespaces for this embedder_path.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=OBJECT_INDEX_REBUILD_BATCH_SIZE,
            help="Vectors per WAL file written during the replay.",
        )

    def handle(self, *args, **options):
        engine = get_default_engine()
        batch_size = options["batch_size"]
        queryset = Embedding.objects.all()
        if options["embedder_path"]:
            queryset = queryset.filter(embedder_path=options["embedder_path"])

        buffers: dict[str, list[tuple[int, list[float]]]] = {}
        totals: dict[str, int] = {}

        def flush(namespace: str) -> None:
            batch = buffers.pop(namespace, [])
            if batch:
                engine.upsert(namespace, batch)

        for embedding in queryset.iterator(chunk_size=batch_size):
            parent = next(
                (
                    (kind, getattr(embedding, fk_attr))
                    for fk_attr, kind in PARENT_FK_TO_KIND.items()
                    if getattr(embedding, fk_attr)
                ),
                None,
            )
            if parent is None:
                continue
            parent_kind, parent_pk = parent
            for dimension, field_name in DIM_TO_FIELD_MAP.items():
                vector = getattr(embedding, field_name, None)
                if vector is None:
                    continue
                namespace = build_namespace(
                    parent_kind, embedding.embedder_path, dimension
                )
                buffers.setdefault(namespace, []).append((parent_pk, list(vector)))
                totals[namespace] = totals.get(namespace, 0) + 1
                if len(buffers[namespace]) >= batch_size:
                    flush(namespace)

        for namespace in list(buffers):
            flush(namespace)

        for namespace in sorted(totals):
            stats = engine.compact(namespace)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{namespace}: replayed {totals[namespace]} vectors, "
                    f"compacted to generation {stats.get('generation')} "
                    f"({stats.get('cluster_count')} clusters)"
                )
            )
        if not totals:
            self.stdout.write("No embeddings matched; nothing rebuilt.")
