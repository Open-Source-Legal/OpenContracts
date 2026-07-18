"""Import-contract tests ported from the PR 2153 branch.

Covers the durable-identity and idempotency contracts that survive the
grammar-architecture rework (the standalone customs service's DB tests were
deleted with it — see ``test_customs_trade_grammars.py`` for the grammar-side
port):

* meta.csv ``external_id`` -> ``DocumentPath.external_id`` stamping, and its
  survival across content re-imports (versioning lineage inheritance);
* ``relationships.csv`` import idempotency (get_or_create on edge identity);
* ``ensure_labels_and_labelset`` label-type coercion;
* the official-CROSS-export-shaped ZIP -> ``zip-to-corpus`` -> enrichment
  contract test, now running through ``EnrichmentService.apply`` (the same
  path every enrichment trigger uses).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import EnrichmentService

User = get_user_model()


class _ImportContractTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="contract", password="p")
        self.corpus = Corpus.objects.create(title="Contract Corpus", creator=self.user)


class ExternalIdLifecycleTests(_ImportContractTestBase):
    """A stamped ``DocumentPath.external_id`` must survive the versioning
    lifecycle: move/delete/restore always copied it, and the update
    (re-import at the same path) branch inherits it too unless the caller
    supplies a fresh value."""

    def _import(self, body: bytes, **doc_kwargs):
        _doc, _status, path_row = self.corpus.import_content(
            content=body,
            path="/HQ/opaque-name.txt",
            user=self.user,
            filename="opaque-name.txt",
            file_type="text/plain",
            title="Some subject",
            **doc_kwargs,
        )
        return path_row

    def test_upversion_inherits_external_id(self):
        first = self._import(b"v1 body", external_id="cross:H850001")
        assert first.external_id == "cross:H850001"

        second = self._import(b"v2 body")  # same path, no external_id

        assert second.id != first.id
        assert second.is_current
        assert second.external_id == "cross:H850001"

    def test_upversion_caller_override_wins(self):
        self._import(b"v1 body", external_id="cross:H850001")

        second = self._import(b"v2 body", external_id="cross:H850099")

        assert second.external_id == "cross:H850099"


class RelationshipImportDedupeTests(_ImportContractTestBase):
    """create_relationships_from_parsed is idempotent (get_or_create)."""

    def _make_doc(self, path):
        doc = Document.objects.create(
            title=path, creator=self.user, file_type="text/plain"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path=path,
            version_number=1,
            creator=self.user,
        )
        return doc

    def test_reimport_skips_existing_edges(self):
        from opencontractserver.tasks.import_tasks import (
            create_relationships_from_parsed,
        )
        from opencontractserver.utils.relationship_file_parser import (
            ParsedRelationship,
        )

        doc1 = self._make_doc("/HQ/H950001.txt")
        doc2 = self._make_doc("/HQ/H950002.txt")
        path_map = {"/HQ/H950001.txt": doc1, "/HQ/H950002.txt": doc2}
        rels = [
            ParsedRelationship(
                source_path="/HQ/H950001.txt",
                target_path="/HQ/H950002.txt",
                label="CITES",
            )
        ]
        logger = logging.getLogger(__name__)

        first = create_relationships_from_parsed(
            self.corpus, self.user, path_map, rels, logger
        )
        second = create_relationships_from_parsed(
            self.corpus, self.user, path_map, rels, logger
        )

        assert first["relationships_created"] == 1
        assert second["relationships_created"] == 0
        assert second["relationships_skipped"] == 1
        assert DocumentRelationship.objects.filter(corpus=self.corpus).count() == 1


class LabelTypeCoercionTests(_ImportContractTestBase):
    """ensure_labels_and_labelset stringifies non-str, non-enum label types."""

    def test_non_string_label_type_is_coerced(self):
        label = self.corpus.ensure_labels_and_labelset(
            label_data={"X": {"text": "X", "label_type": 123}},
            creator_id=self.user.id,
        )["X"]
        assert label.label_type == "123"


# --- Official bulk-export contract test -------------------------------------

# Two rulings shaped like the official CROSS bulk exporter's output
# (CROSS-Corpus crossfeed.export.oc_bulk): `{COLLECTION}/{ruling_number}.txt`
# documents, dumb-anchor sidecars whose producer labels are TOKEN_LABEL (the
# import contract's requirement), and meta.csv titles carrying the
# human-readable SUBJECT — never the ruling number.
CROSS_DOC1_BODY = (
    "HQ H830001\n\n"
    "The applicable subheading for the serving trays will be 3924.90.5650, "
    "HTSUS. The reasoning of NY H830002, which classified comparable goods "
    "under subheading 6307.90.9889, HTSUS, controls. We also considered "
    "NY N999999, which is not before us.\n"
)
CROSS_DOC2_BODY = (
    "NY H830002\n\n"
    "The applicable subheading for the textile bags will be 6307.90.9889, "
    "HTSUS.\n"
)


def _exporter_label(label_id, text, label_type, color="#F59E0B", icon="hash"):
    # Same key set the official exporter writes (oc_bulk._label).
    return {
        "id": label_id,
        "text": text,
        "label_type": label_type,
        "description": f"{text} produced by the CROSS exporter.",
        "color": color,
        "icon": icon,
    }


@pytest.mark.usefixtures("enable_doc_processing_signals")
class CrossOfficialExportIntegrationTests(TransactionTestCase):
    """End-to-end contract test: official-export-shaped ZIP -> zip-to-corpus
    import -> standard enrichment.

    The integration boundary the PR 2153 release blocker slipped through:
    regex unit tests could not see format gates or title-identity mismatches.
    ``TransactionTestCase`` + eager Celery lets the real import chain (parse
    -> text layer -> sidecar anchoring) run to completion before enrichment
    executes — completion is asserted from document state, never assumed from
    the import call returning.
    """

    def setUp(self):
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        with transaction.atomic():
            self.user = User.objects.create_user(username="cross-io", password="p")
        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="CROSS Official Export", creator=self.user
            )
            set_permissions_for_obj_to_user(
                self.user, self.corpus, [PermissionTypes.ALL]
            )

    def _set_text_parser(self):
        """Use the real TxtParser (deterministic, no external service)."""
        from opencontractserver.documents.models import PipelineSettings

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.preferred_parsers = {
            **(pipeline_settings.preferred_parsers or {}),
            "text/plain": "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser",
        }
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

    def _build_official_zip(self) -> io.BytesIO:
        meta = io.StringIO()
        writer = csv.writer(meta)
        writer.writerow(["source_path", "title", "description", "external_id"])
        writer.writerow(
            [
                "HQ/H830001.txt",
                "Plastic serving trays; classification",
                "CROSS HQ ruling H830001",
                "cross:H830001",
            ]
        )
        writer.writerow(
            [
                "HQ/H830002.txt",
                "Textile bags of man-made fibers",
                "CROSS NY ruling H830002",
                "cross:H830002",
            ]
        )

        labels = {
            "text_labels": {
                "HTS_CODE": _exporter_label("label-hts", "HTS_CODE", "TOKEN_LABEL"),
                "CITED_RULING": _exporter_label(
                    "label-cited-ruling", "CITED_RULING", "TOKEN_LABEL", icon="link"
                ),
            },
            "doc_labels": {},
        }

        hts1_start = CROSS_DOC1_BODY.find("3924.90.5650")
        cite_start = CROSS_DOC1_BODY.find("H830002")
        sidecar1 = {
            "annotations": [
                {
                    "id": 1,
                    "label": "HTS_CODE",
                    "rawText": "3924.90.5650",
                    "start": hts1_start,
                    "end": hts1_start + len("3924.90.5650"),
                    "parent_id": None,
                },
                {
                    "id": 2,
                    "label": "CITED_RULING",
                    "rawText": "H830002",
                    "start": cite_start,
                    "end": cite_start + len("H830002"),
                    "parent_id": None,
                },
            ],
            "doc_labels": [],
        }
        hts2_start = CROSS_DOC2_BODY.find("6307.90.9889")
        sidecar2 = {
            "annotations": [
                {
                    "id": 1,
                    "label": "HTS_CODE",
                    "rawText": "6307.90.9889",
                    "start": hts2_start,
                    "end": hts2_start + len("6307.90.9889"),
                    "parent_id": None,
                }
            ],
            "doc_labels": [],
        }

        files = {
            "meta.csv": meta.getvalue().encode("utf-8"),
            "labels.json": json.dumps(labels).encode("utf-8"),
            "HQ/H830001.txt": CROSS_DOC1_BODY.encode("utf-8"),
            "HQ/H830001.json": json.dumps(sidecar1).encode("utf-8"),
            "HQ/H830002.txt": CROSS_DOC2_BODY.encode("utf-8"),
            "HQ/H830002.json": json.dumps(sidecar2).encode("utf-8"),
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        buffer.seek(0)
        return buffer

    def _import_official_zip(self) -> dict[str, Document]:
        from opencontractserver.corpuses.models import TemporaryFileHandle
        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        self._set_text_parser()
        handle = TemporaryFileHandle.objects.create(
            file=ContentFile(self._build_official_zip().read(), name="cross.zip")
        )
        result = import_zip_with_folder_structure.apply(
            kwargs={
                "temporary_file_handle_id": handle.id,
                "user_id": self.user.id,
                "job_id": "cross-official-export",
                "corpus_id": self.corpus.id,
            }
        ).get()
        assert result["success"], result
        assert result["external_ids_applied"] == 2

        docs: dict[str, Document] = {}
        for number in ("H830001", "H830002"):
            path_row = DocumentPath.objects.get(
                corpus=self.corpus,
                path__endswith=f"{number}.txt",
                is_current=True,
                is_deleted=False,
            )
            assert path_row.external_id == f"cross:{number}"
            doc = Document.objects.get(pk=path_row.document_id)
            assert not doc.backend_lock, f"{number} still locked"
            assert doc.txt_extract_file, f"{number} has no text layer"
            docs[number] = doc
        return docs

    def test_official_export_import_then_enrich(self):
        docs = self._import_official_zip()
        doc1, doc2 = docs["H830001"], docs["H830002"]

        res = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert res is not None

        # HTS codes -> htsus: REF_LAW references (both codes in doc1, one in
        # doc2 — the writer dedupes repeat offsets per document).
        hts_refs = CorpusReference.objects.filter(
            corpus=self.corpus,
            reference_type=C.REF_LAW,
            canonical_key__startswith=f"{C.HTSUS_PREFIX}:",
        )
        assert set(hts_refs.values_list("canonical_key", flat=True).distinct()) == {
            "htsus:3924.90.56.50",
            "htsus:6307.90.98.89",
        }

        # Ruling citations: H830002 resolves (external_id/path identity —
        # titles are subjects), N999999 persists unresolved.
        doc_refs = CorpusReference.objects.filter(
            corpus=self.corpus, reference_type=C.REF_DOCUMENT
        )
        resolved = doc_refs.get(resolution_status=C.STATUS_RESOLVED)
        assert resolved.target_document_id == doc2.id
        mention = resolved.source_annotation
        assert mention.document_id == doc1.id
        assert mention.annotation_type == SPAN_LABEL
        assert mention.page == 0
        assert mention.json["text"] == mention.raw_text
        unresolved = doc_refs.get(resolution_status=C.STATUS_UNRESOLVED)
        assert (unresolved.normalized_data or {})[
            C.KEY_DOCUMENT_IDENTIFIER
        ] == "N999999"

        edges = DocumentRelationship.objects.filter(
            corpus=self.corpus, relationship_type=C.DOC_REL_RELATIONSHIP
        )
        assert edges.count() == 1
        assert edges.get().target_document_id == doc2.id

        # Rerun: stable counts across representations (producer sidecar spans
        # retained; enrichment mentions deduped).
        before = Annotation.objects.filter(corpus=self.corpus).count()
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        assert Annotation.objects.filter(corpus=self.corpus).count() == before
        assert doc_refs.count() == 2
        assert edges.count() == 1
