import logging
from typing import Any

from django.apps import apps
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models.signals import post_save
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver

from config.telemetry import record_event

from .models import User

logger = logging.getLogger(__name__)


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
