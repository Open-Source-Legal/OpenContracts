"""
Tests for the user privacy / "slug-only" GraphQL policy.

The contract these tests pin down:

1. Personally identifying fields on ``UserType`` (``email``, ``name``,
   ``firstName``, ``lastName``, ``givenName``, ``familyName``, ``username``,
   ``phone``, ``emailVerified``, ``isSocialUser``) are returned **only** when
   the authenticated requester *is* the user being resolved. Non-self viewers
   — including superusers, anonymous viewers, and other authenticated users —
   always see ``null``.

2. ``displayName`` is the privacy-preserving identifier. Non-self viewers
   always receive the user's ``slug`` (with a stable ``user_<pk>`` redaction
   when slug is unset). Self-views still walk the rich profile-name fallback.

3. ``User.__str__`` does not include the email address — it surfaces the
   slug (or username as a last-resort fallback).

4. ``AnnotatePermissionsForReadMixin.resolve_object_shared_with`` exposes
   only ``id``, ``slug``, and the permission list — never ``email`` or
   ``username``.

These assertions guard against silent regressions if a future change adds
new model fields (which ``DjangoObjectType`` would otherwise auto-expose)
or relaxes the resolver gate.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class _Ctx:
    """Minimal request-like context for the graphene test client.

    Production requests carry a ``permission_annotations`` dict populated
    by the permissioning middleware (see
    ``config.graphql.permissioning.permission_annotator.middleware``).
    The mixin's ``resolve_object_shared_with`` references that attribute
    in a ``logger.info`` call *before* its try/except, so omitting it
    blows the resolver up. We provide an empty dict here so resolvers
    behave as if the corpus simply has no shared-with entries — which is
    sufficient for this suite, since we assert on the *shape* of the
    response, not on a populated share list.
    """

    def __init__(self, user, permission_annotations=None):
        self.user = user
        self.permission_annotations = (
            permission_annotations if permission_annotations is not None else {}
        )


# All PII-bearing fields on ``UserType``. Reused for both the self-view
# (``me``) and cross-user (``userBySlug``) probes — the resolver gate is
# the same regardless of how a UserType lands in a response.
_USER_PII_FIELDS = """
    id
    slug
    displayName
    email
    username
    name
    firstName
    lastName
    givenName
    familyName
    phone
    emailVerified
    isSocialUser
"""

_ME_QUERY = """
    query Me {
        me {
%s
        }
    }
""" % _USER_PII_FIELDS

_USER_BY_SLUG_QUERY = """
    query UserBySlug($slug: String!) {
        userBySlug(slug: $slug) {
%s
        }
    }
""" % _USER_PII_FIELDS


class UserTypePrivacyTestCase(TestCase):
    """PII-field gating on ``UserType``."""

    def setUp(self) -> None:
        # ``alice`` is the resolution target; assertions below check what
        # different requesters see when they query alice's profile.
        self.alice = User.objects.create_user(
            username="alice",
            password="pw-alice",
            email="alice@example.com",
            name="Alice Anderson",
            first_name="Alice",
            last_name="Anderson",
            given_name="Alice",
            family_name="Anderson",
            phone="+1-555-0100",
            email_verified=True,
            is_social_user=False,
            is_profile_public=True,
        )
        self.bob = User.objects.create_user(
            username="bob",
            password="pw-bob",
            email="bob@example.com",
            name="Bob Brown",
            is_profile_public=True,
        )
        self.admin = User.objects.create_superuser(
            username="admin",
            password="pw-admin",
            email="admin@example.com",
        )

    def _query_alice_as(self, requester) -> dict:
        """Resolve alice through the cross-user ``userBySlug`` query.

        Uses ``userBySlug`` rather than ``me`` so we exercise the
        non-self code path in the resolver gate, which is the
        privacy-critical branch.
        """
        client = Client(schema, context_value=_Ctx(requester))
        result = client.execute(
            _USER_BY_SLUG_QUERY, variable_values={"slug": self.alice.slug}
        )
        self.assertNotIn("errors", result, msg=result)
        node = result["data"]["userBySlug"]
        self.assertIsNotNone(
            node,
            msg=(
                "userBySlug returned null — alice's profile is public so "
                "every requester (including anonymous) should resolve."
            ),
        )
        return node

    def _query_self_as_me(self, requester) -> dict:
        """Resolve the requester via ``me`` for self-view assertions."""
        client = Client(schema, context_value=_Ctx(requester))
        result = client.execute(_ME_QUERY)
        self.assertNotIn("errors", result, msg=result)
        return result["data"]["me"]

    # ------------------------------------------------------------------
    # Self-view: alice queries herself — gets full PII
    # ------------------------------------------------------------------
    def test_self_view_returns_full_pii(self) -> None:
        node = self._query_self_as_me(self.alice)

        self.assertEqual(node["email"], "alice@example.com")
        self.assertEqual(node["username"], "alice")
        self.assertEqual(node["name"], "Alice Anderson")
        self.assertEqual(node["firstName"], "Alice")
        self.assertEqual(node["lastName"], "Anderson")
        self.assertEqual(node["givenName"], "Alice")
        self.assertEqual(node["familyName"], "Anderson")
        self.assertEqual(node["phone"], "+1-555-0100")
        self.assertTrue(node["emailVerified"])
        self.assertFalse(node["isSocialUser"])

    def test_self_view_display_name_uses_full_name(self) -> None:
        # Self-views walk the existing rich fallback — ``name`` wins over
        # slug, so settings UIs can still greet the user by name.
        node = self._query_self_as_me(self.alice)
        self.assertEqual(node["displayName"], "Alice Anderson")

    def test_self_view_via_user_by_slug_also_returns_full_pii(self) -> None:
        # Belt-and-suspenders: the resolver gate keys off ``info.context.user``,
        # not the field path, so resolving alice through ``userBySlug`` while
        # *being* alice must also surface the full PII.
        node = self._query_alice_as(self.alice)
        self.assertEqual(node["email"], "alice@example.com")
        self.assertEqual(node["displayName"], "Alice Anderson")

    # ------------------------------------------------------------------
    # Non-self viewer: bob queries alice — gets null for every PII field
    # ------------------------------------------------------------------
    def test_other_authenticated_user_sees_only_slug(self) -> None:
        node = self._query_alice_as(self.bob)

        # All PII redacted to null
        for field in (
            "email",
            "username",
            "name",
            "firstName",
            "lastName",
            "givenName",
            "familyName",
            "phone",
            "emailVerified",
            "isSocialUser",
        ):
            self.assertIsNone(
                node[field], msg=f"{field} leaked to non-self viewer: {node[field]!r}"
            )

        # Slug is the only public identifier
        self.assertEqual(node["slug"], self.alice.slug)
        self.assertEqual(node["displayName"], self.alice.slug)

    def test_other_authenticated_user_never_sees_real_name_in_display_name(
        self,
    ) -> None:
        node = self._query_alice_as(self.bob)
        self.assertNotIn("Alice", node["displayName"])
        self.assertNotIn("Anderson", node["displayName"])

    # ------------------------------------------------------------------
    # Superuser: still treated as non-self — admin DB tooling, not the
    # GraphQL API, is the path for PII access.
    # ------------------------------------------------------------------
    def test_superuser_does_not_see_other_users_pii(self) -> None:
        node = self._query_alice_as(self.admin)

        for field in ("email", "username", "name", "firstName", "lastName"):
            self.assertIsNone(
                node[field],
                msg=(
                    f"Superuser saw {field} via GraphQL — PII access is "
                    "reserved for Django admin, not the public API."
                ),
            )
        self.assertEqual(node["displayName"], self.alice.slug)

    # ------------------------------------------------------------------
    # Anonymous viewer: same redaction; unauthenticated equals "not self".
    # ------------------------------------------------------------------
    def test_anonymous_viewer_sees_only_slug(self) -> None:
        node = self._query_alice_as(AnonymousUser())

        for field in ("email", "username", "name", "firstName", "lastName"):
            self.assertIsNone(node[field])
        self.assertEqual(node["displayName"], self.alice.slug)

    # ------------------------------------------------------------------
    # ``canImportCorpus`` is account-tier sensitive — same self-only
    # gate as the PII fields above.
    # ------------------------------------------------------------------
    def test_can_import_corpus_is_null_for_other_authenticated_user(self) -> None:
        # Reuse alice's profile as the resolution target; bob queries it.
        # ``canImportCorpus`` reflects ``is_usage_capped`` — leaking it
        # cross-user would let any client probe whether another account
        # is paid/free. Must redact to ``null`` for non-self viewers.
        from graphene.test import Client

        from config.graphql.schema import schema

        query = """
            query UserBySlug($slug: String!) {
                userBySlug(slug: $slug) {
                    canImportCorpus
                }
            }
        """
        client = Client(schema, context_value=_Ctx(self.bob))
        result = client.execute(query, variable_values={"slug": self.alice.slug})
        self.assertNotIn("errors", result, msg=result)
        self.assertIsNone(result["data"]["userBySlug"]["canImportCorpus"])

    def test_can_import_corpus_is_null_for_anonymous_viewer(self) -> None:
        from graphene.test import Client

        from config.graphql.schema import schema

        query = """
            query UserBySlug($slug: String!) {
                userBySlug(slug: $slug) {
                    canImportCorpus
                }
            }
        """
        client = Client(schema, context_value=_Ctx(AnonymousUser()))
        result = client.execute(query, variable_values={"slug": self.alice.slug})
        self.assertNotIn("errors", result, msg=result)
        self.assertIsNone(result["data"]["userBySlug"]["canImportCorpus"])

    def test_can_import_corpus_returns_boolean_for_self_view(self) -> None:
        # Self-view: alice queries herself via ``me`` — gets a real
        # boolean (not ``null``). The exact value depends on
        # ``is_usage_capped`` × ``USAGE_CAPPED_USER_CAN_IMPORT_CORPUS``;
        # we just assert the shape here.
        from graphene.test import Client

        from config.graphql.schema import schema

        query = "query Me { me { canImportCorpus } }"
        client = Client(schema, context_value=_Ctx(self.alice))
        result = client.execute(query)
        self.assertNotIn("errors", result, msg=result)
        self.assertIsInstance(result["data"]["me"]["canImportCorpus"], bool)

    # ------------------------------------------------------------------
    # ``isUsageCapped`` is the underlying account-tier flag that
    # ``canImportCorpus`` derives from. Without an explicit resolver the
    # raw model field would surface unredacted, letting any authenticated
    # caller infer paid/free tier — the gate parallels ``canImportCorpus``.
    # ------------------------------------------------------------------
    def test_is_usage_capped_is_null_for_other_authenticated_user(self) -> None:
        from graphene.test import Client

        from config.graphql.schema import schema

        query = """
            query UserBySlug($slug: String!) {
                userBySlug(slug: $slug) {
                    isUsageCapped
                }
            }
        """
        client = Client(schema, context_value=_Ctx(self.bob))
        result = client.execute(query, variable_values={"slug": self.alice.slug})
        self.assertNotIn("errors", result, msg=result)
        self.assertIsNone(result["data"]["userBySlug"]["isUsageCapped"])

    def test_is_usage_capped_is_null_for_anonymous_viewer(self) -> None:
        from graphene.test import Client

        from config.graphql.schema import schema

        query = """
            query UserBySlug($slug: String!) {
                userBySlug(slug: $slug) {
                    isUsageCapped
                }
            }
        """
        client = Client(schema, context_value=_Ctx(AnonymousUser()))
        result = client.execute(query, variable_values={"slug": self.alice.slug})
        self.assertNotIn("errors", result, msg=result)
        self.assertIsNone(result["data"]["userBySlug"]["isUsageCapped"])

    def test_is_usage_capped_returns_boolean_for_self_view(self) -> None:
        from graphene.test import Client

        from config.graphql.schema import schema

        query = "query Me { me { isUsageCapped } }"
        client = Client(schema, context_value=_Ctx(self.alice))
        result = client.execute(query)
        self.assertNotIn("errors", result, msg=result)
        self.assertIsInstance(result["data"]["me"]["isUsageCapped"], bool)

    # ------------------------------------------------------------------
    # Inactive sessions: even when ``is_authenticated`` reports True (it
    # does, statically, on every User instance), a deactivated account
    # whose session cookie is still live must not pass ``_is_self_view``.
    # ------------------------------------------------------------------
    def test_deactivated_user_does_not_see_their_own_pii(self) -> None:
        self.alice.is_active = False
        self.alice.save(update_fields=["is_active"])
        node = self._query_self_as_me(self.alice)
        # ``me`` returns ``null`` for unauthenticated requesters via the
        # resolve_me short-circuit; for a deactivated user the
        # ``is_authenticated`` flag is still True, so ``me`` does
        # resolve, but every PII field must redact.
        if node is None:
            return  # short-circuit branch — also acceptable
        for field in ("email", "username", "name", "firstName", "lastName"):
            self.assertIsNone(
                node[field],
                msg=(
                    f"Deactivated user saw {field}={node[field]!r} via me — "
                    "_is_self_view should fail closed when is_active=False."
                ),
            )


class UserDisplayNameSlugFallbackTestCase(TestCase):
    """Cover the redacted-handle path when ``slug`` is unset.

    The cross-user lookup query (``userBySlug``) requires a slug to find
    the target, so this test invokes the resolver via the relay node
    interface (which walks ``UserType`` directly) to exercise the
    no-slug fallback branch in ``resolve_display_name``.
    """

    def test_non_self_view_falls_back_to_redacted_handle(self) -> None:
        # Bypass the slug-generating ``save()`` so we can simulate the
        # pre-migration state where slug is NULL.
        target = User.objects.create_user(username="target", password="pw")
        User.objects.filter(pk=target.pk).update(slug=None)
        target.refresh_from_db()
        self.assertIsNone(target.slug)

        viewer = User.objects.create_user(username="viewer", password="pw")

        # Drive the resolver directly — this is the same code path the
        # GraphQL layer runs, just without the schema indirection. Lets
        # us exercise the redacted-handle branch without relying on a
        # query that would itself need a slug to find the user.
        from config.graphql.user_types import UserType

        class _Info:
            def __init__(self, ctx):
                self.context = ctx

        # ``UserType.resolve_display_name`` is typed as a method on the
        # graphene type, but at runtime ``self`` is the underlying Django
        # ``User`` instance — that's how DjangoObjectType binds resolvers.
        display = UserType.resolve_display_name(target, _Info(_Ctx(viewer)))  # type: ignore[arg-type]
        # Stable redacted handle: never returns the username (which could
        # be an OAuth ``sub``) and never returns ``""`` or ``None``.
        self.assertTrue(display.startswith("user_"))
        self.assertNotIn("target", display)


class UserStrPrivacyTestCase(TestCase):
    """``__str__`` must not embed email — it leaks into admin / logs."""

    def test_str_uses_slug_not_email(self) -> None:
        user = User.objects.create_user(
            username="charlie",
            email="charlie@example.com",
            password="pw",
        )
        rendered = str(user)
        self.assertNotIn("@", rendered)
        self.assertNotIn("charlie@example.com", rendered)
        # Slug auto-generated from username; ``__str__`` returns it directly.
        self.assertEqual(rendered, user.slug)

    def test_str_falls_back_to_username_when_slug_missing(self) -> None:
        user = User.objects.create_user(username="dave", password="pw")
        # Force slug to NULL via raw update — simulates pre-migration data.
        User.objects.filter(pk=user.pk).update(slug=None)
        user.refresh_from_db()
        self.assertEqual(str(user), "dave")


class ObjectSharedWithPrivacyTestCase(TestCase):
    """The ``object_shared_with`` annotation must not leak email/username.

    Previously, every viewer of a shared corpus / document / labelset saw
    the email and username of every collaborator. This test pins the new
    slug-only contract by invoking the mixin's resolver directly with a
    realistic permission-annotations payload — bypassing the GraphQL
    schema means we don't depend on the test client matching production
    middleware exactly.
    """

    def setUp(self) -> None:
        from django.contrib.auth.models import Permission
        from guardian.shortcuts import assign_perm

        self.owner = User.objects.create_user(username="owner", password="pw")
        self.collaborator = User.objects.create_user(
            username="collab",
            email="collab@example.com",
            password="pw",
        )
        self.viewer = User.objects.create_user(username="viewer", password="pw")

        self.corpus = Corpus.objects.create(
            title="Shared Corpus",
            creator=self.owner,
            backend_lock=False,
            is_public=True,
        )
        # Grant the collaborator a guardian object permission so they
        # appear in ``object_shared_with``.
        self.read_perm = Permission.objects.get(codename="read_corpus")
        assign_perm(self.read_perm, self.collaborator, self.corpus)

    def _resolve_shared_with(self) -> list[dict]:
        from config.graphql.graphene_types import CorpusType

        # Production middleware populates ``permission_annotations`` with
        # an entry mapping the GraphQL type's full name to its permission
        # ID → codename map. Mirror that shape here so the resolver can
        # translate the guardian permission row into a codename.
        annotations = {
            "this_model_permission_id_map": {
                self.read_perm.id: "read_corpus",
            },
        }
        ctx = _Ctx(self.viewer, permission_annotations=annotations)

        class _Info:
            def __init__(self, context):
                self.context = context

        return CorpusType.resolve_object_shared_with(self.corpus, _Info(ctx))

    def test_shared_with_returns_slug_only(self) -> None:
        shared = self._resolve_shared_with()
        self.assertEqual(
            len(shared),
            1,
            msg=(
                "Expected exactly one shared-with entry for the "
                "collaborator; got: %r" % (shared,)
            ),
        )
        entry = shared[0]
        self.assertEqual(entry["slug"], self.collaborator.slug)
        self.assertEqual(entry["id"], self.collaborator.pk)
        self.assertEqual(entry["permissions"], ["read_corpus"])
        # The PII guarantee — neither email nor username leaks here.
        self.assertNotIn("email", entry)
        self.assertNotIn("username", entry)

    def test_shared_with_does_not_emit_collaborator_email(self) -> None:
        # Belt-and-suspenders: even if the entry shape changes, no value
        # in the payload should equal the collaborator's email.
        shared = self._resolve_shared_with()
        flattened = repr(shared)
        self.assertNotIn(self.collaborator.email, flattened)
        self.assertNotIn("collab@example.com", flattened)
