"""Read-only Django admin for chunked-upload bookkeeping.

Operators occasionally need to inspect stale or FAILED chunked-upload
sessions (e.g. to understand why a large upload never completed) or to see
how many parts a session accumulated. These admins are intentionally
read-only: sessions and parts are managed entirely by the
``/api/imports/chunked/*`` endpoints and the ``purge_stale_chunked_uploads``
garbage collector, so manual edits would only risk corrupting in-flight
assembly state.
"""

from django.contrib import admin

from opencontractserver.document_imports.models import (
    ChunkedUploadPart,
    ChunkedUploadSession,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Shared base that disables add/change/delete from the admin UI."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ChunkedUploadSession)
class ChunkedUploadSessionAdmin(_ReadOnlyAdmin):
    list_display = (
        "id",
        "creator",
        "kind",
        "status",
        "filename",
        "total_chunks",
        "created",
        "modified",
    )
    list_filter = ("status", "kind")
    search_fields = ("id", "filename", "creator__username")
    date_hierarchy = "created"
    ordering = ("-created",)


@admin.register(ChunkedUploadPart)
class ChunkedUploadPartAdmin(_ReadOnlyAdmin):
    list_display = ("id", "session", "index", "created")
    search_fields = ("session__id",)
    ordering = ("session", "index")
