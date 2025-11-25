import logging
from typing import TYPE_CHECKING, Optional

from django.contrib.auth.models import AnonymousUser
from django.db.models import Manager, Prefetch, Q, QuerySet
from django_cte import CTEManager

from opencontractserver.shared.QuerySets import (
    AnnotationQuerySet,
    DocumentQuerySet,
    NoteQuerySet,
    PermissionQuerySet,
    UserFeedbackQuerySet,
)

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()
else:
    from django.contrib.auth.models import AbstractUser as User

logger = logging.getLogger(__name__)


class BaseVisibilityManager(Manager):
    """
    Base manager that implements the standard visibility logic for non-annotations and non-relationships .

    This manager provides a secure default implementation of visible_to_user that:
    1. Allows superusers to see everything
    2. For anonymous users: only public objects
    3. For authenticated users: public objects, objects they created, or objects explicitly shared with them

    This is the SECURE fallback logic that should be used by all models that don't have
    more specific permission requirements.
    """

    def visible_to_user(self, user=None) -> QuerySet:
        """
        Returns queryset filtered to only objects visible to the user.

        This implements the exact same logic as the fallback in old resolve_oc_model_queryset:
        - Superusers see everything
        - Anonymous users see only public objects
        - Authenticated users see: public objects, objects they created, or objects with explicit permissions
        """

        from django.apps import apps

        queryset = self.get_queryset()

        # Handle None user as anonymous
        if user is None:
            user = AnonymousUser()

        # Superusers see everything (ordered by created for consistency)
        if hasattr(user, "is_superuser") and user.is_superuser:
            return queryset.order_by("created")

        # Anonymous users only see public items
        if user.is_anonymous:
            return queryset.filter(is_public=True)

        try:
            # Get objects the user has read permission for via Guardian
            model_name = self.model._meta.model_name
            app_label = self.model._meta.app_label

            # Fallback to legacy logic with security warning
            logger.debug(
                f"Using unoptimized visible_to_user permission logic for {model_name} "
                f"(app: {app_label}, model: {model_name})"
            )

            logger.warning(
                f"Consider implementing tuned visible_to_user method on {model_name} manager"
            )

            # === TOP_LEVEL PERMISSION LOGIC ===
            # This logic is for objs that don't follow some parent permissions logic

            # Get the base queryset first (only stuff given user CAN see)
            queryset = self.model.objects.none()  # Start with an empty queryset

            # Handle the case where user resolution failed explicitly
            if user is None:
                queryset = self.model.objects.filter(is_public=True)
            elif user.is_superuser:
                # Superusers see everything, no filtering needed
                queryset = self.model.objects.all().order_by("created")
            elif user.is_anonymous:
                # Anonymous users only see public items
                queryset = self.model.objects.filter(is_public=True)
            else:  # Authenticated, non-superuser
                permission_model_name = f"{model_name}userobjectpermission"
                try:
                    permission_model_type = apps.get_model(
                        app_label, permission_model_name
                    )
                    # Optimize: Get IDs with permissions first, then use IN clause
                    permitted_ids = permission_model_type.objects.filter(
                        permission__codename=f"read_{model_name}", user_id=user.id
                    ).values_list("content_object_id", flat=True)

                    # Build the optimized query using simpler conditions
                    queryset = self.model.objects.filter(
                        Q(creator_id=user.id)
                        | Q(is_public=True)
                        | Q(id__in=permitted_ids)
                    )
                except LookupError:
                    logger.warning(
                        f"Permission model {app_label}.{permission_model_name}"
                        " not found. Falling back to creator/public check."
                    )
                    # Fallback if permission model doesn't exist (might happen for simpler models)
                    queryset = self.model.objects.filter(
                        Q(creator_id=user.id) | Q(is_public=True)
                    )

            # --- Apply Performance Optimizations Based on Model Type ---
            if model_name.upper() == "CORPUS":
                logger.debug("Applying Corpus specific optimizations")
                queryset = queryset.select_related(
                    "creator",
                    "label_set",
                    "user_lock",  # If user_lock info is displayed
                ).prefetch_related(
                    "documents"  # Very important if showing document counts or list previews
                    # Add other prefetches if CorpusType uses them:
                    # 'annotations', 'relationships', 'queries', 'actions', 'notes'
                )
            elif model_name.upper() == "DOCUMENT":
                logger.debug("Applying Document specific optimizations")
                from opencontractserver.annotations.models import Annotation

                queryset = queryset.select_related("creator", "user_lock")

                # Prefetch annotations to avoid N+1 when doc_annotations is accessed
                # This is critical for the docAnnotations GraphQL field
                queryset = queryset.prefetch_related(
                    Prefetch(
                        "doc_annotations",
                        queryset=Annotation.objects.select_related(
                            "annotation_label", "corpus", "analysis", "creator"
                        ),
                        to_attr="_prefetched_doc_annotations",
                    ),
                    # Add other important relationships to avoid N+1 queries
                    "rows",
                    "source_relationships",
                    "target_relationships",
                    "notes",
                )

                # Prefetch permission objects to avoid N+1 queries in myPermissions resolver
                # Only do this for authenticated non-superuser users
                if user and not user.is_anonymous and not user.is_superuser:
                    from opencontractserver.documents.models import (
                        DocumentUserObjectPermission,
                    )

                    # Prefetch user permissions for this specific user
                    queryset = queryset.prefetch_related(
                        Prefetch(
                            "documentuserobjectpermission_set",
                            queryset=DocumentUserObjectPermission.objects.filter(
                                user_id=user.id
                            ).select_related("permission"),
                            to_attr="_prefetched_user_perms",
                        ),
                        # Also prefetch group permissions
                        "documentgroupobjectpermission_set__permission",
                        "documentgroupobjectpermission_set__group",
                    )
            # Add elif blocks here for other models needing specific optimizations

            # Apply distinct *after* optimizations only when necessary.
            # The permission logic with __in might introduce duplicates for authenticated users.
            # Skip distinct for public/superuser queries where it's not needed.
            if user and not user.is_anonymous and not user.is_superuser:
                # Only apply distinct for authenticated non-superuser users where permission JOINs occur
                queryset = queryset.distinct()

            return queryset

        except (ImportError, Exception) as e:
            # Fall back to creator/public check only if Guardian not available or error
            logger.debug(
                f"Could not use Guardian permissions for {self.model.__name__}: {e}. "
                f"Using creator/public filtering only."
            )
            queryset = queryset.filter(Q(creator_id=user.id) | Q(is_public=True))

        return queryset.distinct()


class PermissionManager(BaseVisibilityManager):
    """
    Manager that uses PermissionQuerySet which has its own visible_to_user implementation.
    Inherits from BaseVisibilityManager but overrides to use PermissionQuerySet's version.
    """

    def get_queryset(self):
        return PermissionQuerySet(self.model, using=self._db)

    def for_user(self, user, perm, extra_conditions=None):
        return self.get_queryset().for_user(user, perm, extra_conditions)

    def visible_to_user(self, user) -> PermissionQuerySet:
        """
        Returns queryset filtered by user permission via PermissionQuerySet.
        This overrides BaseVisibilityManager's implementation to use
        PermissionQuerySet's simpler visible_to_user logic.
        """
        return self.get_queryset().visible_to_user(user)


class PermissionCTEManager(CTEManager, PermissionManager):
    """
    Helper class for combining CTEManager and PermissionManager in a single MRO.
    We place CTEManager first so the specialized methods (like from_queryset) work,
    and then PermissionManager second to ensure we also use PermissionQuerySet.
    """

    pass


class UserFeedbackManager(BaseVisibilityManager):
    def get_queryset(self):
        return UserFeedbackQuerySet(self.model, using=self._db)

    def visible_to_user(self, user):
        """Delegate to the queryset's visible_to_user method"""
        return self.get_queryset().visible_to_user(user)

    def get_or_none(self, *args, **kwargs):
        try:
            return self.get(*args, **kwargs)
        except self.model.DoesNotExist:
            return None

    def approved(self):
        return self.get_queryset().approved()

    def rejected(self):
        return self.get_queryset().rejected()

    def pending(self):
        return self.get_queryset().pending()

    def recent(self, days=30):
        return self.get_queryset().recent(days)

    def with_comments(self):
        return self.get_queryset().with_comments()

    def by_creator(self, creator):
        return self.get_queryset().by_creator(creator)

    def search(self, query):
        return self.get_queryset().filter(
            Q(comment__icontains=query) | Q(markdown__icontains=query)
        )


class DocumentManager(BaseVisibilityManager):
    """
    Extends PermissionManager to return a DocumentQuerySet
    that supports vector searching via the mixin.
    """

    def get_queryset(self):
        return DocumentQuerySet(self.model, using=self._db)

    def search_by_embedding(self, query_vector, embedder_path, top_k=10):
        """
        Convenience method so you can do:
            Document.objects.search_by_embedding([...])
        directly.
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class AnnotationManager(PermissionCTEManager.from_queryset(AnnotationQuerySet)):
    """
    Custom Manager for the Annotation model that uses:
      - CTEManager (from_queryset)
      - AnnotationQuerySet (with permission checks, optional vector search, etc.)
    """

    def get_queryset(self) -> AnnotationQuerySet:
        return AnnotationQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Optional[Q] = None
    ) -> AnnotationQuerySet:
        """
        Filters the queryset based on user permissions.
        """
        return self.get_queryset().for_user(user, perm, extra_conditions)

    def search_by_embedding(self, query_vector, embedder_path, top_k=10):
        """
        If using VectorSearchViaEmbeddingMixin in your AnnotationQuerySet,
        you can call this convenience method just like:
            Annotation.objects.search_by_embedding([0.1, 0.2, ...], "xx-embedder", top_k=10)
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class NoteManager(PermissionCTEManager.from_queryset(NoteQuerySet)):
    """
    Custom Manager for the Note model that uses:
      - CTEManager (from_queryset)
      - NoteQuerySet (with permission checks, optional vector search, etc.)
    """

    def get_queryset(self) -> NoteQuerySet:
        return NoteQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Optional[Q] = None
    ) -> NoteQuerySet:
        """
        Filters the queryset based on user permissions.
        """
        return self.get_queryset().for_user(user, perm, extra_conditions)

    def search_by_embedding(self, query_vector, embedder_path, top_k=10):
        """
        If using VectorSearchViaEmbeddingMixin in your NoteQuerySet,
        you can call:
            Note.objects.search_by_embedding([0.1, 0.2, ...], "xx-embedder", top_k=10)
        """
        return self.get_queryset().search_by_embedding(
            query_vector, embedder_path, top_k
        )


class EmbeddingManager(BaseVisibilityManager):
    """
    Manager for Embedding that can store or update embeddings
    without creating accidental duplicates for the same dimension,
    embedder_path, and parent references (document/annotation/note).
    """

    def _get_vector_field_name(self, dimension: int) -> str:
        if dimension == 384:
            return "vector_384"
        elif dimension == 768:
            return "vector_768"
        elif dimension == 1536:
            return "vector_1536"
        elif dimension == 3072:
            return "vector_3072"
        raise ValueError(f"Unsupported embedding dimension: {dimension}")

    def store_embedding(
        self,
        *,
        creator: User,
        dimension: int,
        vector: list[float],
        embedder_path: str,
        document_id: Optional[int] = None,
        annotation_id: Optional[int] = None,
        note_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        message_id: Optional[int] = None,
    ):
        """
        Create or update an Embedding, referencing exactly one of:
        Document, Annotation, Note, Conversation, or ChatMessage.
        If an Embedding already exists for (embedder_path + parent_id), update its vector field
        instead of creating a new record.
        """
        if not any([document_id, annotation_id, note_id, conversation_id, message_id]):
            raise ValueError(
                "Must provide one of document_id, annotation_id, note_id, conversation_id, or message_id."
            )

        field_name = self._get_vector_field_name(dimension)

        # Find existing embedding (if any)
        embedding = (
            self.visible_to_user(user=creator)
            .filter(
                embedder_path=embedder_path,
                document_id=document_id,
                annotation_id=annotation_id,
                note_id=note_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
            .first()
        )

        if embedding:
            setattr(embedding, field_name, vector)
            embedding.save()
            return embedding

        # Create a new embedding if none found
        return self.create(
            creator=creator,
            embedder_path=embedder_path,
            document_id=document_id,
            annotation_id=annotation_id,
            note_id=note_id,
            conversation_id=conversation_id,
            message_id=message_id,
            **{field_name: vector},
        )
