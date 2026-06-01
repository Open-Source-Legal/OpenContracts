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
  5. Refresh Corpus.description and Corpus.description_preview via the
     migration-local ``_compute_cache_from_caml_body`` (a frozen copy of the
     live ``description_cache`` derivation, so this historical migration stays
     self-contained).

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

# Frozen snapshot of ``MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH`` at the time this
# migration was written. Migrations are historical snapshots, so the cache
# derivation is inlined here (rather than importing the live
# ``description_cache`` service) — a future rename/signature change to that
# module must not break this historical migration on fresh installs.
_PREVIEW_MAX_LENGTH = 280


def _markdown_to_plain_text(md: str) -> str:
    """Migration-local copy of ``description_cache.markdown_to_plain_text``."""
    import re

    if not md:
        return ""
    text = md
    text = re.sub(r"^```[^\n]*\n(.*?)^```", r"\1", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"~~(.+?)~~", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _summarize_for_preview(plain_text: str) -> str:
    """Migration-local copy of ``description_cache.summarize_for_preview``."""
    import re

    if not plain_text:
        return ""
    first_paragraph = plain_text.split("\n\n", 1)[0].strip()
    first_paragraph = re.sub(r"\s+", " ", first_paragraph)
    if len(first_paragraph) <= _PREVIEW_MAX_LENGTH:
        return first_paragraph
    cut = first_paragraph[:_PREVIEW_MAX_LENGTH]
    last_space = cut.rfind(" ")
    if last_space > _PREVIEW_MAX_LENGTH // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def _compute_cache_from_caml_body(body) -> tuple[str, str]:
    """Migration-local copy of ``description_cache.compute_cache_from_caml_body``."""
    if not body:
        return "", ""
    plain = _markdown_to_plain_text(body)
    return plain, _summarize_for_preview(plain)


def _coerce_to_text(data) -> str:
    """Normalise a ``FieldFile.read()`` result to ``str``.

    Cloud storage backends (S3Boto3Storage / GoogleCloudStorage via
    django-storages #382) silently return ``bytes`` from a text-mode
    (``"r"``) read *without raising*, so the ``except``-guarded binary
    fallbacks in the readers below never fire — the ``bytes`` flow
    downstream into ``str``-only call sites such as ``body.encode("utf-8")``
    in :func:`_create_caml_doc`, crashing the backfill on cloud deployments
    (``AttributeError: 'bytes' object has no attribute 'encode'``). Local
    ``FileSystemStorage`` returns ``str``, which is why this never surfaced
    in tests.

    Inlined rather than imported from
    ``opencontractserver.utils.files.read_field_file_text`` to keep this
    historical migration self-contained (see module docstring).
    """
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="ignore")
    return data


def _read_md_description(corpus) -> str:
    """Mirror Corpus._read_md_description_content for historical model use."""
    field = corpus.md_description
    if not (field and field.name):
        return ""
    try:
        field.open("r")
        try:
            return _coerce_to_text(field.read())
        finally:
            field.close()
    except Exception:
        # Binary fallback for storage that rejects text-mode reads. Wrap
        # in its own try/except so a single corrupted blob does not abort
        # the entire backfill — log and skip instead.
        try:
            field.open("rb")
            try:
                return field.read().decode("utf-8", errors="ignore")
            finally:
                field.close()
        except Exception:
            return ""


def _read_caml_doc_body(doc) -> str:
    """Read the txt_extract_file body from a Readme.CAML Document instance.

    Migration-local mirror of ``description_cache.read_caml_body`` so the
    backfill can read an already-existing CAML doc on idempotent re-run
    (when ``md_description`` is empty but the head doc already exists).
    """
    field = doc.txt_extract_file
    if not (field and field.name):
        return ""
    try:
        field.open("r")
        try:
            return _coerce_to_text(field.read())
        finally:
            field.close()
    except Exception:
        try:
            field.open("rb")
            try:
                return field.read().decode("utf-8", errors="ignore")
            finally:
                field.close()
        except Exception:
            return ""


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
            # On an idempotent re-run the legacy ``md_description`` may be
            # empty (already cleared), but the CAML doc already exists and
            # is the canonical source. Read its body rather than zeroing the
            # cache from an empty legacy field.
            cache_body = body if body else _read_caml_doc_body(head)
            plain, preview = _compute_cache_from_caml_body(cache_body)
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
        ("corpuses", "0053_add_readme_caml_fk"),
        ("documents", "0039_add_preferred_enrichers_to_pipeline_settings"),
    ]

    operations = [
        migrations.RunPython(backfill_all, noop_reverse),
    ]
