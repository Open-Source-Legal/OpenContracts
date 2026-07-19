"""Coverage-driving tests for ``config/graphql/core/permissions.py``.

The ported ``AnnotatePermissionsForReadMixin`` resolvers
(``resolve_my_permissions`` / ``resolve_object_shared_with`` /
``resolve_is_published``) and the shared ``get_anonymous_user_id`` cache carry
several defensive branches — cached-failure sentinels, frozen/immutable
``info.context`` fallbacks, and swallowed-exception logging — that the rest of
the suite never happens to exercise because production requests always give
these functions a well-behaved, mutable context. This module targets those
branches directly.

One documented, deliberately-preserved quirk drives several tests here:
``resolve_object_shared_with`` reads
``permission_annotations.get("this_model_permission_id_map", {})`` off the
*top level* of ``info.context.permission_annotations``, but the only code that
ever populates that dict (``_annotations_for_model``) writes it nested under
``"<app_label>.<model_name>"``. In a real request the top-level key is
therefore always absent, the id map is always ``{}``, and any actually-shared
object raises ``KeyError`` inside the loop. This is a faithful, non-regressing
port of the graphene-era mixin's behaviour (see git blame on
``config/graphql/permissioning/permission_annotator/mixins.py`` prior to the
strawberry migration) — not something to "fix" here. Tests below either pin
that ``KeyError`` directly (the realistic path) or, where noted, pre-seed the
top-level key the same way the graphene-era sibling test
(``test_user_privacy.py::ObjectSharedWithPrivacyTestCase``) does, to unit-test
the per-user merge logic in isolation from the quirk.

A second, unrelated pre-existing key-name mismatch: ``resolve_my_permissions``
reads ``model_permissions.get("can_publish_model_type", False)``, but
``get_permissions_for_user_on_model_in_app`` (the helper that builds
``model_permissions``) returns the flag under ``"can_publish"``. That mismatch
also predates the strawberry port (same lookup in the graphene mixin), so the
"can-publish" branch below is exercised via a mock of the helper rather than a
real permission grant — the real helper can never trigger it in production.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from guardian.shortcuts import assign_perm

from config.graphql.core.permissions import (
    _ANON_USER_LOOKUP_FAILED,
    get_anonymous_user_id,
    resolve_is_published,
    resolve_my_permissions,
    resolve_object_shared_with,
)
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _Ctx:
    """Mutable stand-in for ``info.context``.

    ``permission_annotations`` is only set when explicitly given — omitting it
    (the default) reproduces a fresh request context, where the resolver's own
    lazy-init path (``_permission_annotations``) creates and attaches it.
    """

    def __init__(self, user, permission_annotations=None):
        self.user = user
        # Declared eagerly (rather than only set on demand) so mypy sees the
        # attribute; ``None`` is behaviourally identical to "unset" for
        # ``get_anonymous_user_id``'s ``getattr(..., "_anon_user_id", None)``.
        self._anon_user_id: int | None = None
        if permission_annotations is not None:
            self.permission_annotations = permission_annotations


class _Info:
    def __init__(self, context):
        self.context = context


class _FrozenCtx:
    """Slotted context that raises ``AttributeError`` on any unknown attribute.

    Stands in for the "frozen/immutable context (some tests)" scenario the
    resolvers explicitly guard against when memoising onto ``info.context``.
    """

    __slots__ = ("user",)

    def __init__(self, user):
        self.user = user


class _BoomBoolUser:
    """A user-like object whose truthiness check itself raises.

    Simulates a broken lazy user proxy (e.g. a lazily-resolved auth backend
    that fails mid-request) to exercise ``resolve_my_permissions``'s
    outermost defensive ``except`` — the last-resort guard wrapping the
    entire permission computation, not just the per-permission id-map lookup.
    """

    id = -999999

    def __bool__(self) -> bool:
        raise RuntimeError("simulated user-proxy failure")


class GetAnonymousUserIdCoverageTestCase(TestCase):
    """Edge branches of the per-request anonymous-user-id cache."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="ganon_user", password="pw")

    def test_returns_none_when_previously_cached_as_failed(self):
        ctx = _Ctx(self.user)
        ctx._anon_user_id = _ANON_USER_LOOKUP_FAILED
        self.assertIsNone(get_anonymous_user_id(_Info(ctx)))

    def test_broken_lookup_caches_failure_sentinel_on_mutable_context(self):
        ctx = _Ctx(self.user)
        with mock.patch(
            "config.graphql.core.permissions.User.get_anonymous",
            side_effect=RuntimeError("no anonymous user configured"),
        ):
            result = get_anonymous_user_id(_Info(ctx))
        self.assertIsNone(result)
        self.assertEqual(ctx._anon_user_id, _ANON_USER_LOOKUP_FAILED)

    def test_broken_lookup_on_frozen_context_does_not_raise(self):
        ctx = _FrozenCtx(self.user)
        with mock.patch(
            "config.graphql.core.permissions.User.get_anonymous",
            side_effect=RuntimeError("no anonymous user configured"),
        ):
            result = get_anonymous_user_id(_Info(ctx))
        self.assertIsNone(result)

    def test_successful_lookup_on_frozen_context_still_returns_id(self):
        ctx = _FrozenCtx(self.user)
        result = get_anonymous_user_id(_Info(ctx))
        self.assertIsNotNone(result)
        self.assertEqual(result, User.get_anonymous().id)  # type: ignore[attr-defined]


class ResolveMyPermissionsCoverageTestCase(TestCase):
    """Branch coverage for ``resolve_my_permissions``."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="rmp_owner", password="pw")
        self.viewer = User.objects.create_user(username="rmp_viewer", password="pw")
        self.corpus = Corpus.objects.create(
            title="RMP Coverage Corpus",
            creator=self.owner,
            backend_lock=False,
            is_public=False,
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.ALL])

    def test_anonymous_viewer_short_circuits_to_empty(self):
        anon = User.get_anonymous()  # type: ignore[attr-defined]
        result = resolve_my_permissions(self.corpus, _Info(_Ctx(anon)))
        self.assertEqual(result, [])

    def test_precomputed_optimizer_flags_map_to_full_permission_set(self):
        # An Annotation must belong to a document or a structural set.
        doc = Document.objects.create(creator=self.owner, title="RMP Coverage Doc")
        annotation = Annotation.objects.create(
            document=doc, creator=self.owner, raw_text="", page=0, json={}
        )
        for flag in (
            "_can_read",
            "_can_create",
            "_can_update",
            "_can_delete",
            "_can_comment",
            "_can_publish",
        ):
            setattr(annotation, flag, True)

        result = set(resolve_my_permissions(annotation, _Info(_Ctx(self.viewer))))
        self.assertEqual(
            result,
            {
                "read_annotation",
                "create_annotation",
                "update_annotation",
                "remove_annotation",
                "comment_annotation",
                "publish_annotation",
            },
        )

    def test_guardianless_model_delegates_to_creator_based_helper(self):
        label = AnnotationLabel.objects.create(
            text="Guardianless", creator=self.owner, is_public=False
        )
        result = set(resolve_my_permissions(label, _Info(_Ctx(self.owner))))
        self.assertEqual(
            result,
            {
                "create_annotationlabel",
                "read_annotationlabel",
                "update_annotationlabel",
                "remove_annotationlabel",
            },
        )

    def test_public_instance_grants_read_even_without_any_grant(self):
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        result = resolve_my_permissions(self.corpus, _Info(_Ctx(self.viewer)))
        self.assertIn("read_corpus", result)

    def test_id_map_lookup_failures_for_user_and_group_perms_are_swallowed(self):
        group = Group.objects.create(name="rmp-idmap-group")
        self.viewer.groups.add(group)
        set_permissions_for_obj_to_user(
            self.viewer, self.corpus, [PermissionTypes.READ]
        )
        assign_perm("update_corpus", group, self.corpus)

        with mock.patch(
            "config.graphql.core.permissions.get_permissions_for_user_on_model_in_app",
            return_value={
                "this_user_group_ids": [group.id],
                # Empty on purpose — mirrors the always-empty map production
                # actually produces via ``_annotations_for_model``, forcing
                # the per-permission KeyError this test pins.
                "this_model_permission_id_map": {},
                "can_publish_model_type": False,
            },
        ):
            result = resolve_my_permissions(self.corpus, _Info(_Ctx(self.viewer)))

        # Neither the user- nor the group-granted permission survives: both
        # id-map lookups raised KeyError internally and were logged, not
        # propagated. The corpus itself isn't public, so nothing else adds a
        # permission either.
        self.assertEqual(result, [])

    def test_can_publish_flag_from_annotator_sets_publish_permission(self):
        # ``can_publish_model_type`` can never be True via the real helper
        # (see module docstring) — mocked here to exercise the resolver's own
        # branch in isolation from that pre-existing key-name mismatch.
        with mock.patch(
            "config.graphql.core.permissions.get_permissions_for_user_on_model_in_app",
            return_value={
                "this_user_group_ids": [],
                "this_model_permission_id_map": {},
                "can_publish_model_type": True,
            },
        ):
            result = resolve_my_permissions(self.corpus, _Info(_Ctx(self.viewer)))
        self.assertIn("publish_corpus", result)

    def test_annotator_helper_failure_is_logged_and_swallowed(self):
        with mock.patch(
            "config.graphql.core.permissions.get_permissions_for_user_on_model_in_app",
            side_effect=RuntimeError("boom"),
        ):
            result = resolve_my_permissions(self.corpus, _Info(_Ctx(self.viewer)))
        self.assertEqual(result, [])

    def test_outer_exception_from_broken_user_proxy_is_swallowed(self):
        ctx = _Ctx(_BoomBoolUser())
        # Bypass the anon-id short circuit deterministically rather than
        # depending on guardian's anonymous-user id happening to differ.
        ctx._anon_user_id = _ANON_USER_LOOKUP_FAILED
        result = resolve_my_permissions(self.corpus, _Info(ctx))
        self.assertEqual(result, [])


class ResolveObjectSharedWithCoverageTestCase(TestCase):
    """Branch coverage for ``resolve_object_shared_with``."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="rosw_owner", password="pw")
        self.viewer = User.objects.create_user(username="rosw_viewer", password="pw")
        self.collaborator = User.objects.create_user(
            username="rosw_collab", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="ROSW Coverage Corpus",
            creator=self.owner,
            backend_lock=False,
            is_public=False,
        )
        # Deliberately NOT granting the owner any guardian permission here:
        # ``resolve_object_shared_with`` reads every row of
        # ``corpususerobjectpermission_set`` unfiltered by user (its job is to
        # enumerate every collaborator), so an owner grant would add extra
        # rows whose permission ids aren't in the tests' synthetic id map —
        # raising KeyError before the multi-grant merge test below ever
        # reaches its own assertions.
        corpus_ct = ContentType.objects.get_for_model(Corpus)
        self.read_perm = Permission.objects.get(
            content_type=corpus_ct, codename="read_corpus"
        )
        self.update_perm = Permission.objects.get(
            content_type=corpus_ct, codename="update_corpus"
        )

    def test_anonymous_viewer_short_circuits_to_empty(self):
        anon = User.get_anonymous()  # type: ignore[attr-defined]
        result = resolve_object_shared_with(self.corpus, _Info(_Ctx(anon)))
        self.assertEqual(result, [])

    def test_guardianless_model_returns_empty(self):
        label = AnnotationLabel.objects.create(text="NoGuardianTables", creator=self.owner)
        result = resolve_object_shared_with(label, _Info(_Ctx(self.viewer)))
        self.assertEqual(result, [])

    def test_realistic_context_raises_keyerror_for_an_actual_share(self):
        """Pins the preserved graphene-parity quirk described in the module
        docstring: a genuine (non-fabricated) request context never has the
        top-level ``this_model_permission_id_map`` key populated, so the id
        map the loop reads is always ``{}`` and a real shared permission
        raises ``KeyError`` rather than resolving to a codename."""
        assign_perm(self.read_perm, self.collaborator, self.corpus)
        ctx = _Ctx(self.viewer)  # no permission_annotations pre-seeded
        with self.assertRaises(KeyError):
            resolve_object_shared_with(self.corpus, _Info(ctx))

    def test_merges_multiple_grants_for_the_same_user(self):
        """Unit-tests the per-user permission-merge loop by pre-seeding
        ``permission_annotations`` the same way the graphene-era sibling test
        (``test_user_privacy.py::ObjectSharedWithPrivacyTestCase``) does —
        a synthetic context, not a claim about the realistic path pinned
        above."""
        assign_perm(self.read_perm, self.collaborator, self.corpus)
        assign_perm(self.update_perm, self.collaborator, self.corpus)
        annotations = {
            "this_model_permission_id_map": {
                self.read_perm.id: "read_corpus",
                self.update_perm.id: "update_corpus",
            },
        }
        ctx = _Ctx(self.viewer, permission_annotations=annotations)

        result = resolve_object_shared_with(self.corpus, _Info(ctx))

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["slug"], self.collaborator.slug)
        self.assertEqual(set(entry["permissions"]), {"read_corpus", "update_corpus"})

    def test_frozen_context_swallows_attribute_error(self):
        ctx = _FrozenCtx(self.viewer)
        result = resolve_object_shared_with(self.corpus, _Info(ctx))
        self.assertEqual(result, [])


class ResolveIsPublishedCoverageTestCase(TestCase):
    """Branch coverage for ``resolve_is_published``."""

    def setUp(self) -> None:
        from django.conf import settings

        self.public_group_name = settings.DEFAULT_PERMISSIONS_GROUP
        self.owner = User.objects.create_user(username="rip_owner", password="pw")
        self.corpus = Corpus.objects.create(
            title="RIP Coverage Corpus",
            creator=self.owner,
            backend_lock=False,
            is_public=False,
        )

    def test_true_when_shared_with_the_public_permissions_group(self):
        group, _ = Group.objects.get_or_create(name=self.public_group_name)
        assign_perm("read_corpus", group, self.corpus)
        self.assertTrue(resolve_is_published(self.corpus, _Info(_Ctx(self.owner))))

    def test_false_without_the_public_permissions_group(self):
        self.assertFalse(resolve_is_published(self.corpus, _Info(_Ctx(self.owner))))
