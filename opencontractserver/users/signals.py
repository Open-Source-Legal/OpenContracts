import logging
from typing import Any

from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver

from config.telemetry import record_event
from opencontractserver.shared.grant_cache import invalidate_actor_grants

from .models import User

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=User.groups.through)
@receiver(m2m_changed, sender=User.user_permissions.through)
@receiver(m2m_changed, sender=Group.permissions.through)
def permission_membership_changed(
    sender, instance, action, reverse, pk_set, using, **kwargs
):
    """Django/admin m2m writes invalidate before their transaction commits."""
    if action not in {"post_add", "post_remove", "post_clear"} or pk_set == set():
        return
    if sender is Group.permissions.through or (reverse and pk_set is None):
        user_ids = (None,)
    elif reverse:
        user_ids = pk_set
    else:
        user_ids = (instance.pk,)
    invalidate_actor_grants(user_ids, using=using)


@receiver(post_delete, sender=Group)
@receiver(post_delete, sender=Permission)
def permission_definition_deleted(sender, using, **kwargs):
    """Cascade deletes bypass m2m_changed, including bulk/admin deletions."""
    invalidate_actor_grants((None,), using=using)


def _create_personal_corpus_for_user(user: User) -> None:
    """
    Create a personal corpus for a user.

    This is a helper function called by the user_created_signal handler
    to create the user's "My Documents" personal corpus.

    Args:
        user: The User instance to create the personal corpus for
    """
    # Import here to avoid circular imports during app initialization
    from opencontractserver.corpuses.models import Corpus

    # Use the class method which handles get_or_create and permissions
    corpus = Corpus.get_or_create_personal_corpus(user)
    logger.info(f"Created personal corpus {corpus.pk} for new user {user.pk}")


def arbitrary_function(user: User) -> None:
    """
    An arbitrary function to be called when a new user is created.

    Args:
        user (User): The newly created user instance
    """
    # Add your custom logic here
    logger.info("New user created: pk=%s", user.pk)  # pragma: no cover


def ready_to_record() -> bool:
    """
    Check if the database and required models are ready.

    Returns:
        bool: True if the database is ready and all required models are installed
    """
    try:
        # Check if we're in a migration
        if apps.get_app_config("users").models_module is None:
            return False

        # Check if the Installation model is ready
        Installation = apps.get_model("users", "Installation")
        # Try a simple database operation
        with transaction.atomic():
            Installation.objects.first()
        return True
    except (LookupError, DatabaseError, ProgrammingError, OperationalError):
        return False


@receiver(post_save, sender=User)
def user_created_signal(
    sender: type[User], instance: User, created: bool, **kwargs: Any
) -> None:
    """
    Signal handler that runs when a User instance is created.

    Creates the user's personal "My Documents" corpus and records telemetry.

    Args:
        sender (Type[User]): The model class that sent the signal
        instance (User): The actual instance being saved
        created (bool): Boolean indicating if this is a new instance
        **kwargs (Any): Additional keyword arguments passed to the signal
    """
    if not created:
        return

    # Skip personal corpus creation for guardian's anonymous user — it is a
    # system-level account that doesn't need a personal document store.
    from django.conf import settings

    anon_name = getattr(settings, "ANONYMOUS_USER_NAME", None)
    if anon_name is not None and instance.username == anon_name:
        return

    # Record telemetry
    try:
        with transaction.atomic():
            if ready_to_record():
                record_event("user_created", {"user_count": User.objects.all().count()})
    except Exception as e:
        # Log but don't raise - we don't want to break user creation if telemetry fails
        logger.error(f"Error recording user created event: {e}")

    # Create personal corpus for new user
    try:
        with transaction.atomic():
            _create_personal_corpus_for_user(instance)
    except IntegrityError:
        # Personal corpus already exists (race condition or duplicate signal)
        # This is not an error - the constraint ensures uniqueness
        logger.warning(
            f"Personal corpus already exists for user {instance.pk} "
            "(possible race condition)"
        )
    except Exception as e:
        # Log but don't raise - we don't want to break user creation
        # Personal corpus can be created on-demand during first upload
        logger.error(f"Error creating personal corpus for user {instance.pk}: {e}")
