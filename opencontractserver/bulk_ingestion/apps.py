from django.apps import AppConfig


class BulkIngestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.bulk_ingestion"
    verbose_name = "Bulk Ingestion"
