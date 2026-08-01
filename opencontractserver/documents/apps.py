from django.apps import AppConfig
from django.db.models.signals import post_migrate, post_save
from django.utils.translation import gettext_lazy as _


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.documents"
    verbose_name = _("Documents")

    def ready(self):
        try:
            import opencontractserver.documents.signals  # noqa F401
            from opencontractserver.documents.models import Document
            from opencontractserver.documents.signals import (
                DOC_CREATE_UID,
                connect_corpus_document_signals,
                process_doc_on_create_atomic,
            )

            # DOCUMENT SIGNALS #########################################################################################
            # When a new doc is created, queue a PAWLS token extract job
            post_save.connect(
                process_doc_on_create_atomic,
                sender=Document,
                dispatch_uid=DOC_CREATE_UID,
            )

            # Connect the m2m_changed signal for when documents are added to corpuses
            connect_corpus_document_signals()

            # STORAGE WARMING ##########################################################################################
            # Pre-warm the storage backend to avoid ~400ms cold start on first file URL access
            # Run synchronously to ensure the main process gets warmed
            from opencontractserver.utils.storage_warming import warm_storage_backend

            warm_storage_backend()

            # BACKWARD COMPATIBILITY LAYER REMOVED - Issue #654 Phase 2 ###############################################
            # The custom M2M manager has been removed. All code must now use:
            # - corpus.add_document(document=doc, user=user) instead of corpus.documents.add(doc)
            # - corpus.remove_document(document=doc, user=user) instead of corpus.documents.remove(doc)
            # - CorpusDocumentService.get_corpus_documents(user, corpus) in user-context code, or
            #   corpus._get_active_documents() in internal/task code,
            #   instead of corpus.documents.all() or corpus.get_documents()
            # - corpus.document_count() instead of corpus.documents.count()
            # This ensures DocumentPath is the single source of truth for corpus-document relationships.

            # Converge the PipelineSettings singleton on every post_migrate.
            # The one-shot seed migration (0031) commits its row outside any
            # test transaction, so a ``TransactionTestCase`` flush truncates it
            # mid-suite and nothing restores it; the lazy re-creation in
            # ``get_instance()`` then deadlocks any async test that reaches it
            # from the asgiref executor thread. This idempotent receiver
            # re-seeds after each flush (and on reused CI volumes at DB setup).
            # See ``ensure_pipeline_settings_seeded``.
            from opencontractserver.documents._pipeline_settings_seed import (
                ensure_pipeline_settings_seeded,
            )

            post_migrate.connect(
                ensure_pipeline_settings_seeded,
                sender=self,
                dispatch_uid="documents_seed_pipeline_settings",
            )

            # Register system checks
            from opencontractserver.documents import checks  # noqa F401

        except ImportError:
            pass
