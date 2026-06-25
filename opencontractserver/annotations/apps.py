from django.apps import AppConfig
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_migrate,
    post_save,
)
from django.utils.translation import gettext_lazy as _


class AnnotationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "opencontractserver.annotations"
    verbose_name = _("Annotations")

    def ready(self):
        try:
            import opencontractserver.annotations.signals  # noqa F401
            from opencontractserver.annotations.models import (
                Annotation,
                Note,
                Relationship,
            )
            from opencontractserver.annotations.signals import (  # Relationship signals
                ANNOT_CREATE_UID,
                NOTE_CREATE_UID,
                REL_CREATE_UPDATE_UID,
                REL_DELETE_UID,
                REL_M2M_SOURCES_UID,
                REL_M2M_TARGETS_UID,
                process_annot_on_create_atomic,
                process_note_on_create_atomic,
                process_relationship_m2m_changed,
                process_relationship_on_change_atomic,
                process_relationship_on_delete,
            )

            post_save.connect(
                process_annot_on_create_atomic,
                sender=Annotation,
                dispatch_uid=ANNOT_CREATE_UID,
            )
            post_save.connect(
                process_note_on_create_atomic,
                sender=Note,
                dispatch_uid=NOTE_CREATE_UID,
            )

            # Relationship signals
            post_save.connect(
                process_relationship_on_change_atomic,
                sender=Relationship,
                dispatch_uid=REL_CREATE_UPDATE_UID,
            )
            post_delete.connect(
                process_relationship_on_delete,
                sender=Relationship,
                dispatch_uid=REL_DELETE_UID,
            )
            m2m_changed.connect(
                process_relationship_m2m_changed,
                sender=Relationship.source_annotations.through,
                dispatch_uid=REL_M2M_SOURCES_UID,
            )
            m2m_changed.connect(
                process_relationship_m2m_changed,
                sender=Relationship.target_annotations.through,
                dispatch_uid=REL_M2M_TARGETS_UID,
            )

            # Converge the shipped AuthorityNamespace rows on every
            # post_migrate. The one-shot seed migrations (0082/0085) commit
            # rows outside any test transaction, so a ``TransactionTestCase``
            # flush truncates them mid-suite; this idempotent receiver
            # re-seeds after each flush (and on reused CI volumes at DB
            # setup). See ``ensure_seeded``.
            from opencontractserver.enrichment._namespace_seed import (
                ensure_seeded,
            )

            post_migrate.connect(
                ensure_seeded,
                sender=self,
                dispatch_uid="annotations_seed_authority_namespaces",
            )

            # Make safe_http's default SSRF allowlist resolve to baseline ∪ the
            # installed authority packs' declared source_hosts, so a self-contained
            # scraping pack can carry the hosts it fetches from in its pack.yaml
            # instead of editing constants/safe_http.py. Injected as a callable so
            # the pure safe_http util never imports the enrichment/pipeline layer.
            from opencontractserver.enrichment.services.authority_source_hosts import (
                effective_source_allowlist,
            )
            from opencontractserver.utils.safe_http import (
                register_allowlist_provider,
            )

            register_allowlist_provider(effective_source_allowlist)
        except ImportError:
            pass
