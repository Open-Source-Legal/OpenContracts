"""Tools for reviewing and editing the corpus's ``Readme.CAML`` article.

The CAML article is a Markdown ``Document`` attached to a corpus
(``title="Readme.CAML"``, ``file_type="text/markdown"``) whose body lives in
``txt_extract_file``.  Citations inside CAML use the directive syntax
``{{@cite SCOPE [args]}}`` where ``SCOPE`` is one of ``sentence`` /
``paragraph`` / ``block`` and ``args`` is an optional ``key=value`` list
(``mode=all``, ``limit=5``).  Citations are resolved client-side via semantic
search at render time -- see
``frontend/src/components/corpuses/caml/useCiteHandler.tsx``.

Three tools compose into a step-by-step CAML review flow that lets the agent
walk through citations one at a time, asking the user before each edit:

  1. ``aread_corpus_caml_article`` -- read-only.  Loads the Readme.CAML for
     the current corpus and returns block-level structure plus the inline
     directives already present.

  2. ``apropose_caml_citation_match`` -- read-only.  Given a query string,
     runs the same semantic search the renderer uses and returns ranked
     annotation candidates so the agent can verify a citation before asking
     the user to insert one.

  3. ``aapply_caml_article_edit`` -- requires approval.  Replaces a single
     occurrence of ``target_text`` with ``replacement_text`` inside the
     Readme.CAML.  Each call triggers one approval prompt, so the agent
     steps through the article one citation at a time.

All three tools use the existing ``visible_to_user`` / ``user_can``
patterns documented in ``docs/permissioning/consolidated_permissioning_guide.md``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction

from opencontractserver.constants.document_processing import (
    CAML_ARTICLE_TITLE,
    CAML_CITATION_MAX_CANDIDATES,
    CAML_EDIT_PREVIEW_RADIUS_CHARS,
    MARKDOWN_MIME_TYPE,
)
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)

# Public API of this module.  ``CAML_ARTICLE_TITLE`` is re-exported here
# for callers that historically imported the title from this module (test
# patches, registry definitions); its canonical home is
# ``opencontractserver.constants.document_processing``.
__all__ = [
    "CAML_ARTICLE_TITLE",
    "aread_corpus_caml_article",
    "apropose_caml_citation_match",
    "aapply_caml_article_edit",
]

# Mirror of ``DIRECTIVE_PATTERN_GLOBAL`` from
# ``frontend/src/components/corpuses/caml/inlineDirectives.ts`` so backend
# parsing matches what the renderer extracts.
_DIRECTIVE_PATTERN = re.compile(
    r"\{\{@(\w+)\s+(sentence|paragraph|block)(?:\s+([^}]+?))?\}\}"
)
_DIRECTIVE_ARG_PATTERN = re.compile(r'(\w+)=(?:"([^"]+)"|(\S+))')


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _parse_directive_args(raw: str | None) -> dict[str, str]:
    """Parse a directive's ``key=value key2=value2`` argument list."""
    if not raw:
        return {}
    args: dict[str, str] = {}
    for match in _DIRECTIVE_ARG_PATTERN.finditer(raw):
        args[match.group(1)] = match.group(2) or match.group(3)
    return args


def _split_blocks(content: str) -> list[tuple[int, int, str]]:
    """Split markdown ``content`` into blank-line-delimited blocks.

    Returns ``(char_start, char_end, text)`` triples preserving the absolute
    offsets in the source so the caller can map blocks back to the original
    file.  Empty blocks are skipped.
    """
    blocks: list[tuple[int, int, str]] = []
    pos = 0
    for match in re.finditer(r"\n\s*\n", content):
        end = match.start()
        text = content[pos:end]
        if text.strip():
            blocks.append((pos, end, text))
        pos = match.end()
    tail = content[pos:]
    if tail.strip():
        blocks.append((pos, len(content), tail))
    return blocks


def _looks_like_prose(text: str) -> bool:
    """Heuristic: is ``text`` natural-language prose suitable for a citation?

    Returns ``False`` for headings, lists, code fences, blockquotes, table
    rows, thematic breaks/setext underlines, and embedded component markers
    so the candidate list stays focused on paragraphs the user would actually
    want to cite.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # Thematic breaks and setext heading underlines are blocks consisting of
    # only ``-``, ``_``, ``=``, or ``*`` (with optional spaces) — exclude them
    # before the first-character check so a lone ``___`` or ``***`` paragraph
    # doesn't slip through as prose.  ``***`` is a valid CommonMark thematic
    # break; emphasis runs like ``*Force majeure*`` survive because they
    # contain non-asterisk characters and so are not a subset of this set.
    if set(stripped.replace(" ", "")) <= {"-", "_", "=", "*"}:
        return False
    # CommonMark list markers require a following whitespace
    # (``- item``, ``* item``, ``+ item``).  Without the whitespace the
    # leading character is start-of-prose — e.g. ``*Force majeure* clauses…``
    # is a paragraph that begins with an emphasis run, not a list.  Match
    # the parser's behaviour and only reject when the marker is followed
    # by a space or tab.
    if stripped.startswith(("- ", "* ", "+ ", "-\t", "*\t", "+\t")) or stripped[:1] in {
        "#",
        ">",
        "|",
    }:
        return False
    if stripped.startswith("```"):
        return False
    if stripped.startswith("[component:"):
        return False
    if re.match(r"^\d+\.\s", stripped):
        return False
    return True


def _load_caml_document_for_user(corpus_id: int, user) -> Document:
    """Return the corpus's ``Readme.CAML`` document if visible to ``user``.

    Delegates to :meth:`CorpusDocumentService.get_corpus_caml_articles`, which
    gates by corpus READ and applies the ``Readme.CAML`` / ``text/markdown``
    filter. Returns the same opaque "not found" message for both "corpus
    does not exist" and "user lacks permission" so the message cannot be
    used for enumeration.
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services import CorpusDocumentService

    not_found = (
        f"Corpus id={corpus_id} has no Readme.CAML article visible to this user."
    )

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist:
        raise ValueError(not_found)

    doc = CorpusDocumentService.get_corpus_caml_articles(user, corpus).first()
    if doc is None:
        raise ValueError(not_found)
    return doc


def _assert_corpus_visible_to_user(corpus_id: int, author_id: int) -> None:
    """Raise ``ValueError`` if ``author_id`` cannot see ``corpus_id``.

    Defense-in-depth check used by tools that don't go through
    :func:`_load_caml_document_for_user` (which performs the same validation
    as part of locating the CAML document).  Returns the same opaque
    "not found" message the read/edit tools surface so a caller cannot
    distinguish "missing user", "missing corpus", and "no permission".
    """
    User = get_user_model()
    not_found = f"Corpus id={corpus_id} is not visible to this user."
    try:
        user = User.objects.get(pk=author_id)
    except User.DoesNotExist:
        raise ValueError(not_found)

    from opencontractserver.corpuses.models import Corpus

    if not Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists():
        raise ValueError(not_found)


def _safe_delete_storage_path(name: str) -> None:
    """Delete a storage path, swallowing failures.

    Used as an ``on_commit`` callback after rotating a CAML article's
    underlying blob.  The new file is already persisted and the DB pointer
    has been bumped; if the old-blob delete fails (transient storage
    error, missing object, etc.) we don't want to surface the failure to
    the agent, since the user-visible edit succeeded.  An orphan blob is
    recoverable via housekeeping; a thrown exception here is not.
    """
    if not name:
        return
    from django.core.files.storage import default_storage

    try:
        default_storage.delete(name)
    except Exception:
        logger.exception("Failed to delete orphaned CAML blob %s", name)


def _read_caml_content(doc: Document) -> str:
    """Read the markdown body of a Readme.CAML document, or '' if empty.

    The file is always written as UTF-8 (see ``ContentFile(... .encode("utf-8"))``
    sites that produce these documents); we open in binary mode and decode
    explicitly so the read doesn't accidentally honour the runtime locale on
    non-UTF-8 hosts and corrupt accented or smart-quote characters in legal text.
    """
    if not doc.txt_extract_file:
        return ""
    with doc.txt_extract_file.open("rb") as fh:
        raw = fh.read()
    return raw.decode("utf-8")


# --------------------------------------------------------------------------- #
# Tool 1 -- read                                                              #
# --------------------------------------------------------------------------- #


def _read_corpus_caml_article(*, corpus_id: int, author_id: int) -> dict[str, Any]:
    """Synchronous worker for :func:`aread_corpus_caml_article`."""
    User = get_user_model()
    try:
        user = User.objects.get(pk=author_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={author_id} does not exist.")

    doc = _load_caml_document_for_user(corpus_id, user)
    content = _read_caml_content(doc)

    blocks: list[dict[str, Any]] = []
    total_directives = 0
    for block_idx, (char_start, char_end, text) in enumerate(_split_blocks(content)):
        directives: list[dict[str, Any]] = []
        for match in _DIRECTIVE_PATTERN.finditer(text):
            directives.append(
                {
                    "agent": match.group(1),
                    "scope": match.group(2),
                    "args": _parse_directive_args(match.group(3)),
                    "block_offset": match.start(),
                    "absolute_offset": char_start + match.start(),
                }
            )
        total_directives += len(directives)

        has_cite = any(d["agent"] == "cite" for d in directives)
        is_prose = _looks_like_prose(text)
        blocks.append(
            {
                "block_idx": block_idx,
                "text": text,
                "char_start": char_start,
                "char_end": char_end,
                "directives": directives,
                "is_prose": is_prose,
                "has_citation_directive": has_cite,
                "needs_citation_candidate": is_prose and not has_cite,
            }
        )

    return {
        "corpus_id": corpus_id,
        "document_id": doc.pk,
        "title": doc.title,
        "modified": doc.modified.isoformat() if doc.modified else None,
        "content": content,
        "blocks": blocks,
        "total_directives": total_directives,
        "candidate_block_indices": [
            b["block_idx"] for b in blocks if b["needs_citation_candidate"]
        ],
    }


async def aread_corpus_caml_article(
    *, corpus_id: int, author_id: int
) -> dict[str, Any]:
    """Read the corpus's ``Readme.CAML`` article for citation review.

    Loads the Markdown content, splits it into blank-line-delimited blocks
    (paragraphs), and tags each block with its existing inline directives plus
    a ``needs_citation_candidate`` heuristic that flags prose blocks lacking a
    ``{{@cite ...}}`` directive.  The agent uses ``candidate_block_indices`` to
    decide which blocks to propose citations for.

    Args:
        corpus_id: ID of the corpus whose ``Readme.CAML`` should be read
            (injected from agent context).
        author_id: ID of the user invoking the tool (injected from agent
            context, used for permission scoping).

    Returns:
        A dict with the article content, per-block structure, and existing
        directive metadata.
    """
    return await _db_sync_to_async(_read_corpus_caml_article)(
        corpus_id=corpus_id,
        author_id=author_id,
    )


# --------------------------------------------------------------------------- #
# Tool 2 -- propose                                                           #
# --------------------------------------------------------------------------- #


async def apropose_caml_citation_match(
    *,
    corpus_id: int,
    author_id: int,
    query_text: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Propose annotation citation candidates for a CAML prose snippet.

    Runs the same semantic search the CAML renderer uses (see
    ``frontend/src/components/corpuses/caml/useCiteHandler.tsx``) over
    annotations visible to the invoking user in the current corpus.  Returns
    ranked candidates so the agent can confirm a citation with the user
    before calling :func:`aapply_caml_article_edit`.

    Args:
        corpus_id: Corpus to search within (injected).
        author_id: User performing the search (injected) -- scopes results
            via ``CoreAnnotationVectorStore`` user filter, which honours
            ``Annotation.objects.visible_to_user`` semantics.
        query_text: The CAML prose snippet to find citations for (typically a
            sentence or paragraph from ``aread_corpus_caml_article``).
        limit: Maximum number of candidates to return (default 5, capped at
            25).

    Returns:
        List of candidate dicts with ``annotation_id``, ``raw_text``,
        ``label_text``, ``label_color``, ``document_id``, ``document_title``,
        ``corpus_id``, ``page``, and ``similarity_score``.  Empty list if no
        matches are found.
    """
    from opencontractserver.llms.vector_stores import (
        CoreAnnotationVectorStore,
        VectorSearchQuery,
    )

    if not query_text or not query_text.strip():
        raise ValueError("query_text must be a non-empty string.")

    # Defense-in-depth corpus-visibility check: the tool is registered with
    # ``requires_corpus=True`` and the vector store further scopes results via
    # ``user_id``, but mirror the explicit ``visible_to_user`` guard the read
    # and edit tools enforce inline so this function fails closed if it is
    # ever invoked outside the registry wrapper.  Wrapped via
    # ``_db_sync_to_async`` because this function runs on the event loop.
    await _db_sync_to_async(_assert_corpus_visible_to_user)(
        corpus_id=corpus_id, author_id=author_id
    )

    capped_limit = max(1, min(int(limit), CAML_CITATION_MAX_CANDIDATES))

    # Wrap both store construction and the search call: the constructor itself
    # invokes ``get_embedder()`` and raises ``ValueError`` if the corpus has no
    # preferred embedder and ``PipelineSettings`` lacks a default — that's a
    # semantic-search precondition failure, not a fatal tool error, so surface
    # it through the same friendly "Semantic search failed" message the agent
    # knows how to recover from.
    try:
        store = CoreAnnotationVectorStore(
            user_id=author_id,
            corpus_id=corpus_id,
        )
        query = VectorSearchQuery(
            query_text=query_text.strip(),
            similarity_top_k=capped_limit,
        )
        results = await store.async_search(query)
    except Exception as exc:
        logger.exception(
            "apropose_caml_citation_match: vector search failed for corpus %s",
            corpus_id,
        )
        raise ValueError(
            "Semantic search failed for this corpus. Confirm the corpus has "
            f"an embedder configured and indexed annotations: {exc}"
        )

    candidates: list[dict[str, Any]] = []
    # ``async_search`` already honours ``similarity_top_k`` (we passed
    # ``capped_limit`` above), so the result list is already bounded.
    # ``CoreAnnotationVectorStore`` builds its queryset with
    # ``select_related("annotation_label", "document", "corpus")`` (see
    # ``core_vector_stores.py``), so the per-result attribute reads below do
    # not fan out into N+1 queries.
    for result in results:
        ann = result.annotation
        label = ann.annotation_label  # may be None for label-less annotations
        document = ann.document  # may be None for structural-set annotations
        candidates.append(
            {
                "annotation_id": ann.pk,
                "raw_text": ann.raw_text or "",
                "label_text": label.text if label is not None else None,
                "label_color": label.color if label is not None else None,
                "document_id": ann.document_id,
                "document_title": document.title if document is not None else None,
                "corpus_id": ann.corpus_id,
                "page": ann.page,
                "similarity_score": float(result.similarity_score),
            }
        )

    return candidates


# --------------------------------------------------------------------------- #
# Tool 3 -- apply (approval-gated)                                            #
# --------------------------------------------------------------------------- #


def _apply_caml_article_edit(
    *,
    corpus_id: int,
    author_id: int,
    target_text: str,
    replacement_text: str,
    rationale: str,
) -> dict[str, Any]:
    """Synchronous worker for :func:`aapply_caml_article_edit`."""
    User = get_user_model()
    try:
        user = User.objects.get(pk=author_id)
    except User.DoesNotExist:
        raise ValueError(f"User with id={author_id} does not exist.")

    if not target_text:
        raise ValueError("target_text must be a non-empty string.")

    if target_text == replacement_text:
        raise ValueError(
            "target_text and replacement_text are identical -- no edit to apply."
        )

    doc = _load_caml_document_for_user(corpus_id, user)

    # Wrap the read-check-write in a transaction with a row lock on the
    # current head Document so two simultaneous approval-gated calls can't
    # both observe ``occurrences == 1`` and create racing version-tree
    # siblings off the same parent.  ``select_for_update`` blocks competing
    # writers (including ``import_document``'s own ``select_for_update`` on
    # the corresponding DocumentPath row) until this transaction commits.
    with transaction.atomic():
        # Atomically acquire the lock and re-load the row's current file
        # pointer — a competing writer may have rotated the blob between
        # ``_load_caml_document_for_user`` and this point.
        locked_doc = Document.objects.select_for_update().get(pk=doc.pk)

        # Defense-in-depth: explicit UPDATE check on the CAML document.  The
        # wrapper validates READ on deps.corpus_id, but the CAML article is a
        # separate Document with its own guardian permissions.  ``user_can``
        # honours creator access uniformly (Phase A — issue #1655), so the
        # creator OR-branch the previous shim call needed is folded into the
        # single ``user_can`` call below.  The check runs inside the locked
        # transaction so a permission revocation between the initial load and
        # the write cannot slip through.
        if not locked_doc.user_can(user, PermissionTypes.UPDATE):
            raise ValueError(
                f"User {user.pk} cannot modify the Readme.CAML for corpus {corpus_id}."
            )

        content = _read_caml_content(locked_doc)

        occurrences = content.count(target_text)
        if occurrences == 0:
            raise ValueError(
                "target_text was not found in the Readme.CAML article. "
                "Re-read the article via aread_corpus_caml_article and pass an "
                "exact substring."
            )
        if occurrences > 1:
            raise ValueError(
                f"target_text matches {occurrences} locations in the article. "
                "Provide a longer substring that matches exactly once."
            )

        new_content = content.replace(target_text, replacement_text, 1)

        # Route the write through the canonical dual-tree workhorse
        # ``import_document``.  Each edit creates a new Document at the
        # head of the version_tree sharing ``version_tree_id`` with the
        # locked doc; ``import_document`` atomically flips the old
        # ``Document.is_current`` and old ``DocumentPath.is_current`` to
        # ``False`` and creates a new ``DocumentPath`` (``is_current=True``,
        # ``version_number += 1``).  The old Document remains in the
        # version tree as a historical sibling — its blob is NOT orphaned,
        # so no storage cleanup is needed here.
        #
        # Frontend deep-links to "the corpus's Readme.CAML" resolve to the
        # head of the version_tree via ``corpus.readme_caml_document_id``
        # (the cached FK refreshed by the Document ``post_save`` signal)
        # or by joining ``DocumentPath`` with ``is_current=True`` — they
        # are no longer pinned to a specific Document pk.  See spec
        # ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``
        # §4.1.1 §4.7.
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.versioning import import_document

        # Lock order inside this atomic block: Document (locked above via
        # ``select_for_update``) -> Corpus -> DocumentPath (locked inside
        # ``import_document`` via ``.select_for_update().first()`` — only when
        # the path already exists; the new-document case has no row to lock).
        # Lock the Corpus row too so a concurrent corpus
        # delete, or a ``readme_caml_document_id`` cache refresh, cannot race
        # between the Document lock and ``import_document`` and leave this edit
        # operating on a stale Corpus.
        corpus = Corpus.objects.select_for_update().get(pk=corpus_id)
        new_doc, _status, _path = import_document(
            corpus=corpus,
            path=CAML_ARTICLE_TITLE,
            content=new_content.encode("utf-8"),
            user=user,
            file_type=MARKDOWN_MIME_TYPE,
            title=CAML_ARTICLE_TITLE,
        )

    # The ``select_for_update`` lock is released at transaction commit.
    # ``caml_doc`` is the new head — the freshly-created version-tree
    # sibling, not the now-historical ``locked_doc``.
    caml_doc = new_doc

    # ``refresh_from_db`` is a read; doing it outside the txn keeps the
    # write block free of any post-save operations that could raise.
    caml_doc.refresh_from_db(fields=["modified"])

    pos = content.find(target_text)
    preview_start = max(0, pos - CAML_EDIT_PREVIEW_RADIUS_CHARS)
    preview_end = min(
        len(new_content),
        pos + len(replacement_text) + CAML_EDIT_PREVIEW_RADIUS_CHARS,
    )
    preview_window = new_content[preview_start:preview_end]

    return {
        "corpus_id": corpus_id,
        "document_id": caml_doc.pk,
        "applied": True,
        "target_text": target_text,
        "replacement_text": replacement_text,
        "rationale": rationale,
        "char_offset": pos,
        "preview": preview_window,
        "modified": (caml_doc.modified.isoformat() if caml_doc.modified else None),
    }


async def aapply_caml_article_edit(
    *,
    corpus_id: int,
    author_id: int,
    target_text: str,
    replacement_text: str,
    rationale: str,
) -> dict[str, Any]:
    """Replace a single occurrence of ``target_text`` inside the corpus CAML.

    The only mutating tool in the trio.  ``target_text`` must occur **exactly
    once** in the file -- the call fails closed otherwise so the agent cannot
    silently rewrite the wrong location.  Each call is gated by
    ``requires_approval`` so each replacement triggers an approval prompt
    that surfaces the agent's ``rationale`` and the new content snippet.

    Typical use:
        # 1. read article via aread_corpus_caml_article
        # 2. for a candidate sentence, call apropose_caml_citation_match
        # 3. ask user, then call this tool to add ``{{@cite sentence}}``

    Args:
        corpus_id: Corpus owning the ``Readme.CAML`` article (injected).
        author_id: User performing the edit (injected) -- must be the
            document creator, a superuser, or have explicit guardian UPDATE
            on the CAML document.
        target_text: Exact substring to replace.  Must occur exactly once.
        replacement_text: Replacement content (typically the original
            sentence plus an inline ``{{@cite ...}}`` directive).
        rationale: Short explanation surfaced in the approval modal so the
            user understands why the edit was proposed.

    Returns:
        Dict describing the applied edit (offset, preview window, new
        ``modified`` timestamp).
    """
    return await _db_sync_to_async(_apply_caml_article_edit)(
        corpus_id=corpus_id,
        author_id=author_id,
        target_text=target_text,
        replacement_text=replacement_text,
        rationale=rationale,
    )
