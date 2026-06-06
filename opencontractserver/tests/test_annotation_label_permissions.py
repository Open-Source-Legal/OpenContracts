"""Tests for AnnotationLabel ``my_permissions`` inheritance.

AnnotationLabels deliberately carry no django-guardian object-permission
tables of their own — access is governed by the LabelSet(s) that include the
label (the LabelSet is the permissioned entity). ``AnnotationLabelType``
therefore resolves ``my_permissions`` by inheriting the caller's permissions
from every LabelSet the label belongs to, mapping ``*_labelset`` codenames
onto ``*_annotationlabel``.

Regression coverage for the production log error:
``resolve_my_permissions() - 'AnnotationLabel' object has no attribute
'annotationlabeluserobjectpermission_set'`` — the generic mixin used to assume
guardian tables exist and crashed (caught + logged) for guardian-less models.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from config.graphql.annotation_types import AnnotationLabelType
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _Ctx:
    """Mutable stand-in for ``info.context`` (the anon-id helper caches on it)."""

    def __init__(self, user):
        self.user = user


class _Info:
    def __init__(self, user):
        self.context = _Ctx(user)


class AnnotationLabelMyPermissionsTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="ll_owner", password="pw")
        self.collaborator = User.objects.create_user(
            username="ll_collab", password="pw"
        )
        self.stranger = User.objects.create_user(username="ll_stranger", password="pw")

        self.labelset = LabelSet.objects.create(
            title="LS", creator=self.owner, is_public=False
        )
        self.label = AnnotationLabel.objects.create(
            text="Important", creator=self.owner, is_public=False
        )
        self.labelset.annotation_labels.add(self.label)

        # The owner gets full CRUD on the labelset; the collaborator only READ.
        # (Guardian-backed models don't auto-grant the creator — grant explicitly.)
        set_permissions_for_obj_to_user(
            self.owner, self.labelset, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.collaborator, self.labelset, [PermissionTypes.READ]
        )

    def _perms(self, user, label=None):
        # graphene passes the model instance as ``self`` to the resolver; mypy
        # types the unbound method's first arg as the GraphQL type, hence the
        # ignore.
        return set(
            AnnotationLabelType.resolve_my_permissions(
                label or self.label, _Info(user)  # type: ignore[arg-type]
            )
        )

    def test_owner_inherits_crud_from_labelset(self):
        perms = self._perms(self.owner)
        self.assertIn("read_annotationlabel", perms)
        self.assertIn("update_annotationlabel", perms)
        self.assertIn("create_annotationlabel", perms)
        self.assertIn("remove_annotationlabel", perms)
        # Mapping must not leak the source model name.
        self.assertFalse(any("labelset" in p for p in perms))

    def test_collaborator_inherits_read_only_from_labelset(self):
        self.assertEqual(self._perms(self.collaborator), {"read_annotationlabel"})

    def test_stranger_gets_no_permissions(self):
        self.assertEqual(self._perms(self.stranger), set())

    def test_public_label_is_always_readable(self):
        public_label = AnnotationLabel.objects.create(
            text="Pub", creator=self.owner, is_public=True
        )
        # Not in any labelset, but public -> read for anyone.
        self.assertEqual(
            self._perms(self.stranger, label=public_label),
            {"read_annotationlabel"},
        )

    def test_builtin_readonly_label_is_readable(self):
        builtin = AnnotationLabel.objects.create(
            text="Builtin", creator=self.owner, is_public=False, read_only=True
        )
        self.assertIn("read_annotationlabel", self._perms(self.stranger, label=builtin))
