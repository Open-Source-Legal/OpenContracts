"""Corpus-scoped service layer.

Segmented services for corpus-scoped object access and permissioning, split
out of the former ``corpus_objs_service.py`` monolith (issue #1716,
service-layer centralization Phase 2 — see
``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``).
Each service inherits :class:`opencontractserver.shared.services.base.BaseService`.

- :class:`~opencontractserver.corpuses.services.folders.FolderCRUDService`
  — folder CRUD, the folder tree, search, and bulk structure creation.
- :class:`~opencontractserver.corpuses.services.folder_documents.FolderDocumentService`
  — document-in-folder placement, listing, and counts.
- :class:`~opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService`
  — document-in-corpus reads / writes and corpus membership.
- :class:`~opencontractserver.corpuses.services.corpus_service.CorpusService`
  — Corpus-row CRUD: delete, visibility, and description versioning.
- :class:`~opencontractserver.corpuses.services.lifecycle.DocumentLifecycleService`
  — soft-delete / restore / trash.
- :class:`~opencontractserver.corpuses.services.paths.CorpusPathService`
  — low-level :class:`DocumentPath` disambiguation internals.

Import the specific service you need from this package::

    from opencontractserver.corpuses.services import FolderCRUDService
"""

from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.corpuses.services.folder_documents import (
    FolderDocumentService,
)
from opencontractserver.corpuses.services.folders import FolderCRUDService
from opencontractserver.corpuses.services.lifecycle import DocumentLifecycleService
from opencontractserver.corpuses.services.paths import CorpusPathService

__all__ = [
    "FolderCRUDService",
    "FolderDocumentService",
    "CorpusDocumentService",
    "CorpusService",
    "DocumentLifecycleService",
    "CorpusPathService",
]
