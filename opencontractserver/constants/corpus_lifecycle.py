"""Constants for corpus document-lifecycle bulk operations (trash / restore).

See ``opencontractserver.corpuses.services.lifecycle.DocumentLifecycleService``,
in particular the ``bulk_soft_delete_documents`` primitive shared by
``empty_corpus`` and folder cascade-delete.
"""

# Chunk size for ``DocumentLifecycleService.bulk_soft_delete_documents``.
# The primitive locks and loads at most this many active ``DocumentPath`` rows
# (plus their joined ``Document``) into Python at once, via keyset pagination
# on ``pk``, instead of materializing every active path in scope in one shot.
# This bounds peak Python-side memory to a fixed ceiling regardless of how
# many documents a caller (``empty_corpus``, folder cascade-delete) puts in
# scope, at the cost of a bounded number of extra queries per additional
# chunk (issue #2045; #1951 fixed the earlier per-document query-count
# blowup). 500 keeps that per-chunk overhead low while still capping the rows
# materialized at once to a small, predictable multiple of the per-row size
# (a ``DocumentPath`` plus its joined ``Document``).
BULK_SOFT_DELETE_CHUNK_SIZE = 500
