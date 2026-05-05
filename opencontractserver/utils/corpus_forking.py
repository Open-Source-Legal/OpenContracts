from typing import TYPE_CHECKING

from opencontractserver.corpuses.models import Corpus
from opencontractserver.tasks import fork_corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_collector import collect_corpus_objects
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from opencontractserver.users.models import User


def build_fork_corpus_task(corpus_pk_to_fork: str, user: "User"):
    """
    Build a Celery task to fork a corpus.

    This collects all necessary IDs and creates a new corpus shell,
    then returns a Celery task signature ready to be executed.

    Args:
        corpus_pk_to_fork: Primary key of the corpus to fork
        user: User who will own the forked corpus

    Returns:
        Celery task signature for fork_corpus
    """
    source_corpus = Corpus.objects.get(pk=corpus_pk_to_fork)

    # Collect all object IDs using the shared collector
    collected = collect_corpus_objects(source_corpus, include_metadata=True)

    # Clone the corpus: https://docs.djangoproject.com/en/3.1/topics/db/queries/copying-model-instances
    source_corpus.pk = None
    source_corpus.slug = ""  # Clear slug so save() generates a new unique one

    # At this point the in-memory instance is detached from the original row;
    # saving it will INSERT a new Corpus.  Rename for clarity.
    corpus_clone = source_corpus
    corpus_clone.title = f"[FORK] {corpus_clone.title}"
    # Lock corpus to tell frontend to show this as loading and disable selection
    corpus_clone.backend_lock = True
    corpus_clone.creator = user
    corpus_clone.parent_id = corpus_pk_to_fork
    corpus_clone.save()

    set_permissions_for_obj_to_user(user, corpus_clone, [PermissionTypes.CRUD])

    # Remove references to related objects on the new object, as these point to original docs and labels
    # Note: New forked corpus has no DocumentPath records yet, so no document cleanup needed
    corpus_clone.label_set = None

    # Copy docs, annotations, folders, relationships, and metadata using async task
    return fork_corpus.si(
        corpus_clone.id,
        collected.document_ids,
        collected.label_set_id,
        collected.annotation_ids,
        collected.folder_ids,
        collected.relationship_ids,
        user.id,
        collected.metadata_column_ids,
        collected.metadata_datacell_ids,
    )
