from django.apps import AppConfig


class WorkerUploadsConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "opencontractserver.worker_uploads"
    verbose_name: str = "Worker Uploads"

    def ready(self) -> None:
        pass  # Placeholder for future signal registrations
