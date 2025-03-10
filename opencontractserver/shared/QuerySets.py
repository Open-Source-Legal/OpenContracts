from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from tree_queries.query import TreeQuerySet

from opencontractserver.utils.permissioning import filter_queryset_by_permission

User = get_user_model()


class PermissionQuerySet(models.QuerySet):
    def visible_to_user(self, user, perm: str = "read") -> models.QuerySet:
        """
        Return objects visible to the user using unified logic:
          1. Superuser: all objects.
          2. Anonymous: only objects with is_public==True.
          3. Authenticated: objects where the user is the creator, or objects that are public,
             or objects for which the user has explicit guardian permission (e.g. "read_<model>").
          4. Additionally, if the model has a direct link to a corpus (or reverse relation 'corpus_set'),
             include objects whose corpus is visible to the user.
        """
        return filter_queryset_by_permission(self, user, perm)

    def approved(self):
        return self.filter(approved=True)

    def recent(self, days=30):
        recent_date = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created__gte=recent_date)

    def by_creator(self, creator):
        return self.filter(creator=creator)


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
        qs = filter_queryset_by_permission(self, user, permission="read")
        return qs.with_tree_fields() if hasattr(self, "with_tree_fields") else qs

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
        return filter_queryset_by_permission(self, user, permission="read")
