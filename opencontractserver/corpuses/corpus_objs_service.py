"""Backward-compatible shim for the corpus service layer.

``corpus_objs_service.py`` was a ~2,900-line monolith holding six distinct
responsibilities in a single ``CorpusObjsService`` class. As of issue #1716
(service-layer centralization, Phase 2) it has been split into the segmented
:mod:`opencontractserver.corpuses.services` package:

- :class:`~opencontractserver.corpuses.services.folders.FolderService`
  — folder CRUD, the folder tree, and document-in-folder placement.
- :class:`~opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService`
  — document-in-corpus reads / writes and corpus membership.
- :class:`~opencontractserver.corpuses.services.lifecycle.DocumentLifecycleService`
  — soft-delete / restore / trash.
- :class:`~opencontractserver.corpuses.services.paths.CorpusPathService`
  — low-level :class:`DocumentPath` disambiguation internals.

``CorpusObjsService`` is retained here ONLY as a deprecated facade that
multiply-inherits the four segmented services, so existing imports
(``from opencontractserver.corpuses.corpus_objs_service import
CorpusObjsService``) and every ``CorpusObjsService.<method>`` call site keep
working unchanged for one release.

.. deprecated::
    Import the specific service you need from
    :mod:`opencontractserver.corpuses.services` directly. This shim module
    will be removed once all call sites are migrated (issue #1716, Phase C).
"""

from __future__ import annotations

import warnings

from opencontractserver.corpuses.services import (
    CorpusDocumentService,
    CorpusPathService,
    DocumentLifecycleService,
    FolderService,
)

warnings.warn(
    "opencontractserver.corpuses.corpus_objs_service (and the CorpusObjsService "
    "facade) is deprecated. Import the specific service you need from "
    "opencontractserver.corpuses.services instead. This shim is removed once all "
    "call sites are migrated (issue #1716, Phase 2C).",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "CorpusObjsService",
    "FolderService",
    "CorpusDocumentService",
    "DocumentLifecycleService",
    "CorpusPathService",
]


class CorpusObjsService(
    FolderService,
    CorpusDocumentService,
    DocumentLifecycleService,
    CorpusPathService,
):
    """DEPRECATED facade — use the segmented services directly.

    Multiply-inherits the four segmented corpus services so that every method
    previously defined on the ``corpus_objs_service`` monolith remains callable
    as ``CorpusObjsService.<method>`` while call sites are migrated (issue
    #1716). The four parent services each inherit ``BaseService`` directly and
    share no method names, so the method resolution order is unambiguous.

    New code MUST import the specific service it needs
    (:class:`~opencontractserver.corpuses.services.folders.FolderService`,
    :class:`~opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService`,
    :class:`~opencontractserver.corpuses.services.lifecycle.DocumentLifecycleService`,
    :class:`~opencontractserver.corpuses.services.paths.CorpusPathService`)
    from :mod:`opencontractserver.corpuses.services` instead.

    This facade adds no methods and overrides nothing — it is a pure
    aggregation point and will be deleted with this module once migration
    completes.
    """

    pass
