"""Write generated artifacts into a user's personal ``My Documents`` workspace.

Every user already owns a personal corpus (``Corpus.is_personal``, provisioned
by the ``User`` ``post_save`` signal), and the document layer already knows how
to version a write (``documents.versioning.import_document``). What was missing
is a way for *generated* content — a finished research report, and later a CAML
article or an extract summary — to land there.

This service binds those primitives and nothing more. It deliberately does not
move, delete, rename or list: the workspace is an ordinary corpus, so
``CorpusService`` / ``FolderCRUDService`` / ``DocumentLifecycleService`` already
own those operations. Adding them here would duplicate a permission surface
that is already correct elsewhere.

Note that markdown documents skip the ingestion pipeline entirely (see
``documents/signals.py``): no parsing, thumbnailing or embedding. Saving is
therefore essentially free, and the saved file is a readable, versioned
artifact rather than something vector search or agent retrieval will surface.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from django.db import transaction

from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.shared.services.base import BaseService

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)

# Characters a path segment must not contain. ``import_document`` splits on
# "/", so a title carrying one would silently invent a folder level.
_UNSAFE_PATH_CHARS = re.compile(r"[/\\\x00-\x1f]+")

# Bounded so a runaway generated title cannot exceed the ``DocumentPath.path``
# column or produce an unreadable filename.
MAX_WORKSPACE_FILENAME_CHARS = 120


def _safe_segment(value: str, *, fallback: str) -> str:
    """Reduce arbitrary generated text to one safe path segment.

    Titles reaching here are model-generated, so they are untrusted input.
    Stripping separators is what stops a title inventing a folder level, but it
    is not sufficient on its own: these paths are also written verbatim into
    corpus V2 export ZIPs, where a surviving ``..`` becomes a zip-slip vector
    for whoever extracts the archive. Dot runs are collapsed and leading dots
    dropped so no segment can ever read as a traversal, while ordinary dotted
    names (``v1.2 report``) are preserved.
    """
    cleaned = _UNSAFE_PATH_CHARS.sub(" ", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = cleaned.strip(". ")
    if not cleaned:
        return fallback
    return cleaned[:MAX_WORKSPACE_FILENAME_CHARS].strip(". ") or fallback


class WorkspaceService(BaseService):
    """Put generated artifacts in the requesting user's personal corpus."""

    @classmethod
    def save_markdown(
        cls,
        *,
        user: Any,
        title: str,
        content: str,
        folder_name: str | None = None,
        filename_stem: str | None = None,
    ) -> Document:
        """Write ``content`` into ``user``'s workspace as a markdown document.

        Idempotent **by path**: saving the same ``filename_stem`` into the same
        folder again versions the existing document in place rather than
        creating a second one — ``import_document`` bumps ``version_number``,
        flips the prior ``Document.is_current`` / ``DocumentPath.is_current`` to
        false, and leaves the old text retrievable in the version tree.

        Args:
            user: Owner of the workspace and creator of the document.
            title: Human-readable document title.
            content: Markdown body.
            folder_name: Optional root-level folder; created on first use.
                Generated artifacts should pass one so they do not bury the
                user's own uploads in the corpus root.
            filename_stem: Stable name for the file, minus the ``.md``
                extension. Defaults to ``title``. Pass a slug when the title
                may change between saves but the file should stay put — the
                path is the idempotency key, so a drifting name creates a new
                document instead of a new version.

        Returns:
            The head ``Document`` for the written path.
        """
        from opencontractserver.corpuses.models import Corpus, CorpusFolder
        from opencontractserver.documents.versioning import import_document

        stem = _safe_segment(filename_stem or title, fallback="untitled")
        safe_title = _safe_segment(title, fallback=stem)

        with transaction.atomic():
            corpus = Corpus.get_or_create_personal_corpus(user)

            folder = None
            path_prefix = ""
            if folder_name:
                safe_folder = _safe_segment(folder_name, fallback="Generated")
                # get_or_create rather than create: two artifacts finishing at
                # once must not race into duplicate folders of the same name.
                folder, _created = CorpusFolder.objects.get_or_create(
                    corpus=corpus,
                    parent=None,
                    name=safe_folder,
                    defaults={"creator": user},
                )
                path_prefix = f"{safe_folder}/"

            document, status, _path = import_document(
                corpus=corpus,
                path=f"{path_prefix}{stem}.md",
                content=content.encode("utf-8"),
                user=user,
                folder=folder,
                file_type=MARKDOWN_MIME_TYPE,
                title=safe_title,
            )

        logger.info(
            "Saved markdown %r to workspace corpus %s for user %s (document %s, %s)",
            f"{path_prefix}{stem}.md",
            corpus.pk,
            getattr(user, "pk", None),
            document.pk,
            status,
        )
        return document


__all__ = ["WorkspaceService", "MAX_WORKSPACE_FILENAME_CHARS"]
