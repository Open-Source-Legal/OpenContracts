"""
Import tasks for corpus import with V2 format support.

Handles backward compatibility with V1 format while supporting all V2 features.
Uses shared helpers from utils/importing.py for DRY document/label/annotation
creation, and corpus.add_document() for proper corpus isolation.
"""

from __future__ import annotations

import json
import logging
import uuid
import zipfile
from typing import IO, TYPE_CHECKING, Any, cast

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from config import celery_app
from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus, TemporaryFileHandle
from opencontractserver.documents.models import (
    Document,
    IngestionSource,
    IngestionSourceCategory,
    PendingCorpusImport,
    PendingDocumentAnnotations,
)
from opencontractserver.types.dicts import (
    CorpusFolderExport,
    DocumentPathExport,
    IngestionSourceExport,
    OpenContractsExportDataJsonPythonType,
    OpenContractsExportDataJsonV2Type,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.import_v2 import (
    import_agent_config,
    import_conversations,
    import_corpus_folders,
    import_md_description_revisions,
    import_metadata_schema,
    import_structural_annotation_set,
)
from opencontractserver.utils.importing import (
    create_document_from_export_data,
    import_doc_annotations,
    prepare_import_labels,
)
from opencontractserver.utils.packaging import (
    unpack_corpus_from_export,
    unpack_label_set_from_export,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import CorpusFolder
    from opencontractserver.users.models import User as UserModel

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()

# Cap on how many known folder-path keys we dump into the "unresolved
# folder_path" warning. Log aggregators (Datadog, CloudWatch) truncate long
# lines, which could hide the very keys we want a human to compare against.
_UNRESOLVED_FOLDER_KEY_SAMPLE_SIZE = 20

# Sentinel the V2 exporter (``etl.py``) writes as the "file" for any document
# without a real ``pdf_file`` (text/markdown/source-less docs): a single NUL
# byte. Reingest cannot re-parse it, so such docs fall back to the baked import.
# Kept as a named constant so it cross-references the exporter side.
_NUL_SOURCE_PLACEHOLDER = b"\x00"


def import_corpus_v2_from_bytes(
    zip_source: IO[bytes],
    user_id: int,
    seed_corpus_id: int | None,
    reingest_and_remap: bool = False,
) -> int | None:
    """
    Run the V2 corpus import against an in-memory or file-like ZIP source.

    This is the in-process entry point — it does not depend on
    ``TemporaryFileHandle``.  Both ``import_corpus_v2`` (the Celery task
    backing the upload mutation) and the fork pipeline call this directly
    so they share one code path for "given a ZIP, materialize a corpus".

    Args:
        zip_source: A readable, seekable binary stream (e.g. ``io.BytesIO``
            from :func:`build_corpus_v2_zip`, or an open ``File`` handle).
            Anything ``zipfile.ZipFile`` accepts as a binary stream is
            valid; caller owns the lifetime.
        user_id: User performing the import.
        seed_corpus_id: Optional corpus ID to merge into instead of
            creating a new one (used by fork to import into a shell).

    Returns:
        Corpus ID on success, ``None`` on failure.
    """
    try:
        user_obj = User.objects.get(id=user_id)

        with zipfile.ZipFile(zip_source, mode="r") as import_zip:
            files = import_zip.namelist()
            logger.info("import_corpus_v2_from_bytes() - Files in ZIP: %s", len(files))

            if "data.json" not in files:
                logger.error(
                    "import_corpus_v2_from_bytes() - data.json not found in ZIP"
                )
                return None

            with import_zip.open("data.json") as corpus_data:
                data_json = json.loads(corpus_data.read().decode("UTF-8"))

            version = data_json.get("version", "1.0")
            logger.info("Detected export format version: %s", version)

            return _import_corpus(
                data_json,
                import_zip,
                user_obj,
                seed_corpus_id,
                version,
                reingest_and_remap=reingest_and_remap,
            )

    except Exception:
        # Log full traceback for Sentry / structured logs.  Callers (e.g.
        # ``fork_corpus``) may also need contextual error detail — they
        # can wrap the ``None`` return into a ``RuntimeError`` themselves
        # if they want to escalate, since this in-process entry point is
        # also called from a Celery task that prefers ``None`` returns.
        #
        # ``exc_info=True`` already attaches the formatted traceback to the
        # log record; passing ``%s`` / ``e`` alongside would duplicate the
        # exception summary into the message body (visible twice in
        # structured-log aggregators).
        logger.error("import_corpus_v2_from_bytes() failed", exc_info=True)
        return None


@celery_app.task()
def import_corpus_v2(
    temporary_file_handle_id: str | int,
    user_id: int,
    seed_corpus_id: int | None,
    reingest_and_remap: bool = False,
) -> int | None:
    """
    Import corpus with support for both V1 and V2 export formats.

    Detects format version from data.json and routes to appropriate handler.
    Both formats share the same core logic via _import_corpus(); V2 adds
    structural sets, folders, relationships, agent config, etc.

    Thin orchestration wrapper around :func:`import_corpus_v2_from_bytes`
    — it loads the ZIP from a ``TemporaryFileHandle`` (the GraphQL upload
    flow) and delegates everything else.

    Args:
        temporary_file_handle_id: ID of TemporaryFileHandle with ZIP
        user_id: User performing import
        seed_corpus_id: Optional corpus ID to merge into

    Returns:
        Corpus ID on success, None on failure
    """
    try:
        logger.info("import_corpus_v2() - for user_id: %s", user_id)

        temporary_file_handle = TemporaryFileHandle.objects.get(
            id=temporary_file_handle_id
        )

        with temporary_file_handle.file.open("rb") as import_file:
            return import_corpus_v2_from_bytes(
                import_file,
                user_id,
                seed_corpus_id,
                reingest_and_remap=reingest_and_remap,
            )

    except Exception as e:
        logger.error("import_corpus_v2() - Exception: %s", e, exc_info=True)
        return None


def _setup_corpus_and_labels(
    data_json: (
        OpenContractsExportDataJsonPythonType | OpenContractsExportDataJsonV2Type
    ),
    user_obj: UserModel,
    seed_corpus_id: int | None,
) -> tuple[
    Corpus,
    LabelSet,
    dict[str, AnnotationLabel],
    dict[str, AnnotationLabel],
]:
    """
    Shared setup for both V1 and V2 imports: create labelset, corpus, and labels.

    Returns:
        Tuple of (corpus_obj, labelset_obj, label_lookup, doc_label_lookup)
    """
    label_set_data = {**data_json["label_set"]}
    label_set_data.pop("id", None)

    # The {**data_json["label_set"]} spread widens to dict[str, Any], which
    # is structurally compatible with the OpenContractsLabelSetType TypedDict
    # the unpacker declares but mypy can't bridge dict <-> TypedDict at the
    # callsite. Tracked under the broader typing-graduation umbrella (#1447)
    # — fix is to widen the unpacker signature to Mapping[str, Any] when
    # ``utils.importing`` graduates from the baseline.
    labelset_obj = unpack_label_set_from_export(label_set_data, user_obj)  # type: ignore[arg-type]  # TODO(#1447)
    if labelset_obj is None:
        raise RuntimeError("Failed to unpack label set from export")
    logger.info("LabelSet created: %s", labelset_obj)

    corpus_data = {**data_json["corpus"]}
    corpus_data.pop("id", None)

    corpus_obj = unpack_corpus_from_export(
        data=corpus_data,  # type: ignore[arg-type]  # TODO(#1447) — see label_set_data note above
        user=user_obj,
        label_set_id=labelset_obj.id,
        corpus_id=seed_corpus_id if seed_corpus_id else None,
    )
    if corpus_obj is None:
        raise RuntimeError("Failed to unpack corpus from export")
    logger.info("Created corpus: %s", corpus_obj)

    # ``data_json`` is dict[str, Any] from json.loads, but
    # ``prepare_import_labels`` expects ``OpenContractsExportDataJsonPythonType``.
    # See the label_set_data note above and TODO(#1447).
    label_lookup, doc_label_lookup = prepare_import_labels(
        data_json,  # type: ignore[arg-type]  # TODO(#1447)
        user_obj.id,
        labelset_obj,
    )

    return corpus_obj, labelset_obj, label_lookup, doc_label_lookup


def _import_document_with_annotations(
    doc_filename: str,
    doc_data: dict[str, Any],
    import_zip: zipfile.ZipFile,
    user_obj: UserModel,
    corpus_obj: Corpus,
    label_lookup: dict[str, AnnotationLabel],
    doc_label_lookup: dict[str, AnnotationLabel],
    structural_sets: dict[str, StructuralAnnotationSet] | None = None,
    reingest_and_remap: bool = False,
    import_run_id: uuid.UUID | None = None,
) -> tuple[Document | None, dict[str | int, int]]:
    """
    Import a single document into a corpus, handling:
    - Document creation (standalone) via shared create_document_from_export_data
    - Adding to corpus via corpus.add_document() (creates corpus-isolated copy)
    - Importing all annotations onto the corpus copy via shared import_doc_annotations

    Args:
        doc_filename: The filename of the document in the ZIP.
        doc_data: The document data dict from the export.
        import_zip: The open ZIP file.
        user_obj: The importing user.
        corpus_obj: The target corpus.
        label_lookup: Combined label lookup.
        doc_label_lookup: Doc-type label lookup.
        structural_sets: Optional mapping of content_hash -> StructuralAnnotationSet
            (V2 only).
        reingest_and_remap: When True, take the reingest path: create the
            document from the raw source bytes (NOT the baked PAWLs), let the
            standard pipeline regenerate PAWLs + structural annotations, and
            defer the surviving non-structural annotations into a
            ``PendingDocumentAnnotations`` row for ``remap_pending_annotations``
            to re-anchor. The export's structural layer is dropped.
        import_run_id: Run id stamped on the deferred row (reingest mode), used
            by the relationship fan-in to group the run's deferred work.

    Returns:
        Tuple of (corpus_doc, annot_id_map) where corpus_doc is the
        corpus-isolated document copy and annot_id_map maps old annotation IDs
        to new PKs. In reingest mode annotations are created asynchronously, so
        the returned map is always empty. Returns (None, {}) on failure.
    """
    # Reingest mode is only meaningful for documents whose *original source
    # file* the export preserved — i.e. PDFs (and other binaries with a real
    # ``pdf_file``). For text/markdown/source-less documents the V2 exporter
    # writes a single-NUL placeholder in place of the file (``etl.py`` —
    # ``b64encode(b"\\x00")``), because the document's content lives only in the
    # baked ``content`` / ``pawls_file_content``. Re-parsing that placeholder
    # would feed ``\\x00`` to the parser. So in reingest mode we peek the source
    # bytes and fall back to the standard baked import for placeholder docs,
    # still recording a DONE ``PendingDocumentAnnotations`` row so the
    # relationship fan-in can resolve this doc's annotation ids.
    reingest_fallback = False
    if reingest_and_remap:
        with import_zip.open(doc_filename) as fh:
            source_bytes = fh.read()
        if _source_is_reingestable(source_bytes):
            return _reingest_document_with_deferred_remap(
                doc_filename,
                doc_data,
                source_bytes,
                user_obj,
                corpus_obj,
                import_run_id,
                label_lookup,
            )
        reingest_fallback = True
        logger.info(
            "Reingest: document %s has no preserved source file (placeholder); "
            "importing its baked layer instead and recording its id_map for "
            "the relationship fan-in.",
            doc_filename,
        )

    try:
        with import_zip.open(doc_filename) as pdf_file_handle:
            # Check for structural annotation set (V2 feature)
            structural_set = None
            struct_hash = doc_data.get("structural_set_hash")
            if structural_sets and struct_hash and struct_hash in structural_sets:
                structural_set = structural_sets[struct_hash]

            # Create standalone document using shared helper
            doc_obj = create_document_from_export_data(
                doc_data=doc_data,
                pdf_file_handle=pdf_file_handle,
                doc_filename=doc_filename,
                user_obj=user_obj,
            )

            # Attach structural annotation set if present
            if structural_set:
                doc_obj.structural_annotation_set = structural_set
                doc_obj.save(update_fields=["structural_annotation_set"])

            # Add to corpus - creates corpus-isolated copy with DocumentPath
            corpus_doc, _status, _doc_path = corpus_obj.add_document(
                document=doc_obj, user=user_obj
            )

            # Import annotations onto the corpus copy using shared helper
            annot_id_map, _doc_labels_count = import_doc_annotations(
                doc_data=doc_data,
                corpus_doc=corpus_doc,
                corpus_obj=corpus_obj,
                user_id=user_obj.id,
                label_lookup=label_lookup,
                doc_label_lookup=doc_label_lookup,
            )

            # Unlock original document
            doc_obj.backend_lock = False
            doc_obj.save(update_fields=["backend_lock"])

            # Reingest fallback: this source-less doc was imported baked rather
            # than reingested. Record a DONE pending row carrying its id_map so
            # the relationship fan-in aggregates its annotation ids alongside the
            # genuinely-reingested docs' maps (otherwise cross-doc relationships
            # touching this doc would be silently dropped at finalize).
            if reingest_fallback and import_run_id is not None:
                PendingDocumentAnnotations.objects.create(
                    document=corpus_doc,
                    corpus=corpus_obj,
                    creator=user_obj,
                    ingestion_run_id=import_run_id,
                    payload={},
                    id_map={str(k): v for k, v in annot_id_map.items()},
                    status=PendingDocumentAnnotations.Status.DONE,
                )

            return corpus_doc, annot_id_map

    except Exception as e:
        logger.error("Error importing document %s: %s", doc_filename, e)
        return None, {}


def _source_is_reingestable(source_bytes: bytes) -> bool:
    """True when the export preserved a real source file for reingest.

    The V2 exporter writes a single NUL byte (``_NUL_SOURCE_PLACEHOLDER``) as the
    file for any document without a real ``pdf_file`` (text/markdown/source-less
    docs); their content survives only as baked ``content`` /
    ``pawls_file_content``. Such a placeholder cannot be re-parsed, so those docs
    fall back to the baked import.
    """
    return source_bytes not in (b"", _NUL_SOURCE_PLACEHOLDER)


def _reingest_document_with_deferred_remap(
    doc_filename: str,
    doc_data: dict[str, Any],
    source_bytes: bytes,
    user_obj: UserModel,
    corpus_obj: Corpus,
    import_run_id: uuid.UUID | None,
    label_lookup: dict[str, AnnotationLabel],
) -> tuple[Document | None, dict[str | int, int]]:
    """Reingest one document and defer its annotations for post-ingest remap.

    Creates the document from the raw source bytes via
    ``corpus.import_content(..., backend_lock=True)`` (no ``processing_started``
    suppression), so the standard post_save chain (``extract_thumbnail ->
    ingest_doc -> remap_pending_annotations -> set_doc_lock_state``) regenerates
    PAWLs + structural annotations from the *current* parser and then re-anchors
    the surviving non-structural annotations.

    The exported ``StructuralAnnotationSet`` is intentionally NOT attached
    (structural annotations are regenerated by the parser). The document and its
    ``PendingDocumentAnnotations`` row share one ``transaction.atomic()`` so the
    on_commit ingest chain (dispatched at the outermost commit) sees the
    committed pending row — the same invariant the bulk-ZIP importer relies on.

    ``pdf_file_hash`` is recomputed from the bytes by ``import_content`` (same
    bytes as the export → same SHA-256), so DocumentPath reconstruction keyed on
    the hash still resolves.

    The export writes each ``labelled_text`` entry's ``annotationLabel`` as the
    label *id* (``etl.py``), but ``remap_pending_annotations`` resolves labels by
    *text* against the corpus labelset (the dumb-anchor contract). So each
    deferred annotation's ``annotationLabel`` is rewritten id -> text here before
    it is persisted, using the import's ``label_lookup`` (keyed by export label
    id). ``doc_labels`` already ship as label text and need no rewrite.
    """
    label_id_to_text = {
        str(label_id): lbl.text for label_id, lbl in label_lookup.items()
    }
    try:
        with transaction.atomic():
            corpus_doc, _status, _path = corpus_obj.import_content(
                content=source_bytes,
                user=user_obj,
                filename=doc_filename,
                title=doc_data["title"],
                description=doc_data.get("description", ""),
                file_type=doc_data.get("file_type"),
                backend_lock=True,
            )
            set_permissions_for_obj_to_user(
                user_obj, corpus_doc, [PermissionTypes.ALL], is_new=True
            )

            # Defer surviving non-structural annotations for remap. Filtering
            # structural entries out here keeps the payload lean and the remap
            # report clean — ``anchor_annotations`` would drop+report them anyway.
            # Rewrite annotationLabel id -> text so the text-keyed remap lookup
            # resolves it.
            non_structural = [
                {
                    **a,
                    "annotationLabel": label_id_to_text.get(
                        str(a.get("annotationLabel")), a.get("annotationLabel")
                    ),
                }
                for a in doc_data.get("labelled_text", [])
                if not a.get("structural")
            ]
            doc_labels = doc_data.get("doc_labels", [])
            if non_structural or doc_labels:
                PendingDocumentAnnotations.objects.create(
                    document=corpus_doc,
                    corpus=corpus_obj,
                    creator=user_obj,
                    ingestion_run_id=import_run_id,
                    payload={
                        "annotations": non_structural,
                        "doc_labels": doc_labels,
                    },
                    status=PendingDocumentAnnotations.Status.PENDING,
                )

        # Synchronous id_map is empty in this mode — annotations land async.
        return corpus_doc, {}

    except Exception as e:
        logger.error("Error reingesting document %s: %s", doc_filename, e)
        return None, {}


def _import_corpus(
    data_json: (
        OpenContractsExportDataJsonPythonType | OpenContractsExportDataJsonV2Type
    ),
    import_zip: zipfile.ZipFile,
    user_obj: UserModel,
    seed_corpus_id: int | None,
    version: str = "1.0",
    reingest_and_remap: bool = False,
) -> int | None:
    """
    Unified import handler for both V1 and V2 formats.

    V1 imports: labels, corpus, documents with annotations.
    V2 imports: all of V1 plus structural sets, folders, relationships,
    agent config, markdown descriptions, and conversations.

    Transaction / rollback contract:
        This function performs many writes and uses nested
        ``transaction.atomic()`` blocks internally (e.g.
        :func:`_import_ingestion_sources`, :func:`import_metadata_schema`).
        Django promotes those nested blocks to **savepoints**, not
        autonomous transactions — so when an inner ``atomic`` raises and is
        caught by this function's broad ``except`` clause (returning
        ``None``), the savepoint is rolled back but any writes already
        flushed to the outer connection's transaction remain pending until
        the caller commits or rolls back.

        Callers that want "all or nothing" import semantics (e.g.
        :func:`fork_corpus`) must therefore wrap this call in their own
        outer ``transaction.atomic()`` and react to a ``None`` return by
        raising — the outer block then rolls back the entire savepoint
        chain.  Callers that don't (the standalone Celery import task)
        accept partial state on failure.
    """
    # V3 archives share the V2 import shape minus the legacy top-level
    # ``md_description`` / ``md_description_revisions`` keys; the
    # corresponding V2 back-compat shim that synthesises a Readme.CAML
    # Document from those keys is a no-op on V3 archives.
    is_v2 = version in {"2.0", "3.0"}
    logger.info(
        "Using %s import format",
        "V3" if version == "3.0" else "V2" if version == "2.0" else "V1",
    )

    try:
        # ===== Shared: Setup corpus, labelset, and labels =====
        corpus_obj, labelset_obj, label_lookup, doc_label_lookup = (
            _setup_corpus_and_labels(data_json, user_obj, seed_corpus_id)
        )

        # Build a (text, label_type)-keyed label lookup for structural
        # annotations and relationships, which reference labels by text
        # rather than PK.  The compound key prevents collisions when
        # different label types share the same text.
        label_lookup_by_text = {
            (label.text, label.label_type): label for label in label_lookup.values()
        }

        # ===== Reingest mode: mint the run id + set up the relationship fan-in.
        # Read corpus-level relationships up front so the coordination row can be
        # created *before* the doc loop dispatches async remaps (the last remap
        # may finalize before the post-loop READY flip — the exactly-once claim
        # in ``_maybe_finalize_corpus_import`` handles either ordering).
        import_run_id: uuid.UUID | None = None
        reingest_relationships: list = []
        if reingest_and_remap:
            import_run_id = uuid.uuid4()
            # The relationship fan-in is async and the orphaned-row sweeper is
            # still deferred (see the design doc §9). Until it lands, a worker
            # crash mid-import leaves PendingCorpusImport / PendingDocumentAnnotations
            # rows stranded with relationships never wired — log the run id so an
            # operator can find and clean up stuck rows by hand.
            logger.warning(
                "[ImportV2] reingest_and_remap enabled for corpus %s "
                "(import_run_id=%s); coordination rows are swept manually until "
                "the orphaned-row sweeper lands.",
                corpus_obj.id,
                import_run_id,
            )
            if is_v2:
                reingest_relationships = (
                    cast(OpenContractsExportDataJsonV2Type, data_json).get(
                        "relationships", []
                    )
                    or []
                )
            if reingest_relationships:
                PendingCorpusImport.objects.create(
                    import_run_id=import_run_id,
                    corpus=corpus_obj,
                    creator=user_obj,
                    relationships_payload=reingest_relationships,
                    expected_doc_count=None,
                    status=PendingCorpusImport.Status.ENUMERATING,
                )

        # ===== V2 only: Import structural annotation sets =====
        # Skipped entirely in reingest mode — the parser regenerates structural
        # annotations from the freshly-produced PAWLs layer.
        structural_sets: dict[str, StructuralAnnotationSet] = {}
        if is_v2 and not reingest_and_remap:
            v2_struct_data = cast(OpenContractsExportDataJsonV2Type, data_json)
            struct_sets_data = v2_struct_data.get("structural_annotation_sets", {})
            for content_hash, struct_data in struct_sets_data.items():
                struct_set = import_structural_annotation_set(
                    struct_data, label_lookup_by_text, user_obj
                )
                if struct_set:
                    structural_sets[content_hash] = struct_set
            logger.info("Imported %s structural annotation sets", len(structural_sets))

        # ===== Shared: Import documents =====
        # Aggregated old_id -> new_id; ``import_doc_annotations`` returns
        # ``dict[str | int, int]`` so the aggregator widens to match.
        all_annot_id_maps: dict[str | int, int] = {}
        # Track doc_ref -> corpus_doc for DocumentPath reconstruction.
        # Despite the legacy name, this map is keyed by every form
        # ``package_*_for_export`` uses for ``document_ref``: pdf_file_hash
        # *and* basename(pdf_file.name) *and* the synthesized
        # ``document_{id}.placeholder`` fallback.  Lookups against any of
        # those forms resolve to the freshly-created Document on the
        # import side, so callers (DocumentPath reconstruction, metadata
        # schema, conversations) only need this one map.
        doc_hash_to_corpus_doc: dict[str, Document] = {}
        # Strict filename -> corpus_doc map (no hash keys mixed in).  Used
        # by CAML README rewriting where mixing in hash keys would risk a
        # filename / hash string collision silently mapping to the wrong doc.
        doc_filename_to_corpus_doc: dict[str, Document] = {}

        for doc_filename, doc_data in data_json["annotated_docs"].items():
            logger.info("Importing document: %s", doc_filename)
            corpus_doc, annot_id_map = _import_document_with_annotations(
                doc_filename=doc_filename,
                doc_data=cast("dict[str, Any]", doc_data),
                import_zip=import_zip,
                user_obj=user_obj,
                corpus_obj=corpus_obj,
                label_lookup=label_lookup,
                doc_label_lookup=doc_label_lookup,
                structural_sets=structural_sets if is_v2 else None,
                reingest_and_remap=reingest_and_remap,
                import_run_id=import_run_id,
            )

            if corpus_doc:
                all_annot_id_maps.update(annot_id_map)
                # Build hash mapping for DocumentPath reconstruction
                if corpus_doc.pdf_file_hash:
                    doc_hash_to_corpus_doc[corpus_doc.pdf_file_hash] = corpus_doc
                # Also map by filename (fallback when hash is unavailable).
                # The export side uses the same filename as its fallback
                # document_ref in package_document_paths().
                doc_hash_to_corpus_doc[doc_filename] = corpus_doc
                doc_filename_to_corpus_doc[doc_filename] = corpus_doc

        # ===== Reingest mode: arm the relationship fan-in =====
        # All docs are enumerated; flip the coordination row to READY (recording
        # the run's actual pending-row count for observability) and attempt
        # finalization. This covers the case where every doc's async remap
        # already completed before READY was set (including a relationship-free
        # run, which has no coordination row — ``_maybe_finalize_corpus_import``
        # is then a clean no-op). The last remap to finish wins the race
        # otherwise; the exactly-once claim guarantees a single finalize.
        if reingest_and_remap and reingest_relationships:
            # Deferred import: ``doc_tasks`` imports from this module, so a
            # top-level import here would form a circular import at module load.
            from opencontractserver.tasks.doc_tasks import (
                _maybe_finalize_corpus_import,
            )

            # ``import_run_id`` is always set when reingest mode created a
            # coordination row (which only happens when relationships exist).
            # Use an explicit guard, not ``assert``: assertions are stripped
            # under ``python -O`` / a ``-O`` Celery worker, which would let a
            # ``filter(import_run_id=None)`` silently mis-target rows.
            if import_run_id is None:
                raise RuntimeError(
                    "_import_corpus: import_run_id must be set in reingest mode "
                    "when relationships exist — this is a bug."
                )
            expected = PendingDocumentAnnotations.objects.filter(
                ingestion_run_id=import_run_id
            ).count()
            # ``updated_at`` is ``auto_now`` but bulk ``.update()`` bypasses it,
            # so stamp it explicitly — the admin panel is the primary surface for
            # spotting stuck/recently-armed runs until the sweeper (§9) lands.
            PendingCorpusImport.objects.filter(import_run_id=import_run_id).update(
                expected_doc_count=expected,
                status=PendingCorpusImport.Status.READY,
                updated_at=timezone.now(),
            )
            _maybe_finalize_corpus_import(import_run_id)

        # ===== V2 only: Import additional features =====
        if is_v2:
            # ``is_v2`` guarantees the V2 export schema; narrow for mypy so
            # ``.get()`` returns the correctly typed lists/dicts instead of
            # the V1∩V2 ``object`` lower-bound.
            v2_data = cast(OpenContractsExportDataJsonV2Type, data_json)

            # Import folders
            folders_data = v2_data.get("folders", [])
            folder_export_id_to_obj = import_corpus_folders(
                folders_data, corpus_obj, user_obj
            )

            # Import ingestion sources and reconstruct DocumentPaths
            ingestion_sources_data = v2_data.get("ingestion_sources", [])
            source_name_map = _import_ingestion_sources(
                ingestion_sources_data, user_obj
            )

            document_paths_data = v2_data.get("document_paths", [])
            if document_paths_data:
                _reconstruct_document_paths(
                    document_paths_data,
                    corpus_obj,
                    doc_hash_to_corpus_doc,
                    folders_data,
                    folder_export_id_to_obj,
                    source_name_map,
                )

            # Import relationships (corpus-level, non-structural).
            # In reingest mode these are wired asynchronously by the fan-in
            # (``finalize_corpus_import_relationships``) once every doc's remap
            # has recorded its id_map — they CANNOT be wired here because
            # ``all_annot_id_maps`` is empty (annotations land async).
            relationships_data = v2_data.get("relationships", [])
            if relationships_data and not reingest_and_remap:
                _import_v2_relationships(
                    relationships_data,
                    corpus_obj,
                    all_annot_id_maps,
                    label_lookup_by_text,
                    user_obj,
                )

            # Import agent config
            agent_config = v2_data.get("agent_config")
            if agent_config:
                import_agent_config(agent_config, corpus_obj)

            # V2 back-compat: synthesize a Readme.CAML Document from the
            # legacy ``md_description`` + ``md_description_revisions`` top-level
            # keys.  V3 archives don't carry those keys (the CAML doc rides
            # in ``annotated_docs`` like any other Document), so the call is
            # a clean no-op on V3 — the shim early-returns on empty input.
            # Pass the doc-filename and annotation id maps so any
            # ``oc-import://`` placeholder links written in the README by
            # the zip author are rewritten to live URLs after all referenced
            # objects have been created.  See utils/caml_rewrite.py and
            # spec §4.8 of the Canonical-CAML refactor.
            md_description = v2_data.get("md_description")
            md_revisions = v2_data.get("md_description_revisions", [])
            if md_description or md_revisions:
                import_md_description_revisions(
                    md_description,
                    md_revisions,
                    corpus_obj,
                    user_obj,
                    doc_filename_to_doc=doc_filename_to_corpus_doc,
                    annot_old_id_to_new_pk=cast(
                        "dict[str | int, int] | None", all_annot_id_maps
                    ),
                )

            # Import manual metadata schema (if present)
            metadata_schema = v2_data.get("metadata_schema")
            if metadata_schema:
                import_metadata_schema(
                    cast("dict[str, Any]", metadata_schema),
                    corpus_obj,
                    user_obj,
                    doc_ref_to_doc=doc_hash_to_corpus_doc,
                )

            # Import conversations (if present)
            if "conversations" in v2_data:
                conversations = v2_data.get("conversations", [])
                messages = v2_data.get("messages", [])
                votes = v2_data.get("message_votes", [])
                import_conversations(
                    conversations,
                    messages,
                    votes,
                    corpus_obj,
                    user_obj,
                    doc_hash_to_doc=doc_hash_to_corpus_doc,
                )

            # Refresh description cache deterministically.
            #
            # V3 archives carry the Readme.CAML Document inside
            # ``annotated_docs``, so it lands via the normal
            # ``_import_document_with_annotations`` path. The Document
            # ``post_save`` signal schedules a cache refresh via
            # ``transaction.on_commit``, but the import runs inside a
            # long outer transaction (and under TestCase test
            # transactions on_commit may not fire), so on_commit can be
            # delayed past the point where callers read back the corpus
            # row. Calling the helper directly here pins
            # ``corpus.description`` / ``.description_preview`` /
            # ``.readme_caml_document_id`` to the imported CAML head the
            # moment the import returns — duplicate work with the signal
            # is harmless (idempotent update).
            from opencontractserver.corpuses.services.description_cache import (
                refresh_description_cache_for_corpus,
            )

            refresh_description_cache_for_corpus(corpus_obj.id)

        logger.info("Import completed successfully for corpus %s", corpus_obj.id)
        return corpus_obj.id

    except Exception as e:
        logger.error("Import failed: %s", e, exc_info=True)
        return None


def _import_v2_relationships(
    relationships_data: list[OpenContractsRelationshipPythonType],
    corpus_obj: Corpus,
    annot_id_map: dict[str | int, int],
    label_lookup: dict[
        tuple[str, str], AnnotationLabel
    ],  # key: (label_text, label_type)
    user_obj: UserModel,
) -> None:
    """
    Import V2 corpus-level relationships, skipping structural ones (handled
    by structural annotation sets).

    Infers the document from the first source annotation for each relationship.
    """
    for rel_data in relationships_data:
        # Skip structural relationships (handled by structural sets)
        if rel_data.get("structural"):
            continue

        label_text = rel_data.get("relationshipLabel", "")
        label_obj = label_lookup.get((label_text, RELATIONSHIP_LABEL))
        if not label_obj:
            logger.warning("Relationship label '%s' not found", label_text)
            continue

        # Map annotation IDs (drop any missing entries before persisting).
        # ``dict.get`` returns ``None`` for unknown keys, so the ``is not None``
        # check on the walrus result is sufficient — no separate membership
        # test required.
        source_ids: list[int] = [
            new_id
            for old_id in rel_data.get("source_annotation_ids", [])
            if (new_id := annot_id_map.get(str(old_id))) is not None
        ]
        target_ids: list[int] = [
            new_id
            for old_id in rel_data.get("target_annotation_ids", [])
            if (new_id := annot_id_map.get(str(old_id))) is not None
        ]

        if source_ids and target_ids:
            # Get document from first source annotation
            first_source_annot = Annotation.objects.get(id=source_ids[0])
            document = first_source_annot.document

            rel = Relationship.objects.create(
                corpus=corpus_obj,
                document=document,
                relationship_label=label_obj,
                structural=False,
                creator=user_obj,
            )
            rel.source_annotations.set(source_ids)
            rel.target_annotations.set(target_ids)
            set_permissions_for_obj_to_user(user_obj, rel, [PermissionTypes.ALL])


def _import_ingestion_sources(
    sources_data: list[IngestionSourceExport],
    user_obj: UserModel,
) -> dict[str, IngestionSource]:
    """
    Import or get-or-create IngestionSource records from exported data.

    Uses get_or_create keyed on (creator, name) so re-importing the same
    corpus doesn't duplicate sources.

    Note: ``get_or_create`` only applies ``source_type``, ``config``, and
    ``active`` on *creation*.  If a source with the same (creator, name)
    already exists locally, its current field values are preserved — the
    export's values are intentionally not applied ("don't clobber local
    changes").  This avoids surprises when a re-import would silently
    reactivate a source the user deactivated, or overwrite a config they
    customised after the initial import.

    Args:
        sources_data: List of IngestionSourceExport dicts from data.json.
        user_obj: The importing user (becomes creator of new sources).

    Returns:
        Mapping of source name -> IngestionSource instance.
    """
    source_map: dict[str, IngestionSource] = {}

    for src in sources_data:
        name = src.get("name")
        if not name:
            continue

        try:
            with transaction.atomic():
                source, created = IngestionSource.objects.get_or_create(
                    creator=user_obj,
                    name=name,
                    defaults={
                        "source_type": src.get(
                            "source_type", IngestionSourceCategory.MANUAL
                        ),
                        "config": src.get("config") or {},
                        "active": src.get("active", True),
                    },
                )
        except IntegrityError as exc:
            logger.debug("IntegrityError on create, falling back to get: %s", exc)
            # Guard the fallback: in the rare case where a concurrent request
            # created-then-deleted the row between the IntegrityError and this
            # .get(), skip the source rather than aborting the entire corpus
            # import with an unhandled DoesNotExist.
            try:
                source = IngestionSource.objects.get(creator=user_obj, name=name)
            except IngestionSource.DoesNotExist:
                logger.warning(
                    "IngestionSource '%s' for user %s vanished between "
                    "IntegrityError and fallback get; skipping.",
                    name,
                    user_obj.id,
                )
                continue
            created = False
        source_map[name] = source

        if created:
            set_permissions_for_obj_to_user(user_obj, source, [PermissionTypes.CRUD])
            logger.debug("Created IngestionSource '%s' for user %s", name, user_obj.id)
        else:
            logger.debug("Reusing existing IngestionSource '%s'", name)

    return source_map


def _build_folder_path_lookup(
    folders_data: list[CorpusFolderExport],
    folder_export_id_to_obj: dict[str, CorpusFolder],
) -> dict[str, CorpusFolder]:
    """
    Build a folder-path -> CorpusFolder lookup that tolerates differing path
    conventions between the exporter and importer.

    The canonical OpenContracts exporter (``utils/export_v2.py``) writes the
    folder's ``get_path()`` (name-joined, e.g. ``"Filings/10-K"``) into both
    ``folder.path`` and ``document_paths.folder_path``.  Third-party exporters
    (e.g. EDGAR scrapers that build the export ZIP themselves) may emit
    slug-joined or otherwise transformed paths.  Either is acceptable as
    long as the convention is consistent **within a single export**, because
    the lookup keys here use the export's own ``folder.path`` field as the
    source of truth — whatever string the exporter chose will match the
    string written into ``document_paths.folder_path`` in the same zip.

    Both the export-provided ``path`` and the freshly-imported folder's
    ``get_path()`` are inserted in case either field is absent, empty, or
    differs from the other under the exporter's chosen convention.

    Collisions between two distinct folders sharing the same lookup key
    (e.g. one folder's ``exported_path`` equals a sibling's ``get_path()``)
    are logged at WARNING and the last writer wins — same loud-failure
    posture as an unresolved ``folder_path``.

    Args:
        folders_data: Folder dicts as written by the exporter.
        folder_export_id_to_obj: Map from each folder dict's ``id`` to the
            ``CorpusFolder`` row created during import (from
            :func:`import_corpus_folders`).

    Returns:
        Mapping of every known path representation to its ``CorpusFolder``.
    """
    folder_path_to_folder: dict[str, CorpusFolder] = {}

    def _register(key: str | None, folder_obj: CorpusFolder) -> None:
        if not key:
            return
        existing = folder_path_to_folder.get(key)
        if existing is not None and existing is not folder_obj:
            logger.warning(
                "Folder path key collision: %r maps to both folder %s and "
                "folder %s; last writer wins.",
                key,
                existing.id,
                folder_obj.id,
            )
        folder_path_to_folder[key] = folder_obj

    for folder_data in folders_data:
        folder_obj = folder_export_id_to_obj.get(folder_data["id"])
        if folder_obj is None:
            # Folder creation failed earlier (already logged by
            # import_corpus_folders).
            continue
        _register(folder_obj.get_path(), folder_obj)
        _register(folder_data.get("path"), folder_obj)
    return folder_path_to_folder


def _reconstruct_document_paths(
    document_paths_data: list[DocumentPathExport],
    corpus_obj: Corpus,
    doc_hash_to_corpus_doc: dict[str, Document],
    folders_data: list[CorpusFolderExport],
    folder_export_id_to_obj: dict[str, CorpusFolder],
    source_name_map: dict[str, IngestionSource] | None = None,
) -> None:
    """
    Update DocumentPaths created by corpus.add_document() to match the exported
    path, version_number, folder assignments, and ingestion lineage.

    Only current, non-deleted paths from the export are applied since historical
    versions don't have file content in the export. This ensures the document
    tree structure matches the original corpus.

    Args:
        document_paths_data: List of exported DocumentPath dicts.
        corpus_obj: The target corpus.
        doc_hash_to_corpus_doc: Mapping of document_ref (hash or old ID) to
            the imported corpus-isolated Document.
        folders_data: Folder dicts from the export — used to learn whichever
            path convention the exporter used so ``document_paths.folder_path``
            resolves regardless of canonical vs. third-party formatting.
        folder_export_id_to_obj: Map from export folder id to the imported
            ``CorpusFolder`` (the return value of ``import_corpus_folders``).
        source_name_map: Mapping of source name -> IngestionSource instance
            (from _import_ingestion_sources).
    """
    from opencontractserver.documents.models import DocumentPath

    if source_name_map is None:
        source_name_map = {}

    folder_path_map = _build_folder_path_lookup(folders_data, folder_export_id_to_obj)

    # Pre-build a document -> DocumentPath lookup to avoid N queries in the loop
    path_by_doc_id = {
        p.document_id: p
        for p in DocumentPath.objects.filter(
            corpus=corpus_obj, document__in=doc_hash_to_corpus_doc.values()
        )
    }

    for path_data in document_paths_data:
        # Only reconstruct current, non-deleted paths
        if not path_data.get("is_current", True) or path_data.get("is_deleted", False):
            continue

        doc_ref = path_data.get("document_ref")
        corpus_doc = doc_hash_to_corpus_doc.get(doc_ref)
        if not corpus_doc:
            logger.debug(
                "DocumentPath reconstruction: no matching doc for ref %s", doc_ref
            )
            continue

        # Find the DocumentPath created by add_document() for this corpus_doc
        existing_path = path_by_doc_id.get(corpus_doc.pk)
        if not existing_path:
            continue

        # Update path and version_number to match export
        updates: dict[str, Any] = {}
        exported_path = path_data.get("path")
        if exported_path and exported_path != existing_path.path:
            updates["path"] = exported_path

        exported_version = path_data.get("version_number")
        if exported_version and exported_version != existing_path.version_number:
            updates["version_number"] = exported_version

        # Update folder assignment if folder_path is specified
        folder_path = path_data.get("folder_path")
        if folder_path:
            folder = folder_path_map.get(folder_path)
            if folder:
                updates["folder"] = folder
            else:
                # Loud failure mode: the exporter pointed this document at a
                # folder we couldn't resolve, so it would silently land at the
                # corpus root.  This typically means folder.path and
                # document_paths.folder_path were written with different
                # conventions, or the referenced folder failed to import.
                # Cap the displayed key list — log aggregators truncate long
                # lines, which would hide the very keys we want to compare
                # against.
                known_keys = sorted(folder_path_map.keys())
                key_sample = known_keys[:_UNRESOLVED_FOLDER_KEY_SAMPLE_SIZE]
                logger.warning(
                    "DocumentPath reconstruction: folder_path %r did not "
                    "resolve to any imported folder in corpus %s (doc %s). "
                    "Document will remain at corpus root. Known folder paths "
                    "(%d total, showing first %d): %s",
                    folder_path,
                    corpus_obj.id,
                    corpus_doc.id,
                    len(known_keys),
                    len(key_sample),
                    key_sample,
                )

        # Restore ingestion lineage fields
        source_name = path_data.get("ingestion_source_name")
        if source_name and source_name in source_name_map:
            updates["ingestion_source"] = source_name_map[source_name]
        elif source_name:
            logger.warning(
                "DocumentPath references unknown ingestion source '%s' "
                "— lineage not restored",
                source_name,
            )

        external_id = path_data.get("external_id")
        if external_id is not None:
            updates["external_id"] = external_id

        # Asymmetry note: export omits ``ingestion_metadata`` entirely when
        # the value is falsy (see ``package_document_paths``), so a missing
        # key here is the expected "empty" signal.  An explicit ``None`` is
        # treated the same as absent — we only restore a dict payload when
        # the exporter actually wrote one.
        ingestion_metadata = path_data.get("ingestion_metadata")
        if ingestion_metadata is not None:
            updates["ingestion_metadata"] = ingestion_metadata

        if updates:
            for key, value in updates.items():
                setattr(existing_path, key, value)
            existing_path.save(update_fields=list(updates.keys()))
            logger.debug("Updated DocumentPath for doc %s: %s", corpus_doc.id, updates)
