from django.db import models
from django.db.models import Q
from django.utils import timezone
from tree_queries.query import TreeQuerySet

from opencontractserver.shared.mixins import VectorSearchViaEmbeddingMixin


class PermissionedTreeQuerySet(TreeQuerySet):
    def approved(self):
        return self.filter(approved=True)

    def rejected(self):
        return self.filter(rejected=True)

    def pending(self):
        return self.filter(approved=False, rejected=False)

    def recent(self, days=30):
        recent_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created__gte=recent_date)

    def with_comments(self):
        return self.exclude(comment="")

    def by_creator(self, creator):
        return self.filter(creator=creator)

    def visible_to_user(self, user):
        """
        Gets queryset with_tree_fields that is visible to user. At moment, we're JUST filtering
        on creator and is_public, BUT this will filter on per-obj permissions later.
        """
        # Handle None user as anonymous
        if user is None:
            from django.contrib.auth.models import AnonymousUser

            user = AnonymousUser()

        if hasattr(user, "is_superuser") and user.is_superuser:
            return self.all().order_by("created")

        if user.is_anonymous or not hasattr(user, "is_authenticated"):
            queryset = self.filter(Q(is_public=True)).distinct()
        else:
            # Try to use Guardian's permission system for authenticated users
            from guardian.shortcuts import get_objects_for_user

            try:
                # Get objects the user has read permission for via Guardian
                model_name = self.model._meta.model_name
                app_label = self.model._meta.app_label
                perm = f"{app_label}.read_{model_name}"

                # Get objects user has permission for
                permitted_objects = get_objects_for_user(
                    user,
                    perm,
                    klass=self.model,
                    accept_global_perms=False,
                    with_superuser=False,
                )

                # Get the IDs of permitted objects
                permitted_ids = list(permitted_objects.values_list("id", flat=True))

                # Combine: creator OR public OR has explicit permission
                queryset = self.filter(
                    Q(creator=user) | Q(is_public=True) | Q(id__in=permitted_ids)
                ).distinct()

            except (ImportError, Exception):
                # Fall back to creator/public check only if Guardian not available
                queryset = self.filter(Q(creator=user) | Q(is_public=True)).distinct()

        # Apply model-specific optimizations
        model_name = self.model._meta.model_name
        if model_name == "corpus":
            queryset = queryset.select_related(
                "creator",
                "label_set",
                "user_lock",
            )

        return queryset.with_tree_fields()

    def with_tree_fields(self):
        return super().with_tree_fields()


class UserFeedbackQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(approved=True)

    def rejected(self):
        return self.filter(rejected=True)

    def pending(self):
        return self.filter(approved=False, rejected=False)

    def recent(self, days=30):
        recent_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created__gte=recent_date)

    def with_comments(self):
        return self.exclude(comment="")

    def by_creator(self, creator):
        return self.filter(creator=creator)

    def visible_to_user(self, user):
        if user.is_superuser:
            return self.all()

        if user.is_anonymous:
            return self.filter(Q(is_public=True)).distinct()

        # UserFeedback is visible if:
        # 1. Created by the user, OR
        # 2. Is public, OR
        # 3. Has a commented_annotation that is public (handle NULL case)

        result = self.filter(
            Q(creator=user)
            | Q(is_public=True)
            | (
                Q(commented_annotation__isnull=False)
                & Q(commented_annotation__is_public=True)
            )
        ).distinct()

        return result


class PermissionQuerySet(models.QuerySet):
    def visible_to_user(self, user, perm=None):

        if user.is_superuser:
            return self.all()

        # model = self.model
        # content_type = ContentType.objects.get_for_model(model)
        #
        # # Determine the permission codename
        # permission_codename = f'{perm}_{model._meta.model_name}'
        #
        # # User permission subquery
        # user_perm = UserObjectPermission.objects.filter(
        #     content_type=content_type,
        #     user=user,
        #     permission__codename=permission_codename,
        #     object_pk=OuterRef('pk')
        # )
        #
        # # Group permission subquery
        # group_perm = GroupObjectPermission.objects.filter(
        #     content_type=content_type,
        #     group__user=user,
        #     permission__codename=permission_codename,
        #     object_pk=OuterRef('pk')
        # )

        # Construct the base queryset
        # queryset = self.annotate(
        #     has_user_perm=Exists(user_perm),
        #     has_group_perm=Exists(group_perm)
        # )

        # Filter based on permissions and public status.
        # NOTE(deferred): Instance-level sharing (django-guardian user/object
        # permissions) is not yet wired here. Currently only creator and
        # is_public are checked. See visible_to_user() on per-model managers
        # for the full permission-aware pattern.
        # permission_filter = Q(has_user_perm=True) | Q(has_group_perm=True) | Q(is_public=True)
        permission_filter = Q(is_public=True)
        if not user.is_anonymous:
            permission_filter |= Q(creator=user)

        # # Add extra conditions based on permission type
        # if perm == 'read':
        #     # For read permission, include objects created by the user
        #     permission_filter |= Q(creator=user)
        # elif perm == 'publish':
        #     # For publish permission, only include objects created by the user
        #     permission_filter &= Q(creator=user)

        return self.filter(permission_filter).distinct()


class DocumentQuerySet(PermissionQuerySet, VectorSearchViaEmbeddingMixin):
    """
    Custom QuerySet for Document that includes permission filtering
    with guardian checks and vector-based search.
    """

    def visible_to_user(self, user, perm=None):
        """
        Override PermissionQuerySet.visible_to_user to include guardian
        permission checks. Without this override, chaining
        .filter().visible_to_user() would skip guardian entirely.

        Follows the same pattern as BaseVisibilityManager.visible_to_user
        (opencontractserver/shared/Managers.py lines 103-118).
        """
        from django.contrib.auth.models import AnonymousUser

        if user is None:
            user = AnonymousUser()

        if hasattr(user, "is_superuser") and user.is_superuser:
            return self.all()

        if user.is_anonymous:
            return self.filter(is_public=True).distinct()

        # Query guardian permission table directly for performance
        from django.apps import apps

        try:
            permission_model = apps.get_model(
                "documents", "documentuserobjectpermission"
            )
            permitted_ids = permission_model.objects.filter(
                permission__codename="read_document", user_id=user.id
            ).values_list("content_object_id", flat=True)

            return self.filter(
                Q(creator=user) | Q(is_public=True) | Q(id__in=permitted_ids)
            ).distinct()
        except LookupError:
            return self.filter(Q(creator=user) | Q(is_public=True)).distinct()


class AnnotationQuerySet(PermissionQuerySet, VectorSearchViaEmbeddingMixin):
    """
    Custom QuerySet for Annotation model, combining:
      - PermissionQuerySet for permission-based filtering
      - VectorSearchViaEmbeddingMixin for vector-based search

    CTE support: django-cte 3.0+ provides the standalone with_cte() function
    that works on any queryset, so CTEQuerySet inheritance is no longer needed.
    """

    def visible_to_user(self, user, perm=None):
        """
        Override to properly handle annotation privacy model.
        This ensures that even when AnnotationQueryOptimizer isn't used,
        the privacy model is still respected.
        """
        from opencontractserver.analyzer.models import (
            Analysis,
            AnalysisUserObjectPermission,
        )
        from opencontractserver.extracts.models import (
            Extract,
            ExtractUserObjectPermission,
        )

        # Superusers see everything
        if user.is_superuser:
            return self.all()

        # Start with base queryset
        qs = self.all()

        # For anonymous users, only show public structural annotations
        if user.is_anonymous:
            # Handle both document-attached and structural_set-linked annotations
            doc_attached_public = Q(document__isnull=False) & Q(
                document__is_public=True
            )
            structural_set_public = (
                Q(document__isnull=True)
                & Q(structural_set__isnull=False)
                & Q(structural_set__documents__is_public=True)
            )
            return qs.filter(
                Q(structural=True)
                & (doc_attached_public | structural_set_public)
                & (Q(corpus__isnull=True) | Q(corpus__is_public=True))
            ).distinct()

        # Build visibility filters for analyses
        visible_analyses = Analysis.objects.filter(Q(is_public=True) | Q(creator=user))
        analyses_with_permission = AnalysisUserObjectPermission.objects.filter(
            user=user
        ).values_list("content_object_id", flat=True)
        visible_analyses = visible_analyses | Analysis.objects.filter(
            id__in=analyses_with_permission
        )

        # Build visibility filters for extracts
        visible_extracts = Extract.objects.filter(Q(creator=user))
        extracts_with_permission = ExtractUserObjectPermission.objects.filter(
            user=user
        ).values_list("content_object_id", flat=True)
        visible_extracts = visible_extracts | Extract.objects.filter(
            id__in=extracts_with_permission
        )

        # Complex filter for annotation visibility
        # An annotation is visible if:
        # 1. It's structural (always visible if doc is visible)
        # 2. User created it
        # 3. It's not private to an analysis/extract OR user has access to that analysis/extract
        # 4. AND user has access to the document and corpus
        visibility_filter = (
            # Structural annotations (always visible if doc is readable)
            Q(structural=True)
            |
            # User's own annotations
            Q(creator=user)
            |
            # Regular annotations (no privacy fields)
            (Q(created_by_analysis__isnull=True) & Q(created_by_extract__isnull=True))
            |
            # Analysis-created annotations user can see
            (Q(created_by_analysis__in=visible_analyses))
            |
            # Extract-created annotations user can see
            (Q(created_by_extract__in=visible_extracts))
        )

        # Also need document/corpus visibility
        # Query guardian permission tables for documents and corpuses
        from django.apps import apps

        try:
            doc_perm_model = apps.get_model("documents", "documentuserobjectpermission")
            doc_permitted_ids = doc_perm_model.objects.filter(
                permission__codename="read_document", user_id=user.id
            ).values_list("content_object_id", flat=True)
        except LookupError:
            doc_permitted_ids = []

        try:
            corpus_perm_model = apps.get_model("corpuses", "corpususerobjectpermission")
            corpus_permitted_ids = corpus_perm_model.objects.filter(
                permission__codename="read_corpus", user_id=user.id
            ).values_list("content_object_id", flat=True)
        except LookupError:
            corpus_permitted_ids = []

        # Handle TWO types of annotations:
        # 1. Document-attached: have document FK set, check document visibility
        # 2. Structural via structural_set: have document=NULL, check via structural_set__documents
        doc_attached_filter = Q(document__isnull=False) & (
            Q(document__is_public=True)
            | Q(document__creator=user)
            | Q(document_id__in=doc_permitted_ids)
        )

        # Structural annotations linked via structural_set (document FK is NULL)
        # These are visible if ANY document using that structural_set is visible to user
        structural_set_filter = (
            Q(document__isnull=True)
            & Q(structural_set__isnull=False)
            & Q(structural=True)
            & (
                Q(structural_set__documents__is_public=True)
                | Q(structural_set__documents__creator=user)
                | Q(structural_set__documents__id__in=doc_permitted_ids)
            )
        )

        doc_visibility_filter = doc_attached_filter | structural_set_filter

        # Corpus visibility (for document-attached annotations with corpus)
        corpus_filter = (
            Q(corpus__isnull=True)
            | Q(corpus__is_public=True)
            | Q(corpus__creator=user)
            | Q(corpus_id__in=corpus_permitted_ids)
        )

        return qs.filter(
            visibility_filter & doc_visibility_filter & corpus_filter
        ).distinct()


class NoteQuerySet(PermissionQuerySet, VectorSearchViaEmbeddingMixin):
    """
    Custom QuerySet for Note model, combining:
      - PermissionQuerySet
      - VectorSearchViaEmbeddingMixin

    Notes inherit permissions from their parent document and corpus
    following the MIN(document_permission, corpus_permission) pattern.

    CTE support: django-cte 3.0+ provides the standalone with_cte() function
    that works on any queryset, so CTEQuerySet inheritance is no longer needed.
    """

    def visible_to_user(self, user, perm=None):
        """
        Notes inherit visibility from document + corpus.
        A note is visible if:
        1. User created it, OR
        2. Document is visible AND corpus is visible (or null)
        """
        from django.contrib.auth.models import AnonymousUser

        if user is None:
            user = AnonymousUser()

        if hasattr(user, "is_superuser") and user.is_superuser:
            return self.all()

        if user.is_anonymous:
            return self.filter(
                Q(document__is_public=True)
                & (Q(corpus__isnull=True) | Q(corpus__is_public=True))
                & Q(is_public=True)
            ).distinct()

        # Authenticated: visible if creator OR (doc visible AND corpus visible)
        doc_visible = Q(document__is_public=True) | Q(document__creator=user)
        corpus_visible = (
            Q(corpus__isnull=True) | Q(corpus__is_public=True) | Q(corpus__creator=user)
        )

        return self.filter(Q(creator=user) | (doc_visible & corpus_visible)).distinct()
