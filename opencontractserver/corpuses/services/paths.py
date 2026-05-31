"""DocumentPath disambiguation internals for the corpus service layer.

``CorpusPathService`` holds the low-level :class:`DocumentPath` path
manipulation helpers used by the folder write operations when documents are
moved between folders or displaced by a folder deletion. Every method here is
an internal helper (underscore-prefixed): the path layer performs NO
permission checks — callers gate corpus permissions *before* reaching these
helpers.

Split out of the former ``corpus_objs_service.py`` monolith — see
``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``
(issue #1716, service-layer centralization Phase 2).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.db.models.signals import post_save

from opencontractserver.constants.document_processing import (
    MAX_PATH_CREATE_RETRIES,
    MAX_PATH_DISAMBIGUATION_SUFFIX,
    PATH_CONFLICT_MSG,
)
from opencontractserver.shared.services.base import BaseService

if TYPE_CHECKING:
    from opencontractserver.corpuses.models import Corpus, CorpusFolder
    from opencontractserver.documents.models import DocumentPath
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)


class CorpusPathService(BaseService):
    """Low-level :class:`DocumentPath` disambiguation helpers.

    All methods are internal helpers (underscore-prefixed) shared by the
    folder write operations in
    :class:`~opencontractserver.corpuses.services.folders.FolderCRUDService`
    and
    :class:`~opencontractserver.corpuses.services.folder_documents.FolderDocumentService`.
    They perform NO permission checks — the calling service is responsible
    for gating corpus permissions first.
    """

    @staticmethod
    def _compute_moved_path(
        current_path: str,
        target_folder: CorpusFolder | None,
        target_folder_path: str | None = None,
    ) -> str:
        """
        Compute the new path string when moving a document to a different folder.

        Extracts the **filename only** (last segment after the final ``/``) from
        the current path and prepends the target folder's path, or places at root
        if ``target_folder`` is ``None``.  All intermediate directory segments
        from the original path are intentionally dropped — the new path is
        derived entirely from the target folder's tree position.

        Examples::

            _compute_moved_path("/old/dir/report.pdf", folder_with_path_Legal)
            # => "/Legal/report.pdf"  (intermediate "old/dir" dropped)

            _compute_moved_path("/report.pdf", None)
            # => "/report.pdf"  (root placement)

        Args:
            current_path: Current DocumentPath.path value (e.g. "/documents/report.pdf")
            target_folder: Target folder (None = corpus root)
            target_folder_path: Pre-computed value of ``target_folder.get_path()``.
                Pass this when invoking the method many times for the same target
                folder (e.g. inside a bulk move loop) to avoid repeated O(depth)
                ancestor traversals — ``get_path()`` issues a recursive CTE
                query on every call.  Ignored when ``target_folder`` is ``None``.
                When ``None`` (the default), the path is computed on demand via
                ``target_folder.get_path()``.  Only ``None`` triggers the
                fallback — any other value (including empty string) is used
                as-is.  The value need not be pre-stripped of leading/trailing
                slashes — ``.strip("/")`` is applied internally.

        Returns:
            New path string (e.g. "/Legal/report.pdf" or "/report.pdf")
        """
        # Guard against empty, whitespace-only, or root-only paths early.
        if not current_path or not current_path.strip() or current_path.strip() == "/":
            raise ValueError(
                f"Cannot extract filename from path {current_path!r} — "
                f"empty or root-only paths are not supported"
            )

        # Extract filename (last segment of path)
        filename = (
            current_path.rsplit("/", 1)[-1] if "/" in current_path else current_path
        )

        # Secondary guard: the rsplit may produce an empty filename for paths
        # like "/dir/" (trailing slash).
        if not filename:
            raise ValueError(
                f"Cannot extract filename from path {current_path!r} — "
                f"empty or root-only paths are not supported"
            )

        if target_folder:
            folder_path = (
                target_folder.get_path()
                if target_folder_path is None
                else target_folder_path
            ).strip("/")
            return f"/{folder_path}/{filename}"
        else:
            return f"/{filename}"

    @staticmethod
    def _target_directory_string_from_path(
        folder_path: str | None,
    ) -> str:
        """
        Return a canonical directory string from a folder path string.

        Normalises the path by stripping leading/trailing slashes and
        wrapping with ``/prefix/`` format, matching the format that
        ``_fetch_occupied_paths_in_directory`` expects.

        - ``None`` (root) → ``"/"``
        - ``"Legal/Contracts"`` → ``"/Legal/Contracts/"``
        """
        if folder_path is None:
            return "/"
        # Normalise "/" (the root-equivalent path string that
        # ``CorpusFolder.get_path()`` may return for a root folder) to the
        # canonical root directory rather than raising — callers should
        # not need to know that ``None`` is the internal root sentinel.
        if folder_path == "/":
            return "/"
        stripped = folder_path.strip("/")
        if not stripped:
            raise ValueError(
                "_target_directory_string_from_path: folder_path is empty "
                f"after stripping slashes (original: {folder_path!r})"
            )
        return f"/{stripped}/"

    @classmethod
    def reconcile_paths_after_folder_change(
        cls,
        *,
        corpus: Corpus,
        root_folder: CorpusFolder,
        old_root_path: str,
        user: User,
    ) -> int:
        """Rewrite stored ``DocumentPath.path`` strings after a folder rename/move.

        Folder rename (``update_folder``) and folder move (``move_folder``)
        change a folder's position in the tree — and therefore the value of
        ``folder.get_path()`` — but historically left the ``path`` strings of
        the documents inside the folder (and its descendants) untouched. Because
        document *moves* derive ``path`` from ``folder.get_path()``
        (:meth:`_compute_moved_path`), a folder rename made the two drift out of
        sync: a document moved into ``/Legal/x.pdf`` kept that stale path after
        ``Legal`` was renamed to ``Contracts``.

        This reconciler closes that gap. For every **folder-derived** active
        path under ``root_folder`` and its descendants — i.e. paths that
        currently equal ``/<old folder path>/<filename>`` — it rewrites the
        directory prefix to the folder's new path, creating immutable MOVED
        history nodes via the same batch machinery as
        :meth:`FolderDocumentService.move_documents_to_folder` (deactivate +
        ``bulk_create`` + manual ``post_save`` dispatch).

        Paths that are **not** folder-derived (e.g. the ``/documents/<title>``
        default an upload assigns regardless of folder) are intentionally left
        untouched: they never reflected the folder location, so a rename does
        not make them any more stale. This keeps the change minimal and
        collision-free (source and target directories are disjoint because the
        root path string actually changed).

        **Caller contract**: must run inside the SAME ``transaction.atomic()``
        block that performed the folder mutation, AFTER ``root_folder`` has been
        saved with its new name/parent (so ``get_path()`` returns the new
        value). ``old_root_path`` is ``root_folder.get_path()`` captured BEFORE
        the mutation. No permission check — the calling service gates corpus
        UPDATE first.

        Args:
            corpus: The corpus owning the folder and its documents.
            root_folder: The folder that was renamed or moved (already saved).
            old_root_path: ``root_folder.get_path()`` as it was before the change.
            user: User performing the operation (creator of the new path nodes).

        Returns:
            Number of DocumentPath rows rewritten (0 if nothing drifted).
        """
        from opencontractserver.documents.models import DocumentPath

        new_root_path = root_folder.get_path()
        if old_root_path == new_root_path:
            return 0

        # Every folder in the moved/renamed subtree (includes the root itself).
        affected_folders = list(root_folder.get_descendant_folders())
        folder_by_id = {f.id: f for f in affected_folders}
        new_path_by_folder = {f.id: f.get_path() for f in affected_folders}
        # A descendant's path is ``new_root_path`` + a stable suffix (names
        # below the root did not change), so its OLD path is the same suffix
        # appended to ``old_root_path``.
        old_path_by_folder = {
            fid: old_root_path + npath[len(new_root_path) :]
            for fid, npath in new_path_by_folder.items()
        }

        current_paths = list(
            DocumentPath.objects.select_for_update(of=("self",))
            .filter(
                folder__in=affected_folders,
                corpus=corpus,
                is_current=True,
                is_deleted=False,
            )
            .order_by("pk")
        )

        occupied_by_dir: dict[str, set[str]] = {}
        planned: list[tuple[DocumentPath, str]] = []
        for dp in current_paths:
            # ``CorpusFolder.get_path()`` joins folder names with "/" and never
            # returns a leading slash, so wrapping it in slashes yields a clean
            # "/<folder path>/" prefix (no "//<...>" double-slash that would
            # silently match nothing and turn reconciliation into a no-op).
            old_prefix = f"/{old_path_by_folder[dp.folder_id]}/"
            if not dp.path.startswith(old_prefix):
                # Not folder-derived (e.g. "/documents/<title>") — leave as-is.
                continue
            new_folder_path = new_path_by_folder[dp.folder_id]
            # Pass the already-loaded folder + its path so _compute_moved_path
            # neither hits the DB (no folder FK fetch) nor runs an ancestor CTE.
            new_candidate = cls._compute_moved_path(
                dp.path,
                folder_by_id[dp.folder_id],
                target_folder_path=new_folder_path,
            )
            target_dir = cls._target_directory_string_from_path(new_folder_path)
            if target_dir not in occupied_by_dir:
                occupied_by_dir[target_dir] = cls._fetch_occupied_paths_in_directory(
                    corpus, target_dir
                )
            occupied = occupied_by_dir[target_dir]
            new_candidate = cls.disambiguate_path(
                new_candidate, corpus, occupied_override=occupied
            )
            occupied.add(new_candidate)
            planned.append((dp, new_candidate))

        if not planned:
            return 0

        old_pks = [dp.pk for dp, _ in planned]
        DocumentPath.objects.filter(pk__in=old_pks).update(is_current=False)

        new_rows = [
            DocumentPath(
                document_id=dp.document_id,
                corpus=corpus,
                folder_id=dp.folder_id,
                path=new_path,
                version_number=dp.version_number,
                parent=dp,
                is_current=True,
                is_deleted=False,
                creator=user,
            )
            for dp, new_path in planned
        ]
        created = DocumentPath.objects.bulk_create(new_rows)
        cls._dispatch_document_path_created_signals(created)

        logger.info(
            "Reconciled %d document path(s) under folder %s in corpus %s "
            "after move/rename (%r -> %r)",
            len(created),
            root_folder.id,
            corpus.id,
            old_root_path,
            new_root_path,
        )
        return len(created)

    @staticmethod
    def _dispatch_document_path_created_signals(
        paths: list[DocumentPath],
    ) -> None:
        """
        Manually dispatch ``post_save`` (``created=True``) for rows created via
        :meth:`DocumentPath.objects.bulk_create`.

        ``bulk_create`` bypasses per-row ``pre_save``/``post_save`` signal
        delivery, which would silently drop the document-text embedding
        side-effect wired up in
        ``documents.signals.process_doc_on_document_path_create``.  Bulk
        write paths replicate the single-row semantics by sending the signal
        themselves after the INSERT.

        Note: only ``post_save`` is replayed here. ``pre_save`` is still
        skipped — consistent with ``bulk_create``'s own contract and
        acceptable today because ``DocumentPath`` has no registered
        ``pre_save`` receivers. If a ``pre_save`` receiver is added in the
        future (e.g. to auto-populate a field or stamp a timestamp), this
        method must be extended to dispatch it before the INSERT rather
        than after.

        Args:
            paths: DocumentPath instances returned by ``bulk_create``.
        """
        # Nested import to avoid circular dependency during app initialization.
        from opencontractserver.documents.models import DocumentPath

        # All kwargs match what Django's ``Model.save()`` dispatches for a
        # newly created instance: ``created=True``, ``update_fields=None``,
        # ``raw=False``, and the actual database alias from ``_state.db``.
        # Passing ``update_fields`` explicitly (rather than omitting it)
        # ensures future signal handlers that declare it as an explicit
        # keyword argument won't raise ``TypeError``.
        for path in paths:
            post_save.send(
                sender=DocumentPath,
                instance=path,
                created=True,
                update_fields=None,
                raw=False,
                using=path._state.db,
            )

    @staticmethod
    def _fetch_occupied_paths_in_directory(
        corpus: Corpus,
        directory: str,
        exclude_pk: int | None = None,
    ) -> set[str]:
        """
        Fetch the set of occupied active-path strings in a single directory.

        Performs a **single** SQL query that matches immediate children of
        ``directory`` only (not nested subdirectories).  Used both by the
        single-doc disambiguation fast path and by batch operations that
        need to pre-fetch the entire target directory once, instead of
        once per document.

        Args:
            corpus: Corpus to query.
            directory: Directory string terminated by ``/`` (e.g. ``/Target/``
                       for folder ``Target``, or ``/`` for corpus root). An
                       empty string raises ``ValueError`` to surface caller
                       bugs that would otherwise trigger a full-table scan.
            exclude_pk: Optional DocumentPath PK to exclude from the result
                        (e.g. the record being superseded by a single move).

        Returns:
            Set of path strings currently occupied in ``directory``.
        """
        # Nested import to avoid circular dependency:
        # paths -> documents.models -> corpuses.models -> services
        from opencontractserver.documents.models import DocumentPath

        qs = DocumentPath.objects.filter(
            corpus=corpus,
            is_current=True,
            is_deleted=False,
        )
        # Special-case root-level paths: for directory="/", path__startswith="/"
        # would match EVERY active path in the corpus.  Instead, use a regex
        # that only matches single-segment root paths (e.g. "/report.pdf"
        # but not "/folder/report.pdf").
        #
        # NOTE: These regex filters cannot use a btree index on ``path``
        # (PostgreSQL requires anchored patterns with no alternation for
        # index-only scans).  For typical corpus sizes this is fine, but
        # corpuses with thousands of files at the same directory level may
        # benefit from a GIN/pg_trgm index or a rewrite using
        # ``path__startswith`` + a slash-count annotation.
        # TODO(perf, #1199 follow-up): file a dedicated issue if this regex
        # scan shows up in profiling on large directories before adding an
        # index — the btree on ``path`` is still useful for exact-match
        # lookups and we don't want to regress write throughput.
        if directory == "/":
            qs = qs.filter(path__regex=r"^/[^/]+$")
        elif directory:
            # Match only immediate children (not nested subdirectories)
            # to avoid pulling the entire subtree into memory.
            qs = qs.filter(path__regex=rf"^{re.escape(directory)}[^/]+$")
        else:
            # directory == "" means base_path had no leading slash — structurally
            # unexpected since all stored paths start with "/".  Raise rather
            # than silently loading ALL active paths, which would mask a bug
            # in the caller and degrade performance on large corpuses.
            raise ValueError(
                f"_fetch_occupied_paths_in_directory: empty directory "
                f"for corpus {corpus.id}"
            )
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return set(qs.values_list("path", flat=True))

    @classmethod
    def disambiguate_path(
        cls,
        base_path: str,
        corpus: Corpus,
        exclude_pk: int | None = None,
        occupied_override: set[str] | None = None,
        extra_occupied: set[str] | None = None,
    ) -> str:
        """
        Generate a unique path by appending numeric suffixes when a conflict exists.

        Given a base path like ``/Target/report.pdf``, this checks for existing
        active (``is_current=True, is_deleted=False``) DocumentPath records in the
        same corpus. If the base path is taken it tries ``/Target/report_1.pdf``,
        ``/Target/report_2.pdf``, etc. until an unused path is found.

        A hard cap (``MAX_PATH_DISAMBIGUATION_SUFFIX``) prevents unbounded loops
        if many documents share the same filename in the same folder.

        **Performance**: Uses a single query (via
        :meth:`_fetch_occupied_paths_in_directory`) to pre-fetch all occupied
        paths in the target directory, then checks candidates in memory
        (O(1) per candidate instead of O(1)-per-query).  Bulk operations may
        pass ``occupied_override`` to skip the per-call query entirely and
        share a single pre-fetched set across many disambiguations.

        **Concurrency note**: The caller's ``select_for_update()`` only prevents
        two concurrent moves of the **same** document from racing.  It does NOT
        lock target-path rows — two concurrent moves of **different** documents
        to the same target folder can both observe a candidate path as free and
        race to create it.  The database's ``unique_active_path_per_corpus``
        partial unique constraint is the real safety net: the loser's ``INSERT``
        raises ``IntegrityError``, which callers handle via savepoints.

        Args:
            base_path: The ideal path string to use.
            corpus: Corpus to check for conflicts in.
            exclude_pk: Optional DocumentPath PK to exclude from conflict check
                        (the record being superseded).  Ignored when
                        ``occupied_override`` is provided — the caller is
                        responsible for filtering their own pre-fetched set.
            occupied_override: Optional pre-fetched set of occupied paths.  When
                               provided, the per-call DB query is skipped and
                               this set is used as the authoritative occupancy
                               snapshot.  Callers in bulk operations pass a
                               shared **mutable** set and append each
                               disambiguated result to it so subsequent
                               disambiguations see the within-batch claim.
            extra_occupied: Optional set of additional paths to treat as
                           occupied. Now used only by the single-document
                           retry loop in
                           :meth:`_create_successor_path_with_retry` to
                           mark paths claimed by prior failed attempts
                           within that same call; bulk callers should use
                           ``occupied_override`` instead. Merged into the
                           DB-queried set; ignored when
                           ``occupied_override`` is provided.

        Returns:
            A path string unique among active paths in the corpus (and the
            ``occupied_override`` set, if provided) *at query time*.  This is a
            best-effort check — concurrent transactions may claim the same
            path between the SELECT and INSERT (TOCTOU race).  The database's
            ``unique_active_path_per_corpus`` partial unique constraint is the
            authoritative guarantee of uniqueness; callers must handle
            ``IntegrityError`` for the rare conflict case.

        Raises:
            ValueError: If ``base_path`` lacks a leading ``/``, or if no unique
                path can be found within the suffix limit.
        """
        # All stored DocumentPath.path values start with "/".  Reject
        # slashless paths early with a clear message rather than letting
        # them propagate to _fetch_occupied_paths_in_directory where the
        # resulting empty-directory ValueError is harder to diagnose.
        if not base_path.startswith("/"):
            raise ValueError(
                f"disambiguate_path: base_path must start with '/' "
                f"(got {base_path!r})"
            )

        if occupied_override is not None:
            # Caller pre-fetched the occupied set — skip the DB query entirely.
            # This is the hot path for bulk operations which share a single
            # fetch across N disambiguations.
            #
            # ``occupied_override`` is treated as read-only inside this method;
            # callers are responsible for appending the returned path to the
            # set after this method returns.
            occupied = occupied_override
        else:
            # Derive the directory once so that both the fetch and the candidate
            # loop agree on which namespace we're searching.  The leading-slash
            # guard above guarantees "/" is present, so rsplit always produces a
            # non-empty directory prefix (at worst "/" for root-level paths).
            directory = base_path.rsplit("/", 1)[0] + "/"

            occupied = cls._fetch_occupied_paths_in_directory(
                corpus, directory, exclude_pk=exclude_pk
            )

            # Merge in any extra occupied paths (e.g. from within-batch claims
            # during retry loops)
            if extra_occupied:
                occupied = occupied | extra_occupied

        if base_path not in occupied:
            return base_path

        # Split into stem and extension for suffix insertion.
        # We must split the *filename* segment, not the full path, so that
        # dotfiles like ".gitignore" are handled correctly (the leading dot
        # is NOT an extension separator).
        if "/" in base_path:
            dir_part, filename = base_path.rsplit("/", 1)
        else:
            dir_part, filename = None, base_path

        # Determine whether the filename has a true extension.
        # A leading dot (e.g. ".gitignore") is not an extension separator;
        # strip it before checking, then re-prepend after the split.
        bare = filename.lstrip(".")
        leading_dots = filename[: len(filename) - len(bare)]

        def _join_stem(name_part: str) -> str:
            return f"{dir_part}/{name_part}" if dir_part is not None else name_part

        if "." in bare:
            name_stem, name_ext = bare.rsplit(".", 1)
            stem = _join_stem(f"{leading_dots}{name_stem}")
            ext = f".{name_ext}"
        else:
            stem = _join_stem(filename)
            ext = ""

        for counter in range(1, MAX_PATH_DISAMBIGUATION_SUFFIX + 1):
            candidate = f"{stem}_{counter}{ext}"
            if candidate not in occupied:
                log_prefix = (
                    f"Within-batch {PATH_CONFLICT_MSG.lower()}"
                    if occupied_override is not None or extra_occupied
                    else PATH_CONFLICT_MSG
                )
                logger.warning(
                    "%s for %r in corpus %s — disambiguated to %r",
                    log_prefix,
                    base_path,
                    corpus.id,
                    candidate,
                )
                return candidate

        logger.error(
            "Path disambiguation exhausted for %r in corpus %s after %d attempts",
            base_path,
            corpus.id,
            MAX_PATH_DISAMBIGUATION_SUFFIX,
        )
        raise ValueError(
            f"Cannot find a unique path for {base_path!r} in corpus {corpus.id} "
            f"after {MAX_PATH_DISAMBIGUATION_SUFFIX} attempts"
        )

    @classmethod
    def _create_successor_path_with_retry(
        cls,
        *,
        current: DocumentPath,
        corpus: Corpus,
        folder: CorpusFolder | None,
        base_path: str,
        user: User,
        extra_occupied: set[str] | None = None,
    ) -> tuple[DocumentPath, str]:
        """
        Atomically deactivate ``current`` and create a successor DocumentPath,
        retrying on ``IntegrityError`` from the ``unique_active_path_per_corpus``
        partial unique constraint.

        This is the TOCTOU race recovery layer for path uniqueness:
        ``disambiguate_path`` checks for occupied paths at query time, but a
        concurrent transaction can claim the same path between the SELECT and
        the INSERT.  Each retry runs:

        1. ``disambiguate_path`` to choose a free path (treating any
           previously-lost paths as occupied)
        2. A nested ``transaction.atomic()`` savepoint
        3. ``current.is_current = False`` save
        4. ``DocumentPath.objects.create(...)`` for the successor

        On ``IntegrityError`` the savepoint is rolled back (so ``current``
        remains the active path in the DB), the losing path is added to the
        in-memory occupied set, and the loop tries again with a fresh
        disambiguation.

        After ``MAX_PATH_CREATE_RETRIES`` consecutive failures the most
        recent ``IntegrityError`` is re-raised so the caller can roll back
        the outer transaction.

        **Caller contract**: must already be inside an outer
        ``transaction.atomic()`` block that holds a ``select_for_update``
        lock on ``current``.  The lock prevents two callers from racing on
        the *same* document; this helper only handles races on the *target
        path slot* (different documents racing for the same filename).

        Args:
            current: Currently active DocumentPath being superseded.
            corpus: Owning corpus (must equal ``current.corpus``).
            folder: Target folder for the successor (None = corpus root).
            base_path: Initial proposed path; disambiguated each attempt.
            user: User performing the operation (set as creator).
            extra_occupied: Optional set of paths already claimed by earlier
                items in a batch operation; merged into the in-memory
                occupied set on every disambiguation.

        Returns:
            ``(new_path_record, chosen_path_string)`` — the path string may
            differ from ``base_path`` after disambiguation/retries.

        Raises:
            ValueError: If ``disambiguate_path`` exhausts its suffix cap.
            IntegrityError: If ``MAX_PATH_CREATE_RETRIES`` consecutive
                INSERT attempts all lose the race.
        """
        # Deferred to break circular import (documents -> corpuses -> documents).
        from opencontractserver.documents.models import DocumentPath

        # Track paths we've attempted unsuccessfully so disambiguation
        # avoids them on subsequent retries within the same call.
        occupied_after_loss: set[str] = set(extra_occupied or ())
        last_exc: IntegrityError | None = None

        for attempt in range(MAX_PATH_CREATE_RETRIES + 1):
            new_path = cls.disambiguate_path(
                base_path,
                corpus,
                exclude_pk=current.pk,
                extra_occupied=occupied_after_loss,
            )
            try:
                # Savepoint: both the deactivation and the create must
                # succeed together, or neither commits.  An IntegrityError
                # rolls back the savepoint without poisoning the outer
                # transaction, allowing retry.
                with transaction.atomic():
                    current.is_current = False
                    current.save(update_fields=["is_current"])

                    new_record = DocumentPath.objects.create(
                        document=current.document,
                        corpus=corpus,
                        folder=folder,
                        path=new_path,
                        version_number=current.version_number,
                        parent=current,
                        is_current=True,
                        is_deleted=False,
                        creator=user,
                    )
                    return new_record, new_path
            except IntegrityError as exc:
                # Only retry for the specific partial-unique constraint;
                # other IntegrityErrors (null, FK) are real bugs and
                # should not be retried.
                #
                # Guard order: first check the psycopg2 pgcode so we only
                # inspect the error message for UniqueViolation errors
                # (pgcode 23505); then confirm the constraint name.  This
                # avoids retrying on unrelated IntegrityErrors that happen
                # to contain the constraint name as a substring, and also
                # avoids matching on non-English Postgres error messages.
                cause = getattr(exc, "__cause__", None)
                pgcode = getattr(cause, "pgcode", None)
                if pgcode != "23505" or "unique_active_path_per_corpus" not in str(exc):
                    raise
                last_exc = exc
                occupied_after_loss.add(new_path)
                # The savepoint rollback restored ``current.is_current=True``
                # in the database, but the in-memory attribute still reflects
                # the unsaved write.  Reset it so the next iteration's save()
                # actually writes ``False`` again.
                current.is_current = True
                logger.warning(
                    "IntegrityError on attempt %d/%d creating path %r for "
                    "document %s in corpus %s — concurrent path conflict, "
                    "retrying with fresh disambiguation: %s",
                    attempt + 1,
                    MAX_PATH_CREATE_RETRIES + 1,
                    new_path,
                    current.document_id,
                    corpus.id,
                    exc,
                )

        logger.error(
            "DocumentPath creation failed after %d retries for document %s "
            "in corpus %s — concurrent path conflicts could not be resolved",
            MAX_PATH_CREATE_RETRIES + 1,
            current.document_id,
            corpus.id,
        )
        # last_exc is guaranteed non-None here: the loop runs at least once
        # and only exits via return-on-success or via the except block which
        # always sets last_exc.  Guard defensively so ``python -O`` doesn't
        # silently turn this into ``raise None``.
        if last_exc is None:
            raise RuntimeError(
                "Unreachable: retry loop exited without setting last_exc"
            )
        raise last_exc
