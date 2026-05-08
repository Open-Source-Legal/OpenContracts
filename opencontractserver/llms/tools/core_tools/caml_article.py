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

All three tools use the existing ``visible_to_user`` / ``user_has_permission_for_obj``
patterns documented in ``docs/permissioning/consolidated_permissioning_guide.md``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import user_has_permission_for_obj

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)


# Title used for the corpus-level CAML article.  Must stay in sync with the
# frontend constant ``CAML_ARTICLE_FILENAME`` declared in
# ``frontend/src/assets/configurations/constants.ts``.
CAML_ARTICLE_TITLE = "Readme.CAML"

# Mirror of ``DIRECTIVE_PATTERN_GLOBAL`` from
# ``frontend/src/components/corpuses/caml/inlineDirectives.ts`` so backend
# parsing matches what the renderer extracts.
_DIRECTIVE_PATTERN = re.compile(
    r"\{\{@(\w+)\s+(sentence|paragraph|block)(?:\s+([^}]+?))?\}\}"
)
_DIRECTIVE_ARG_PATTERN = re.compile(r'(\w+)=(?:"([^"]+)"|(\S+))')

# Cap on candidates returned by ``apropose_caml_citation_match`` -- keeps the
# tool output bounded regardless of what the LLM passes for ``limit``.
_MAX_CITATION_CANDIDATES = 25

# Window of surrounding text returned in ``apply``'s preview so the approval
# modal can show "before/after" context without dumping the whole document.
_PREVIEW_RADIUS_CHARS = 80


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
    rows, and embedded component markers so the candidate list stays focused
    on paragraphs the user would actually want to cite.
    """
    stripped = text.strip()
    if not stripped:
        return False
    first = stripped[:1]
    if first in {"#", "-", "*", ">", "|"}:
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

    Uses ``Corpus.get_documents(include_caml=True)`` to follow the same
    DocumentPath-based lookup the frontend's article query uses, then
    intersects with ``Document.objects.visible_to_user`` for IDOR-safe access.
    Raises ``ValueError`` with a single error string for both
    "corpus does not exist" and "user lacks permission" so the message cannot
    be used for enumeration.
    """
    from opencontractserver.corpuses.models import Corpus

    not_found = (
        f"Corpus id={corpus_id} has no Readme.CAML article visible to this user."
    )

    try:
        corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_id)
    except Corpus.DoesNotExist:
        raise ValueError(not_found)

    caml_ids = list(
        corpus.get_documents(include_caml=True)
        .filter(title=CAML_ARTICLE_TITLE, file_type=MARKDOWN_MIME_TYPE)
        .values_list("id", flat=True)
    )
    if not caml_ids:
        raise ValueError(not_found)

    # ``corpus.get_documents(include_caml=True)`` already filters via the
    # ``DocumentPath.is_current=True`` join (see CorpusType.get_documents),
    # so the second query just intersects ``caml_ids`` with documents the
    # user can read — IDOR-safe two-query pattern.
    doc = Document.objects.visible_to_user(user).filter(pk__in=caml_ids).first()
    if doc is None:
        raise ValueError(not_found)
    return doc


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
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


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

    # NOTE: Corpus-visibility is *not* enforced inside this function.  The tool
    # is registered with ``requires_corpus=True`` so the wrapper validates that
    # ``corpus_id`` is visible to ``author_id`` before dispatch; results are
    # additionally scoped by the vector store's ``user_id`` filter, which
    # honours ``Annotation.objects.visible_to_user`` semantics.  If this tool
    # is ever invoked outside the wrapper, add an explicit ``Corpus.objects
    # .visible_to_user(user).get(pk=corpus_id)`` check here.
    capped_limit = max(1, min(int(limit), _MAX_CITATION_CANDIDATES))

    store = CoreAnnotationVectorStore(
        user_id=author_id,
        corpus_id=corpus_id,
    )
    query = VectorSearchQuery(
        query_text=query_text.strip(),
        similarity_top_k=capped_limit,
    )
    try:
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
    for result in results[:capped_limit]:
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

    # Defense-in-depth: explicit UPDATE check on the CAML document.  The
    # wrapper validates READ on deps.corpus_id, but the CAML article is a
    # separate Document with its own guardian permissions -- creator access
    # is honoured here (user_has_permission_for_obj does not consider it for
    # documents, see its docstring).
    if not (
        user.is_superuser
        or doc.creator_id == user.id
        or user_has_permission_for_obj(user, doc, PermissionTypes.UPDATE)
    ):
        raise ValueError(
            f"User {user.id} cannot modify the Readme.CAML for corpus {corpus_id}."
        )

    # Wrap the read-check-write in a transaction with a row lock on the
    # Document so two simultaneous approval-gated calls can't both observe
    # ``occurrences == 1`` and clobber each other's edit.  ``select_for_update``
    # blocks competing writers until this transaction commits.
    with transaction.atomic():
        Document.objects.select_for_update().filter(pk=doc.pk).first()
        # Refresh the row's file pointer in case another writer rotated the
        # blob between the original load and the lock acquisition.
        doc.refresh_from_db()

        content = _read_caml_content(doc)

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

        # Persist via FileField.save which writes the new file blob and bumps
        # ``Document.modified`` automatically.  We keep the same Document row so
        # frontend deep-links to ``Readme.CAML`` continue to work (no new
        # version_tree entry).
        file_name = doc.txt_extract_file.name or ""
        filename = file_name.rsplit("/", 1)[-1] or "Readme.CAML.md"
        doc.txt_extract_file.save(filename, ContentFile(new_content.encode("utf-8")))
        doc.refresh_from_db(fields=["modified"])

    pos = content.find(target_text)
    preview_start = max(0, pos - _PREVIEW_RADIUS_CHARS)
    preview_end = min(
        len(new_content), pos + len(replacement_text) + _PREVIEW_RADIUS_CHARS
    )
    preview_window = new_content[preview_start:preview_end]

    return {
        "corpus_id": corpus_id,
        "document_id": doc.pk,
        "applied": True,
        "target_text": target_text,
        "replacement_text": replacement_text,
        "rationale": rationale,
        "char_offset": pos,
        "preview": preview_window,
        "modified": doc.modified.isoformat() if doc.modified else None,
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
