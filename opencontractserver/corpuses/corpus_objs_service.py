"""Backward-compatible shim for the corpus service layer.

``corpus_objs_service.py`` was a ~2,900-line monolith holding six distinct
responsibilities in a single ``CorpusObjsService`` class. As of issue #1716
(service-layer centralization, Phase 2) it has been split into the segmented
:mod:`opencontractserver.corpuses.services` package:

- :class:`~opencontractserver.corpuses.services.folders.FolderCRUDService`
  — folder CRUD, the folder tree, search, and bulk structure creation.
- :class:`~opencontractserver.corpuses.services.folder_documents.FolderDocumentService`
  — document-in-folder placement, listing, and counts.
- :class:`~opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService`
  — document-in-corpus reads / writes and corpus membership.
- :class:`~opencontractserver.corpuses.services.lifecycle.DocumentLifecycleService`
  — soft-delete / restore / trash.
- :class:`~opencontractserver.corpuses.services.paths.CorpusPathService`
  — low-level :class:`DocumentPath` disambiguation internals.

``CorpusObjsService`` is retained here ONLY as a deprecated facade that
multiply-inherits the five segmented services, so existing imports
(``from opencontractserver.corpuses.corpus_objs_service import
CorpusObjsService``) and every ``CorpusObjsService.<method>`` call site keep
working unchanged until all call sites are migrated (issue #1716, Phase 2C).

.. deprecated::
    Import the specific service you need from
    :mod:`opencontractserver.corpuses.services` directly. This shim module
    will be removed in a follow-up PR once all call sites are migrated
    (issue #1716, Phase 2C).
"""

from __future__ import annotations

import warnings

from opencontractserver.corpuses.services import (
    CorpusDocumentService,
    CorpusPathService,
    DocumentLifecycleService,
    FolderCRUDService,
    FolderDocumentService,
)

warnings.warn(
    "opencontractserver.corpuses.corpus_objs_service (and the CorpusObjsService "
    "facade) is deprecated. Import the specific service you need from "
    "opencontractserver.corpuses.services instead. This shim is removed once all "
    "call sites are migrated (issue #1716, Phase 2C).",
    DeprecationWarning,
    # stacklevel=2 so the warning names the file that imported the shim, not
    # this module — making each deprecated call site directly actionable for
    # the Phase 2C migration.
    stacklevel=2,
)

__all__ = [
    "CorpusObjsService",
    "FolderCRUDService",
    "FolderDocumentService",
    "CorpusDocumentService",
    "DocumentLifecycleService",
    "CorpusPathService",
]


class CorpusObjsService(
    FolderCRUDService,
    FolderDocumentService,
    CorpusDocumentService,
    DocumentLifecycleService,
    CorpusPathService,
):
    """DEPRECATED facade — use the segmented services directly.

    Multiply-inherits the five segmented corpus services so that every method
    previously defined on the ``corpus_objs_service`` monolith remains callable
    as ``CorpusObjsService.<method>`` while call sites are migrated (issue
    #1716). The five parent services each inherit ``BaseService`` directly and
    share no method names, so the method resolution order is unambiguous.

    New code MUST import the specific service it needs
    (:class:`~opencontractserver.corpuses.services.folders.FolderCRUDService`,
    :class:`~opencontractserver.corpuses.services.folder_documents.FolderDocumentService`,
    :class:`~opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService`,
    :class:`~opencontractserver.corpuses.services.lifecycle.DocumentLifecycleService`,
    :class:`~opencontractserver.corpuses.services.paths.CorpusPathService`)
    from :mod:`opencontractserver.corpuses.services` instead.

    This facade adds no methods and overrides nothing — it is a pure
    aggregation point and will be deleted with this module once migration
    completes.
    """

    pass
