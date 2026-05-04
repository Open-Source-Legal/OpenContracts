from django.apps import AppConfig


class DocumentUploadsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "opencontractserver.document_uploads"
    verbose_name: str = "Document Uploads (REST)"
