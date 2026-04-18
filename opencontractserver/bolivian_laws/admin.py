from django.contrib import admin

from opencontractserver.bolivian_laws.models import (
    BolivianLegalDocument,
    LegalAreaCorpus,
)


@admin.register(LegalAreaCorpus)
class LegalAreaCorpusAdmin(admin.ModelAdmin):
    list_display = ("area", "corpus", "created")
    readonly_fields = ("area", "corpus", "created")
    search_fields = ("area",)


@admin.register(BolivianLegalDocument)
class BolivianLegalDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "area",
        "source",
        "status",
        "published_at",
        "ingested_at",
    )
    list_filter = ("area", "source", "status")
    search_fields = ("title", "external_id", "pdf_sha256")
    readonly_fields = (
        "pdf_sha256",
        "document",
        "corpus",
        "created",
        "ingested_at",
        "last_error",
    )
    actions = ["mark_pending_for_retry"]

    @admin.action(description="Marcar como pendiente para reintentar")
    def mark_pending_for_retry(self, request, queryset):
        # Resets tracking-record state so a fresh re-ingest can succeed.
        # SHA-based dedupe will still block re-ingesting the exact same
        # bytes — for a true retry, delete the record first.
        updated = queryset.update(
            status=BolivianLegalDocument.Status.PENDING,
            last_error="",
            ingested_at=None,
        )
        self.message_user(request, f"{updated} record(s) marked as pending.")
