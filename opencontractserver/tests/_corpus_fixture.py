"""
Shared rich-corpus fixture for roundtrip / parity tests.

Both ``TestV2ThreeRoundTripDataIntegrity`` (export/import) and the fork
parity tests need the same "everything turned on" corpus to exercise
every feature that should round-trip.  Putting the construction here
keeps the two tests aligned and prevents drift.
"""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone as tz

from django.core.files.base import ContentFile

from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageVote,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusFolder,
)
from opencontractserver.documents.models import Document, DocumentPath, IngestionSource
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

# Minimal valid PDF used by every doc in the fixture so the export
# pipeline has something to ZIP.
_MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj <</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj <</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj <</Type/Page/Parent 2 0 R/Resources<<>>/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n"
    b"0000000115 00000 n\ntrailer <</Size 4/Root 1 0 R>>\nstartxref\n204\n%%EOF\n"
)


def build_rich_test_corpus(user) -> Corpus:
    """
    Construct a fully-featured corpus exercising every in-scope V2 feature:

    - 4 labels (token, span, doc-type, relationship)
    - Root → Child folder hierarchy
    - Shared structural annotation set with parent-linked structural
      annotations + a structural relationship
    - 2 documents (both sharing the structural set), with file content,
      hashes, ingestion lineage on one path
    - User annotations: token, span, doc-type, plus a parent-linked
      token annotation
    - Cross-document corpus-level relationship
    - md description routed through CorpusService.update_description so
      the corpus has a canonical Readme.CAML Document on construction
      (the V3 export carries it forward via annotated_docs)
    - Conversations (corpus-level + doc-level) with messages and a vote,
      using fixed historical timestamps so timestamp preservation is
      checked too
    - Manual metadata schema (Fieldset + manual Columns + Datacells)

    The returned ``Corpus`` is the canonical reference; callers can
    re-query any related objects from it.
    """
    # ----- Labels & label set ----------------------------------------
    labelset = LabelSet.objects.create(
        title="Roundtrip LabelSet",
        description="LabelSet for 3x roundtrip integrity test",
        creator=user,
    )
    token_label = AnnotationLabel.objects.create(
        text="RT Token Label",
        description="A token label",
        color="#abcdef",
        label_type=TOKEN_LABEL,
        creator=user,
    )
    span_label = AnnotationLabel.objects.create(
        text="RT Span Label",
        description="A span label",
        color="#fedcba",
        label_type=SPAN_LABEL,
        creator=user,
    )
    doc_label = AnnotationLabel.objects.create(
        text="RT Doc Label",
        description="A doc-type label",
        color="#112233",
        label_type=DOC_TYPE_LABEL,
        creator=user,
    )
    rel_label = AnnotationLabel.objects.create(
        text="RT Rel Label",
        description="A relationship label",
        color="#445566",
        label_type=RELATIONSHIP_LABEL,
        creator=user,
    )
    labelset.annotation_labels.add(token_label, span_label, doc_label, rel_label)

    # ----- Corpus ----------------------------------------------------
    corpus = Corpus.objects.create(
        title="Roundtrip Corpus",
        description="Rich fixture for 3x roundtrip integrity test",
        label_set=labelset,
        creator=user,
        corpus_agent_instructions="Corpus-level instructions for RT",
        document_agent_instructions="Document-level instructions for RT",
        post_processors=["pp.one", "pp.two"],
        allow_comments=True,
    )
    set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.ALL])

    # ----- Folder hierarchy ------------------------------------------
    root_folder = CorpusFolder.objects.create(
        corpus=corpus,
        name="Root",
        description="root folder",
        color="#aa0000",
        icon="folder",
        tags=["root", "rt"],
        creator=user,
    )
    child_folder = CorpusFolder.objects.create(
        corpus=corpus,
        name="Child",
        description="child folder",
        color="#00aa00",
        icon="folder",
        tags=["child"],
        parent=root_folder,
        creator=user,
    )

    # ----- Structural annotation set shared across two documents ----
    pawls_payload = [
        {
            "page": {"index": 0, "width": 612, "height": 792},
            "tokens": [
                {"x": 10, "y": 10, "width": 50, "height": 12, "text": "Hello"},
                {"x": 70, "y": 10, "width": 50, "height": 12, "text": "World"},
            ],
        }
    ]
    struct_set = StructuralAnnotationSet.objects.create(
        content_hash="rt_struct_hash",
        parser_name="docling",
        parser_version="9.9",
        page_count=1,
        token_count=2,
        pawls_parse_file=ContentFile(
            json.dumps(pawls_payload).encode("utf-8"), name="pawls.json"
        ),
        txt_extract_file=ContentFile(b"Hello World extracted text", name="text.txt"),
        creator=user,
    )
    struct_parent = Annotation.objects.create(
        structural_set=struct_set,
        annotation_label=token_label,
        raw_text="Hello",
        page=0,
        json={
            "0": {
                "bounds": {"left": 10, "top": 10, "right": 60, "bottom": 22},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                "rawText": "Hello",
            }
        },
        annotation_type="header",
        structural=True,
        long_description="Top-of-doc heading",
        creator=user,
    )
    struct_child = Annotation.objects.create(
        structural_set=struct_set,
        annotation_label=token_label,
        raw_text="World",
        page=0,
        json={
            "0": {
                "bounds": {"left": 70, "top": 10, "right": 120, "bottom": 22},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                "rawText": "World",
            }
        },
        annotation_type="paragraph",
        structural=True,
        parent=struct_parent,
        creator=user,
    )
    struct_rel = Relationship.objects.create(
        structural_set=struct_set,
        relationship_label=rel_label,
        structural=True,
        creator=user,
    )
    struct_rel.source_annotations.set([struct_parent.id])
    struct_rel.target_annotations.set([struct_child.id])

    # ----- Ingestion source ------------------------------------------
    ingestion_source = IngestionSource.objects.create(
        name="rt_crawler",
        source_type="crawler",
        config={"endpoint": "https://example.invalid/feed"},
        active=True,
        creator=user,
    )

    # ----- Two documents, both sharing the structural set ------------
    doc_a = Document.objects.create(
        title="Doc A",
        description="First doc",
        pdf_file=ContentFile(_MINIMAL_PDF_BYTES, name="doc_a.pdf"),
        pdf_file_hash="rt_doc_a_hash",
        file_type="application/pdf",
        page_count=1,
        structural_annotation_set=struct_set,
        creator=user,
    )
    doc_b = Document.objects.create(
        title="Doc B",
        description="Second doc",
        pdf_file=ContentFile(_MINIMAL_PDF_BYTES, name="doc_b.pdf"),
        pdf_file_hash="rt_doc_b_hash",
        file_type="application/pdf",
        page_count=1,
        structural_annotation_set=struct_set,
        creator=user,
    )
    set_permissions_for_obj_to_user(user, doc_a, [PermissionTypes.ALL])
    set_permissions_for_obj_to_user(user, doc_b, [PermissionTypes.ALL])

    DocumentPath.objects.create(
        document=doc_a,
        corpus=corpus,
        folder=root_folder,
        path="/documents/doc_a.pdf",
        version_number=1,
        ingestion_source=ingestion_source,
        external_id="ext-A-1",
        ingestion_metadata={"source_run": "abc123"},
        creator=user,
    )
    DocumentPath.objects.create(
        document=doc_b,
        corpus=corpus,
        folder=child_folder,
        path="/documents/doc_b.pdf",
        version_number=1,
        creator=user,
    )

    # ----- User annotations ------------------------------------------
    annot_a_tok = Annotation.objects.create(
        document=doc_a,
        corpus=corpus,
        annotation_label=token_label,
        raw_text="Doc A first annotation",
        page=0,
        json={
            "0": {
                "bounds": {"left": 10, "top": 30, "right": 100, "bottom": 42},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                "rawText": "Doc A first annotation",
            }
        },
        annotation_type="paragraph",
        creator=user,
    )
    Annotation.objects.create(
        document=doc_a,
        corpus=corpus,
        annotation_label=span_label,
        raw_text="A span on doc A",
        page=0,
        json={"start": 0, "end": 14},
        annotation_type="span",
        creator=user,
    )
    annot_b_tok = Annotation.objects.create(
        document=doc_b,
        corpus=corpus,
        annotation_label=token_label,
        raw_text="Doc B annotation",
        page=0,
        json={
            "0": {
                "bounds": {"left": 20, "top": 50, "right": 200, "bottom": 62},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                "rawText": "Doc B annotation",
            }
        },
        annotation_type="paragraph",
        content_modalities=["TEXT"],
        long_description="Long-form analysis of the doc B clause",
        creator=user,
    )
    # Child annotation parented to annot_b_tok — exercises parent_id
    # remapping during import.
    Annotation.objects.create(
        document=doc_b,
        corpus=corpus,
        annotation_label=token_label,
        raw_text="Doc B child clause",
        page=0,
        json={
            "0": {
                "bounds": {"left": 220, "top": 50, "right": 280, "bottom": 62},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                "rawText": "Doc B child clause",
            }
        },
        annotation_type="paragraph",
        parent=annot_b_tok,
        creator=user,
    )
    Annotation.objects.create(
        document=doc_a,
        corpus=corpus,
        annotation_label=doc_label,
        annotation_type=DOC_TYPE_LABEL,
        creator=user,
    )

    cross_rel = Relationship.objects.create(
        corpus=corpus,
        document=doc_a,
        relationship_label=rel_label,
        structural=False,
        creator=user,
    )
    cross_rel.source_annotations.set([annot_a_tok.id])
    cross_rel.target_annotations.set([annot_b_tok.id])

    # ----- Markdown description (canonical CAML write path) ----------
    #
    # Routed through ``CorpusService.update_description`` so the fixture
    # produces a real Readme.CAML Document on construction (Task 14 of
    # the Canonical-CAML refactor).  The legacy
    # ``corpus.md_description.save(...)`` + ``CorpusDescriptionRevision``
    # write path is gone — V3 export carries the CAML doc forward via
    # ``annotated_docs`` like any other Document, and the importer
    # re-attaches it on the other side.
    #
    # ``update_description`` cascades the cache refresh via the Document
    # ``post_save`` signal's ``transaction.on_commit`` hook, but Django's
    # ``TestCase`` wraps the test in a transaction that never commits.
    # Refresh the cache columns directly here so the snapshot helpers
    # observe canonical state regardless of which TestCase / atomic
    # context the fixture is invoked from.
    from opencontractserver.corpuses.services.corpus_service import CorpusService
    from opencontractserver.corpuses.services.description_cache import (
        refresh_description_cache_for_corpus,
    )

    md_text = "# Roundtrip Corpus\n\nA test corpus for export round-tripping.\n"
    CorpusService.update_description(user, corpus, md_text)
    refresh_description_cache_for_corpus(corpus.pk)
    corpus.refresh_from_db()

    # ----- Manual metadata schema ------------------------------------
    from opencontractserver.extracts.models import Column, Datacell, Fieldset

    metadata_fieldset = Fieldset.objects.create(
        name="RT Metadata Schema",
        description="Manual metadata schema for the roundtrip fixture",
        corpus=corpus,
        creator=user,
    )
    col_status = Column.objects.create(
        name="Status",
        fieldset=metadata_fieldset,
        output_type="str",
        data_type="STRING",
        validation_config={"required": True},
        default_value=None,
        help_text="Document review status",
        display_order=0,
        is_manual_entry=True,
        creator=user,
    )
    col_priority = Column.objects.create(
        name="Priority",
        fieldset=metadata_fieldset,
        output_type="int",
        data_type="INTEGER",
        validation_config={"min": 0, "max": 10},
        default_value={"value": 3},
        help_text="Triage priority 0-10",
        display_order=1,
        is_manual_entry=True,
        creator=user,
    )
    Datacell.objects.create(
        column=col_status,
        document=doc_a,
        data={"value": "approved"},
        data_definition="str",
        creator=user,
    )
    Datacell.objects.create(
        column=col_priority,
        document=doc_a,
        data={"value": 7},
        data_definition="int",
        creator=user,
    )
    Datacell.objects.create(
        column=col_status,
        document=doc_b,
        data={"value": "pending"},
        data_definition="str",
        creator=user,
    )

    # ----- Conversations / messages / votes --------------------------
    conv_ts_corpus = datetime(2024, 1, 2, 3, 4, 5, tzinfo=tz.utc)
    conv_ts_doc = datetime(2024, 1, 3, 8, 30, 15, tzinfo=tz.utc)
    msg_ts_parent = datetime(2024, 1, 2, 3, 5, 0, tzinfo=tz.utc)
    msg_ts_child = datetime(2024, 1, 2, 3, 6, 30, tzinfo=tz.utc)
    msg_ts_doc = datetime(2024, 1, 3, 9, 0, 0, tzinfo=tz.utc)
    vote_ts = datetime(2024, 1, 2, 3, 7, 45, tzinfo=tz.utc)

    corpus_conv = Conversation.objects.create(
        chat_with_corpus=corpus,
        title="Corpus chat",
        description="A corpus-level conversation",
        conversation_type="chat",
        is_public=True,
        is_locked=False,
        is_pinned=True,
        creator=user,
    )
    set_permissions_for_obj_to_user(user, corpus_conv, [PermissionTypes.ALL])
    doc_conv = Conversation.objects.create(
        chat_with_document=doc_a,
        title="Doc A chat",
        description="A doc-level conversation",
        conversation_type="chat",
        creator=user,
    )
    set_permissions_for_obj_to_user(user, doc_conv, [PermissionTypes.ALL])

    msg_parent = ChatMessage.objects.create(
        conversation=corpus_conv,
        content="Hello, corpus assistant",
        msg_type="HUMAN",
        state="completed",
        data={"meta": "user msg"},
        creator=user,
    )
    msg_child = ChatMessage.objects.create(
        conversation=corpus_conv,
        content="Hi, here's a reply",
        msg_type="LLM",
        state="completed",
        parent_message=msg_parent,
        data={"meta": "llm msg"},
        creator=user,
    )
    doc_msg = ChatMessage.objects.create(
        conversation=doc_conv,
        content="What's in doc A?",
        msg_type="HUMAN",
        state="completed",
        creator=user,
    )
    MessageVote.objects.create(message=msg_child, vote_type="upvote", creator=user)

    Conversation.all_objects.filter(pk=corpus_conv.pk).update(
        created_at=conv_ts_corpus, updated_at=conv_ts_corpus
    )
    Conversation.all_objects.filter(pk=doc_conv.pk).update(
        created_at=conv_ts_doc, updated_at=conv_ts_doc
    )
    ChatMessage.all_objects.filter(pk=msg_parent.pk).update(created_at=msg_ts_parent)
    ChatMessage.all_objects.filter(pk=msg_child.pk).update(created_at=msg_ts_child)
    ChatMessage.all_objects.filter(pk=doc_msg.pk).update(created_at=msg_ts_doc)
    MessageVote.objects.filter(message=msg_child).update(created_at=vote_ts)

    return corpus
