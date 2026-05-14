"""
Shared corpus state-snapshot helper for roundtrip tests.

This module is the single source of truth for "what should be preserved
when a corpus is copied" — used by both:

- ``test_corpus_export_import_v2.TestV2ThreeRoundTripDataIntegrity`` —
  asserts a corpus survives N export/import roundtrips unchanged.
- ``test_corpus_fork_round_trip`` parity tests — assert that
  ``fork(C)`` produces the same end-state corpus as
  ``export(C) → import(C)``.

The snapshot captures content-derived keys (titles, raw text, paths,
checksums) rather than PKs, since fork and export/import both mint new
IDs.  Optional ``strip_fork_prefix`` mode strips leading ``"[FORK] "``
sequences from titles so a fork snapshot can be compared against its
source/export-import snapshot.
"""

from __future__ import annotations

import json
import re
from typing import Any

from django.db.models import Q

from opencontractserver.annotations.compact_json import compact_annotation_json
from opencontractserver.annotations.models import (
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.constants.corpus_forking import FORK_TITLE_PREFIX
from opencontractserver.conversations.models import Conversation  # noqa: E402
from opencontractserver.conversations.models import ChatMessage, MessageVote
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDescriptionRevision,
    CorpusFolder,
)
from opencontractserver.documents.models import DocumentPath

_FORK_PREFIX_RE = re.compile(rf"^({re.escape(FORK_TITLE_PREFIX)})+")


def _strip_fork(title: str | None) -> str:
    """Strip any number of leading ``"[FORK] "`` sequences from ``title``."""
    if not title:
        return title or ""
    return _FORK_PREFIX_RE.sub("", title)


def snapshot_corpus(
    corpus: Corpus, *, strip_fork_prefix: bool = False
) -> dict[str, Any]:
    """
    Return a normalized snapshot of the in-scope state of ``corpus``.

    IDs and creation timestamps for entities that are re-minted on
    roundtrip (corpus, labelset, label, document, annotation pks) are
    deliberately excluded; content-derived keys are used instead so the
    snapshot is stable across fork / export / import operations.

    Args:
        corpus: The Corpus to snapshot.
        strip_fork_prefix: If True, any leading ``"[FORK] "`` sequences
            on the corpus / labelset / document / fieldset titles are
            removed before being added to the snapshot.  Used when
            comparing a fork to its export-import counterpart, since
            fork stacks ``"[FORK] "`` while export+import doesn't.
    """
    norm = _strip_fork if strip_fork_prefix else (lambda t: t or "")

    # ----- Active corpus-isolated documents via DocumentPath -----
    active_paths = list(
        DocumentPath.objects.filter(
            corpus=corpus, is_current=True, is_deleted=False
        ).select_related("document", "folder", "ingestion_source")
    )
    active_docs = [p.document for p in active_paths]

    # ----- User annotations summary + parent pairs -----
    annotations_summary: dict[tuple, dict] = {}
    user_annot_parent_pairs: list[tuple[str, str | None]] = []
    for doc in active_docs:
        qs = Annotation.objects.filter(
            document=doc, corpus=corpus, structural=False
        ).select_related("annotation_label", "parent")
        for annot in qs:
            key = (
                norm(doc.title),
                annot.annotation_label.text if annot.annotation_label else "",
                (annot.annotation_label.label_type if annot.annotation_label else ""),
                annot.raw_text or "",
                annot.annotation_type or "",
            )
            entry = annotations_summary.setdefault(
                key,
                {
                    "count": 0,
                    "long_descriptions": [],
                    "content_modalities": [],
                    "json_blobs": [],
                },
            )
            entry["count"] += 1
            entry["long_descriptions"].append(annot.long_description or "")
            entry["content_modalities"].append(sorted(annot.content_modalities or []))
            entry["json_blobs"].append(
                json.dumps(
                    compact_annotation_json(annot.json) or {},
                    sort_keys=True,
                    default=str,
                )
            )
            user_annot_parent_pairs.append(
                (
                    annot.raw_text or "",
                    annot.parent.raw_text if annot.parent else None,
                )
            )
    for entry in annotations_summary.values():
        entry["long_descriptions"].sort()
        entry["content_modalities"].sort()
        entry["json_blobs"].sort()
    user_annot_parent_pairs.sort()

    # ----- Structural annotation set summary -----
    struct_set_hashes = sorted(
        {
            d.structural_annotation_set.content_hash
            for d in active_docs
            if d.structural_annotation_set
        }
    )
    struct_summary: dict[str, dict] = {}
    for h in struct_set_hashes:
        s = StructuralAnnotationSet.objects.filter(content_hash=h).first()
        if not s:
            continue
        struct_annotations = list(
            Annotation.objects.filter(structural_set=s).select_related(
                "annotation_label"
            )
        )
        struct_relationships = list(Relationship.objects.filter(structural_set=s))
        parent_pairs = sorted(
            [
                (a.raw_text, a.parent.raw_text if a.parent else None)
                for a in struct_annotations
            ]
        )
        pawls_content = ""
        if s.pawls_parse_file and s.pawls_parse_file.name:
            with s.pawls_parse_file.open("r") as f:
                pawls_content = f.read()
        txt_content = ""
        if s.txt_extract_file and s.txt_extract_file.name:
            with s.txt_extract_file.open("r") as f:
                txt_content = f.read()
        struct_summary[h] = {
            "parser_name": s.parser_name,
            "parser_version": s.parser_version,
            "page_count": s.page_count,
            "token_count": s.token_count,
            "annotation_count": len(struct_annotations),
            "annotation_raw_texts": sorted(
                a.raw_text or "" for a in struct_annotations
            ),
            "annotation_types": sorted(
                a.annotation_type or "" for a in struct_annotations
            ),
            "annotation_long_descriptions": sorted(
                a.long_description or "" for a in struct_annotations
            ),
            "annotation_labels": sorted(
                a.annotation_label.text if a.annotation_label else ""
                for a in struct_annotations
            ),
            "annotation_json_blobs": sorted(
                json.dumps(
                    compact_annotation_json(a.json) or {},
                    sort_keys=True,
                    default=str,
                )
                for a in struct_annotations
            ),
            "parent_pairs": parent_pairs,
            "relationship_count": len(struct_relationships),
            "pawls_normalized": pawls_content,
            "txt_content": txt_content,
        }

    # ----- Folders -----
    folders = list(CorpusFolder.objects.filter(corpus=corpus).select_related("parent"))
    folder_summary = sorted(
        (
            f.get_path(),
            f.name,
            f.description,
            f.color,
            f.icon,
            tuple(f.tags or []),
        )
        for f in folders
    )

    # ----- DocumentPaths -----
    path_summary = sorted(
        (
            norm(p.document.title),
            p.path,
            p.folder.get_path() if p.folder else None,
            p.version_number,
            p.ingestion_source.name if p.ingestion_source else None,
            p.external_id or "",
            tuple(sorted((p.ingestion_metadata or {}).items())),
        )
        for p in active_paths
    )

    # ----- Non-structural relationships -----
    non_struct_rels = (
        Relationship.objects.filter(corpus=corpus, structural=False)
        .select_related("relationship_label")
        .order_by("id")
    )
    relationship_summary = []
    for rel in non_struct_rels:
        src = sorted(
            (
                norm(a.document.title) if a.document else "",
                a.raw_text or "",
                a.annotation_label.text if a.annotation_label else "",
            )
            for a in rel.source_annotations.select_related(
                "document", "annotation_label"
            ).all()
        )
        tgt = sorted(
            (
                norm(a.document.title) if a.document else "",
                a.raw_text or "",
                a.annotation_label.text if a.annotation_label else "",
            )
            for a in rel.target_annotations.select_related(
                "document", "annotation_label"
            ).all()
        )
        relationship_summary.append(
            {
                "label": (
                    rel.relationship_label.text if rel.relationship_label else ""
                ),
                "structural": rel.structural,
                "sources": src,
                "targets": tgt,
            }
        )

    # ----- Markdown description + revisions -----
    md_content = ""
    if corpus.md_description and corpus.md_description.name:
        with corpus.md_description.open("r") as f:
            md_content = f.read()
    revisions = list(
        CorpusDescriptionRevision.objects.filter(corpus=corpus).order_by("version")
    )
    revision_summary = [
        {
            "version": r.version,
            "diff": r.diff,
            "snapshot": r.snapshot,
            "checksum_base": r.checksum_base,
            "checksum_full": r.checksum_full,
        }
        for r in revisions
    ]

    # ----- Conversations + messages + votes -----
    convs = list(
        Conversation.objects.filter(
            Q(chat_with_corpus=corpus) | Q(chat_with_document__in=active_docs)
        )
        .select_related("chat_with_document")
        .order_by("id")
    )
    conv_summary = []
    for c in convs:
        msgs = list(ChatMessage.objects.filter(conversation=c).order_by("created_at"))
        msg_summary = [
            {
                "content": m.content or "",
                "msg_type": m.msg_type,
                "state": m.state,
                "data": m.data,
                "parent_content": (
                    m.parent_message.content if m.parent_message else None
                ),
                "created_at": m.created_at.isoformat(),
                "vote_types": sorted(
                    (v.vote_type, v.created_at.isoformat())
                    for v in MessageVote.objects.filter(message=m)
                ),
            }
            for m in msgs
        ]
        conv_summary.append(
            {
                "title": c.title or "",
                "description": c.description or "",
                "conversation_type": c.conversation_type or "chat",
                "is_public": c.is_public,
                "is_locked": c.is_locked,
                "is_pinned": c.is_pinned,
                "chat_with_corpus": c.chat_with_corpus_id == corpus.id,
                "chat_with_document_title": (
                    norm(c.chat_with_document.title) if c.chat_with_document else None
                ),
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
                "messages": msg_summary,
            }
        )
    conv_summary.sort(key=lambda c: (c["title"], c["chat_with_corpus"]))

    # ----- Ingestion source names -----
    used_source_names = sorted(
        {p.ingestion_source.name for p in active_paths if p.ingestion_source}
    )

    # ----- Labels (text + type pairs) -----
    if corpus.label_set:
        label_pairs = sorted(
            (label.text, label.label_type)
            for label in corpus.label_set.annotation_labels.all().distinct()
        )
        labelset_title = norm(corpus.label_set.title)
        labelset_description = corpus.label_set.description
    else:
        label_pairs = []
        labelset_title = ""
        labelset_description = ""

    # ----- Manual metadata schema -----
    from opencontractserver.extracts.models import Datacell

    metadata_summary: dict = {}
    fieldset = getattr(corpus, "metadata_schema", None)
    if fieldset is not None:
        columns_list = sorted(
            (
                {
                    "name": c.name,
                    "output_type": c.output_type,
                    "data_type": c.data_type,
                    "validation_config": c.validation_config or None,
                    "default_value": c.default_value,
                    "help_text": c.help_text,
                    "display_order": c.display_order,
                }
                for c in fieldset.columns.filter(is_manual_entry=True)
            ),
            key=lambda c: (c["display_order"], c["name"]),
        )
        datacells_list = sorted(
            (
                {
                    "column_name": dc.column.name,
                    "doc_title": norm(dc.document.title),
                    "data": dc.data,
                    "data_definition": dc.data_definition,
                }
                for dc in Datacell.objects.filter(
                    column__fieldset=fieldset, extract__isnull=True
                ).select_related("column", "document")
            ),
            key=lambda dc: (dc["doc_title"], dc["column_name"]),
        )
        metadata_summary = {
            "fieldset_name": norm(fieldset.name),
            "fieldset_description": fieldset.description or "",
            "columns": columns_list,
            "datacells": datacells_list,
        }

    return {
        "corpus": {
            "title": norm(corpus.title),
            "description": corpus.description,
            "corpus_agent_instructions": corpus.corpus_agent_instructions,
            "document_agent_instructions": corpus.document_agent_instructions,
            "post_processors": list(corpus.post_processors or []),
            "allow_comments": corpus.allow_comments,
        },
        "labelset_title": labelset_title,
        "labelset_description": labelset_description,
        "labels": label_pairs,
        "doc_titles": sorted(norm(d.title) for d in active_docs),
        "doc_hashes": sorted(d.pdf_file_hash or "" for d in active_docs),
        "doc_file_types": sorted(d.file_type or "" for d in active_docs),
        "doc_descriptions": sorted(d.description or "" for d in active_docs),
        "active_doc_count": len(active_docs),
        "annotations_summary": dict(sorted(annotations_summary.items())),
        "user_annot_parent_pairs": user_annot_parent_pairs,
        "struct_summary": struct_summary,
        "folders": sorted(folder_summary),
        "paths": path_summary,
        "relationships": relationship_summary,
        "md_description": md_content,
        "revisions": revision_summary,
        "conversations": conv_summary,
        "ingestion_sources": used_source_names,
        "metadata_schema": metadata_summary,
    }
