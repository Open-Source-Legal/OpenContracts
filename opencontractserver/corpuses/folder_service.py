"""
Backwards-compatibility shim for the old ``DocumentFolderService`` API.

The single-class ``DocumentFolderService`` has been split into two focused
services:

- :class:`opencontractserver.documents.document_service.DocumentService`
  for document-level operations (creation, quota, validation, standalone
  lookup, document-level permissions).
- :class:`opencontractserver.corpuses.corpus_objs_service.CorpusObjsService`
  for corpus-scoped operations ("give me X inside corpus Y for user Z" —
  documents-in-corpus, folders, soft-delete/restore lifecycle, future
  corpus-linked object types).

``DocumentFolderService`` is preserved as a multiple-inheritance subclass
of both new services so existing imports continue to work unchanged.  New
code should import the appropriate service directly; this shim will be
removed once the migration is complete.
"""

from __future__ import annotations

from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
from opencontractserver.documents.document_service import DocumentService


class DocumentFolderService(CorpusObjsService, DocumentService):
    """
    Deprecated. Use ``DocumentService`` or ``CorpusObjsService`` directly.

    Inherits the full method surface from both new services so existing
    callers continue to work without code changes.  The MRO is
    ``(DocumentFolderService, CorpusObjsService, DocumentService, object)``
    — corpus-scoped methods resolve first, which matches the fact that the
    overwhelming majority of legacy callers are corpus-scoped.

    The two parent classes are partitioned so they do not share any public
    method names; a unit test in
    ``opencontractserver/tests/test_document_service.py`` asserts the
    invariant.
    """
