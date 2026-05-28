"""Canonical-CAML cutover — backfill Readme.CAML docs for every corpus.

Forward-only. For every Corpus with non-empty ``md_description`` and no
existing Readme.CAML Document attached via DocumentPath:
  1. Create a Document with title=Readme.CAML, file_type=text/markdown,
     fresh version_tree_id, is_current=True, and txt_extract_file
     holding the md_description body.
  2. Create a DocumentPath linking corpus → document with
     path='Readme.CAML', version_number=1, is_current=True.
  3. Replay every CorpusDescriptionRevision (oldest-first) as a
     Document version-tree sibling sharing the head's version_tree_id,
     with its own DocumentPath (is_current=False, is_deleted=False,
     version_number=N matching the revision order). Preserves
     created/modified by passing them explicitly.
  4. Populate Corpus.readme_caml_document_id pointing at the head.
  5. Refresh Corpus.description and Corpus.description_preview via
     compute_cache_from_caml_body.

Idempotent: re-running is a no-op for already-migrated rows because
each step uses lookup-before-create.

The schema removal (md_description column drop, CorpusDescriptionRevision
table drop) is deferred to migration 0053 so ops can run this data
migration in a maintenance window without forcing the schema cleanup
in the same transaction.

Spec: docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md §4.9
"""
from __future__ import annotations

import uuid

from django.core.files.base import ContentFile
from django.db import migrations


CAML_TITLE = "Readme.CAML"
CAML_FILE_TYPE = "text/markdown"
CAML_PATH = "Readme.CAML"


def _read_md_description(corpus) -> str:
    """Mirror Corpus._read_md_description_content for historical model use."""
    field = corpus.md_description
    if not (field and field.name):
        return ""
    try:
        field.open("r")
        try:
            return field.read()
        finally:
            field.close()
    except Exception:
        field.open("rb")
        try:
            return field.read().decode("utf-8", errors="ignore")
        finally:
            field.close()


def _get_existing_caml_doc(corpus_id, Document, DocumentPath):
    """Return the current Readme.CAML doc for the corpus, or None.

    Joins through DocumentPath because Document has no corpus FK.
    """
    path = (
        DocumentPath.objects.filter(
            corpus_id=corpus_id,
            path=CAML_PATH,
            is_current=True,
            is_deleted=False,
        )
        .order_by("-id")
        .first()
    )
    if path is None:
        return None
    return Document.objects.filter(pk=path.document_id).first()


def _create_caml_doc(corpus, body, Document, DocumentPath):
    """Create the head Readme.CAML Document + DocumentPath for the corpus."""
    tree_id = uuid.uuid4()
    doc = Document.objects.create(
        title=CAML_TITLE,
        file_type=CAML_FILE_TYPE,
        creator_id=corpus.creator_id,
        version_tree_id=tree_id,
        is_current=True,
    )
    doc.txt_extract_file.save(
        f"{CAML_TITLE}.md",
        ContentFile(body.encode("utf-8")),
        save=True,
    )
    DocumentPath.objects.create(
        document=doc,
        corpus=corpus,
        folder=None,
        path=CAML_PATH,
        version_number=1,
        is_current=True,
        is_deleted=False,
        creator_id=corpus.creator_id,
    )
    return doc


def _replay_revisions(corpus, head_doc, Document, DocumentPath, RevisionModel):
    """Each revision becomes a Document sibling sharing head's version_tree_id.

    Replays oldest-first. Siblings carry is_current=False on both
    Document and DocumentPath. Preserves created/modified by passing
    them explicitly.
    """
    revisions = RevisionModel.objects.filter(corpus_id=corpus.pk).order_by("version")
    for rev in revisions:
        snap = rev.snapshot
        if not snap:
            continue  # diff-only revisions can't be replayed standalone
        sibling = Document.objects.create(
            title=CAML_TITLE,
            file_type=CAML_FILE_TYPE,
            creator_id=rev.author_id or corpus.creator_id,
            version_tree_id=head_doc.version_tree_id,
            is_current=False,
            created=rev.created,
        )
        sibling.txt_extract_file.save(
            f"{CAML_TITLE}.v{rev.version}.md",
            ContentFile(snap.encode("utf-8")),
            save=True,
        )
        DocumentPath.objects.create(
            document=sibling,
            corpus=corpus,
            folder=None,
            path=CAML_PATH,
            version_number=rev.version,  # Use historical version order
            is_current=False,
            is_deleted=False,
            creator_id=rev.author_id or corpus.creator_id,
        )


def backfill_all(apps, schema_editor):
    """Iterate every Corpus, backfill, refresh cache. Idempotent."""
    from opencontractserver.corpuses.services.description_cache import (
        compute_cache_from_caml_body,
    )

    Corpus = apps.get_model("corpuses", "Corpus")
    Document = apps.get_model("documents", "Document")
    DocumentPath = apps.get_model("documents", "DocumentPath")
    RevisionModel = apps.get_model("corpuses", "CorpusDescriptionRevision")

    for corpus in Corpus.objects.iterator(chunk_size=200):
        body = _read_md_description(corpus)
        head = _get_existing_caml_doc(corpus.pk, Document, DocumentPath)
        if head is None and body:
            head = _create_caml_doc(corpus, body, Document, DocumentPath)
            _replay_revisions(corpus, head, Document, DocumentPath, RevisionModel)
        if head is not None:
            plain, preview = compute_cache_from_caml_body(body or "")
            Corpus.objects.filter(pk=corpus.pk).update(
                description=plain,
                description_preview=preview,
                readme_caml_document_id=head.pk,
            )
        else:
            # No body, no doc — explicitly zero the cache
            Corpus.objects.filter(pk=corpus.pk).update(
                description="",
                description_preview="",
                readme_caml_document_id=None,
            )


def noop_reverse(apps, schema_editor):
    """Forward-only — column-drop content has no useful reverse."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0051_add_readme_caml_fk"),
        ("documents", "0039_add_preferred_enrichers_to_pipeline_settings"),
    ]

    operations = [
        migrations.RunPython(backfill_all, noop_reverse),
    ]
