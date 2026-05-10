"""
Tests for the Reddit-style auto-assigned user handle.

Covers:
- ``handle_generator.generate_handle`` — uniqueness, no PII leakage,
  determinism under a fixed seed, suffix promotion under saturation.
- User model auto-assignment on save.
- Management command ``regenerate_user_handles`` rerun semantics.
- ``UserType.displayName`` resolver chain priority and fallback safety.
"""

from __future__ import annotations

import random
import re
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.users.handle_generator import (
    PLAIN_ATTEMPTS,
    SUFFIXED_ATTEMPTS,
    _camel_case_pair,
    generate_handle,
)
from opencontractserver.users.handle_wordlists import ADJECTIVES, NOUNS

User = get_user_model()


class _Ctx:
    """Minimal request context stand-in for Graphene test client."""

    def __init__(self, user):
        self.user = user


# ---------------------------------------------------------------------------
# Word list invariants
# ---------------------------------------------------------------------------


class HandleWordlistTests(TestCase):
    """Guardrails on the curated word lists themselves."""

    def test_wordlists_have_no_duplicates(self):
        self.assertEqual(len(set(ADJECTIVES)), len(ADJECTIVES))
        self.assertEqual(len(set(NOUNS)), len(NOUNS))

    def test_wordlists_are_lowercase_alpha_only(self):
        for word in (*ADJECTIVES, *NOUNS):
            self.assertTrue(
                word.isalpha() and word.islower(),
                f"Word list entry {word!r} must be lowercase alphabetic",
            )

    def test_wordlists_provide_a_meaningful_namespace(self):
        # Actual namespace is ~56k pairs; assert at 40k so we keep meaningful
        # protection against a careless deletion (cap the loss at ~25%) without
        # making the test brittle for legitimate small trims.
        self.assertGreaterEqual(len(ADJECTIVES) * len(NOUNS), 40_000)

    def test_wordlists_respect_length_bounds(self):
        """Each entry must be 3-12 characters, per the wordlist docstring.

        The constraint is easy to violate accidentally when extending the
        lists; pin it down so any out-of-bounds entry trips immediately.
        """
        for word in (*ADJECTIVES, *NOUNS):
            self.assertGreaterEqual(len(word), 3, f"{word!r} is too short")
            self.assertLessEqual(len(word), 12, f"{word!r} is too long")

    def test_wordlists_have_no_cross_list_overlap(self):
        """No word should appear in both lists.

        Cross-list duplicates would let the generator emit degenerate
        same-word pairs like ``cometComet``. The wordlist docstring states
        this rule explicitly; pin it down with a test so a future careless
        addition trips immediately.
        """
        overlap = set(ADJECTIVES) & set(NOUNS)
        self.assertEqual(
            overlap,
            set(),
            f"Words appear in both ADJECTIVES and NOUNS: {sorted(overlap)}",
        )


# ---------------------------------------------------------------------------
# Pure generator tests
# ---------------------------------------------------------------------------


class HandleGeneratorTests(TestCase):
    """Tests for the pure generator function with no User dependency."""

    def test_camel_case_pair_format(self):
        self.assertEqual(_camel_case_pair("clever", "fox"), "cleverFox")
        self.assertEqual(_camel_case_pair("BRAVE", "Bear"), "braveBear")

    def test_camel_case_pair_rejects_empty_inputs(self):
        with self.assertRaises(ValueError):
            _camel_case_pair("", "fox")
        with self.assertRaises(ValueError):
            _camel_case_pair("clever", "")

    def test_generate_handle_returns_camel_case_pair_against_empty_table(self):
        """Against an empty queryset the generator should never need a suffix."""
        rng = random.Random(42)
        handle = generate_handle(scope_qs=User.objects.none(), rng=rng)
        self.assertRegex(handle, r"^[a-z]+[A-Z][a-z]+$")

    def test_generate_handle_deterministic_under_fixed_seed(self):
        a = generate_handle(scope_qs=User.objects.none(), rng=random.Random(1234))
        b = generate_handle(scope_qs=User.objects.none(), rng=random.Random(1234))
        self.assertEqual(a, b)

    def test_generate_handle_yields_distinct_values_at_scale(self):
        """With a fresh RNG and an empty scope, batch generation should be diverse."""
        rng = random.Random(7)
        seen = {
            generate_handle(scope_qs=User.objects.none(), rng=rng) for _ in range(200)
        }
        # We're sampling 200 from a 50k+ namespace — uniqueness should approach 100%.
        self.assertGreater(len(seen), 195)

    def test_generate_handle_skips_existing_values(self):
        """Existing handles in the scope queryset must not be re-issued."""
        from unittest import mock

        # Shrink the wordlists to a 2x2 namespace so we can saturate it
        # deterministically and verify the only-remaining candidate is picked.
        with mock.patch(
            "opencontractserver.users.handle_generator.ADJECTIVES",
            ("brave", "clever"),
        ), mock.patch(
            "opencontractserver.users.handle_generator.NOUNS",
            ("bear", "fox"),
        ):
            User.objects.create_user(
                username="u1", email="u1@x.com", handle="braveBear"
            )
            User.objects.create_user(username="u2", email="u2@x.com", handle="braveFox")
            User.objects.create_user(
                username="u3", email="u3@x.com", handle="cleverBear"
            )

            handle = generate_handle(scope_qs=User.objects.all(), rng=random.Random(0))

        self.assertEqual(handle, "cleverFox")

    def test_generate_handle_falls_back_to_suffix_when_namespace_saturated(self):
        """When every base pair is taken the generator promotes to numeric suffix."""
        from unittest import mock

        # Patch the word lists down to a single pair so collision is forced.
        single_adj = ("clever",)
        single_noun = ("fox",)

        # Pre-populate the only available pair.
        User.objects.create_user(
            username="taken",
            email="t@example.com",
            handle="cleverFox",
        )

        with mock.patch(
            "opencontractserver.users.handle_generator.ADJECTIVES", single_adj
        ), mock.patch("opencontractserver.users.handle_generator.NOUNS", single_noun):
            handle = generate_handle(scope_qs=User.objects.all(), rng=random.Random(99))

        # Must end in digits (the suffix) and start with the only available pair.
        self.assertTrue(
            handle.startswith("cleverFox") and handle != "cleverFox",
            f"Expected suffixed cleverFox<digits>, got {handle!r}",
        )
        self.assertRegex(handle, r"\d+$")


# ---------------------------------------------------------------------------
# User.save() integration
# ---------------------------------------------------------------------------


class UserModelHandleAutoAssignTests(TestCase):
    """Auto-assignment of ``handle`` on User.save()."""

    def test_new_user_gets_handle(self):
        user = User.objects.create_user(username="new_handle_user", email="n@x.com")
        self.assertTrue(user.handle, "Newly created user should have an auto handle")
        assert user.handle is not None
        self.assertRegex(user.handle, r"^[a-z]+[A-Z][a-z]+(\d+)?$")

    def test_handle_is_unique_per_user(self):
        u1 = User.objects.create_user(username="u1", email="u1@x.com")
        u2 = User.objects.create_user(username="u2", email="u2@x.com")
        self.assertNotEqual(u1.handle, u2.handle)

    def test_existing_handle_not_overwritten_on_resave(self):
        user = User.objects.create_user(username="stable", email="s@x.com")
        original = user.handle
        user.email = "changed@x.com"
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.handle, original)

    def test_handle_does_not_leak_pii_or_oauth_id(self):
        """A user whose username looks like an Auth0 ``provider|sub`` must still
        get a clean auto-assigned handle that contains none of that string."""
        user = User.objects.create_user(
            username="auth0|abc123-def-456",
            email="oauth@x.com",
        )
        assert user.handle is not None
        self.assertNotIn("auth0", user.handle.lower())
        self.assertNotIn("|", user.handle)
        self.assertNotIn("abc123", user.handle)

    def test_slug_does_not_leak_oauth_id(self):
        """An OAuth/social user's slug must never be derived from the raw
        ``provider|sub`` username — it must be based on the auto-assigned
        handle instead."""
        user = User.objects.create_user(
            username="google-oauth2|114688257717759010643",
            email="goog@x.com",
        )
        assert user.slug is not None, "slug must be set"
        assert user.handle is not None, "handle must be set"
        self.assertNotIn("google-oauth2", user.slug)
        self.assertNotIn("114688", user.slug)
        self.assertNotIn("|", user.slug)
        # The slug must match the handle (or be a handle-derived variant).
        self.assertTrue(
            user.slug == user.handle or user.slug.startswith(user.handle + "-"),
            f"Expected slug based on handle {user.handle!r}, got {user.slug!r}",
        )

    def test_slug_matches_handle_for_new_social_user(self):
        """For a brand-new social user the slug is generated from the handle
        in the same save() call, so slug and handle share the same base."""
        user = User.objects.create_user(
            username="auth0|xyz987",
            email="auth0user@x.com",
            is_social_user=True,
        )
        assert user.handle is not None, "handle must be set"
        assert user.slug is not None, "slug must be set"
        # Slug must be handle or handle with a collision suffix like "handle-2".
        self.assertTrue(
            user.slug == user.handle or user.slug.startswith(user.handle + "-"),
            f"slug {user.slug!r} does not match handle {user.handle!r}",
        )

    def test_anonymous_user_save_skips_handle_assignment(self):
        """The django-guardian Anonymous account is a system row; it must
        never receive an auto-handle so the migration / management command /
        save() guards stay symmetric. django-guardian seeds this row at
        startup, so we work with the existing user rather than creating one.
        """
        anon, _ = User.objects.get_or_create(username="Anonymous")
        # Make sure no prior test fixture leaked a handle onto Anonymous.
        User.objects.filter(pk=anon.pk).update(handle=None)
        anon.refresh_from_db()
        anon.email = "anon@x.com"
        anon.save()
        anon.refresh_from_db()
        self.assertIsNone(
            anon.handle,
            f"Anonymous user must not receive a handle (got {anon.handle!r})",
        )

    def test_regenerate_command_skips_anonymous_user(self):
        """The management command's ``--reroll-all`` / missing-fill modes must
        also skip Anonymous so its handle stays None even after a forced reroll.
        """
        anon, _ = User.objects.get_or_create(username="Anonymous")
        User.objects.filter(pk=anon.pk).update(handle=None)
        anon.refresh_from_db()
        self.assertIsNone(anon.handle)

        out = StringIO()
        call_command("regenerate_user_handles", "--reroll-all", stdout=out)

        anon.refresh_from_db()
        self.assertIsNone(
            anon.handle,
            "Anonymous handle must remain None even under --reroll-all",
        )


# ---------------------------------------------------------------------------
# displayName resolver chain
# ---------------------------------------------------------------------------


_DISPLAY_NAME_QUERY = """
query Me {
  me {
    id
    displayName
  }
}
"""


class DisplayNameResolverTests(TestCase):
    """Resolution-chain priority for ``UserType.displayName``.

    The resolver returns the slug-only public path for non-self viewers
    (see ``_is_self_view`` in ``config/graphql/user_types``); to exercise
    the rich self-view chain we must construct an info mock whose
    ``context.user`` *is* the user being resolved.
    """

    class _SelfInfo:
        """Minimal Graphene info stand-in that passes ``_is_self_view``."""

        def __init__(self, user):
            self.context = type("Ctx", (), {"user": user})()

    @classmethod
    def _resolve_for(cls, user) -> str:
        # Calling the resolver directly avoids depending on a `me`-style query
        # we may not control, while still exercising the production code path.
        from config.graphql.user_types import UserType

        return UserType.resolve_display_name(user, info=cls._SelfInfo(user))

    def test_name_takes_priority(self):
        user = User.objects.create_user(
            username="auth0|abc",
            email="prio@x.com",
            name="Ada Lovelace",
            given_name="Ada",
            family_name="Lovelace",
            first_name="Ada",
            last_name="Lovelace",
        )
        self.assertEqual(self._resolve_for(user), "Ada Lovelace")

    def test_given_family_used_when_name_blank(self):
        user = User.objects.create_user(
            username="auth0|abc",
            email="gf@x.com",
            given_name="Grace",
            family_name="Hopper",
        )
        self.assertEqual(self._resolve_for(user), "Grace Hopper")

    def test_first_last_used_when_given_family_blank(self):
        user = User.objects.create_user(
            username="auth0|abc",
            email="fl@x.com",
            first_name="Alan",
            last_name="Turing",
        )
        self.assertEqual(self._resolve_for(user), "Alan Turing")

    def test_handle_used_when_no_name_fields_set(self):
        user = User.objects.create_user(username="auth0|abc", email="h@x.com")
        # Auth0-style username should NOT surface; the auto-assigned handle should.
        result = self._resolve_for(user)
        self.assertEqual(result, user.handle)
        self.assertNotIn("|", result)

    def test_username_preferred_over_redacted_when_not_oauth_style(self):
        user = User.objects.create_user(username="alice", email="a@x.com")
        # ``user.save()`` would re-trigger auto-assignment, so clear via
        # ``QuerySet.update`` (which bypasses ``save()``) to surface the
        # username branch.
        User.objects.filter(pk=user.pk).update(handle=None)
        user.refresh_from_db()
        self.assertEqual(self._resolve_for(user), "alice")

    def test_redacted_fallback_when_everything_missing(self):
        # ``is_social_user=True`` is the gate that routes a ``|``-containing
        # username through the OAuth-sub redaction; without it the resolver
        # would return the username verbatim (legitimate per
        # ``UserUnicodeUsernameValidator`` for locally-chosen usernames).
        user = User.objects.create_user(
            username="auth0|abcdef0123",
            email="r@x.com",
            is_social_user=True,
        )
        # Strip the auto-handle so we hit the redacted branch.
        User.objects.filter(pk=user.pk).update(handle=None)
        user.refresh_from_db()
        # Resolver returns the last 6 chars of the sub (after stripping the
        # provider prefix), per ``OAUTH_SUB_DISPLAY_SUFFIX_LENGTH``.
        self.assertEqual(self._resolve_for(user), "user_ef0123")

    def test_display_name_query_exposes_field_in_schema(self):
        """The GraphQL schema must expose ``displayName`` on UserType.

        Exercises the public ``me`` query, which is the simplest path that
        returns a ``UserType`` to a Graphene test client and so guards the
        schema wiring without depending on Auth0 / login.
        """
        user = User.objects.create_user(
            username="schema_check",
            email="sc@x.com",
            name="Schema User",
        )
        client = Client(schema, context_value=_Ctx(user))
        result = client.execute(_DISPLAY_NAME_QUERY)
        self.assertNotIn("errors", result, msg=str(result))
        self.assertEqual(
            result["data"]["me"]["displayName"],
            "Schema User",
        )


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------


class RegenerateUserHandlesCommandTests(TestCase):
    """Smoke tests for the ``regenerate_user_handles`` management command."""

    def _run(self, *args: str) -> str:
        out = StringIO()
        call_command("regenerate_user_handles", *args, stdout=out)
        return out.getvalue()

    def test_default_mode_only_fills_missing(self):
        clean = User.objects.create_user(username="clean", email="c@x.com")
        original = clean.handle
        missing = User.objects.create_user(username="missing", email="m@x.com")
        User.objects.filter(pk=missing.pk).update(handle=None)

        output = self._run()

        clean.refresh_from_db()
        missing.refresh_from_db()
        self.assertEqual(clean.handle, original, "Existing handle must be preserved")
        self.assertTrue(missing.handle, "Missing handle must be backfilled")
        self.assertIn("updated 1 user(s)", output)

    def test_dry_run_does_not_write(self):
        u = User.objects.create_user(username="dry", email="d@x.com")
        User.objects.filter(pk=u.pk).update(handle=None)

        output = self._run("--dry-run")

        u.refresh_from_db()
        self.assertIsNone(u.handle, "Dry run must not commit changes")
        self.assertIn("would update", output)

    def test_reroll_all_and_reroll_suffixed_are_mutually_exclusive(self):
        """Passing both flags is an operator mistake — fail fast instead of
        silently letting ``--reroll-all`` win."""
        with self.assertRaises(CommandError) as ctx:
            self._run("--reroll-all", "--reroll-suffixed")
        self.assertIn("mutually exclusive", str(ctx.exception))

    def test_reroll_suffixed_targets_only_numeric_tails(self):
        plain = User.objects.create_user(username="plain", email="p@x.com")
        plain.handle = "cleverFox"
        plain.save(update_fields=["handle"])

        suffixed = User.objects.create_user(username="suffixed", email="s@x.com")
        suffixed.handle = "cleverFox42"
        suffixed.save(update_fields=["handle"])

        self._run("--reroll-suffixed")

        plain.refresh_from_db()
        suffixed.refresh_from_db()
        self.assertEqual(plain.handle, "cleverFox", "Plain handle must be untouched")
        self.assertNotEqual(
            suffixed.handle,
            "cleverFox42",
            "Suffixed handle must be re-rolled",
        )


# ---------------------------------------------------------------------------
# Sanity-check generator tunables — this is a defence against accidental
# regressions if someone shrinks the word list or attempts cap.
# ---------------------------------------------------------------------------


class HandleGeneratorTunablesTests(TestCase):
    def test_attempt_caps_are_positive(self):
        self.assertGreater(PLAIN_ATTEMPTS, 0)
        self.assertGreater(SUFFIXED_ATTEMPTS, 0)

    def test_suffix_format_is_numeric(self):
        # Sanity: the suffix part of the regex used by --reroll-suffixed must
        # accept what the generator emits when forced into the suffix branch.
        from unittest import mock

        with mock.patch(
            "opencontractserver.users.handle_generator.ADJECTIVES", ("only",)
        ), mock.patch("opencontractserver.users.handle_generator.NOUNS", ("one",)):
            User.objects.create_user(username="a", email="a@x.com", handle="onlyOne")
            handle = generate_handle(scope_qs=User.objects.all(), rng=random.Random(0))
        self.assertTrue(re.search(r"\d+$", handle), f"Expected suffix on {handle!r}")


# ---------------------------------------------------------------------------
# regenerate_user_slugs management command
# ---------------------------------------------------------------------------


class RegenerateUserSlugsCommandTests(TestCase):
    """Verify the ``regenerate_user_slugs`` management command detects and
    repairs OAuth-sub-derived slugs without touching legitimate slugs."""

    def _make_oauth_user_with_bad_slug(self, username, email):
        """Create a user whose slug was synthetically derived from their OAuth username."""
        from opencontractserver.shared.slug_utils import sanitize_slug

        user = User.objects.create_user(username=username, email=email)
        # Force the slug to the old (broken) OAuth-derived value so we can test repair.
        bad_slug = sanitize_slug(username, max_length=64)
        User.objects.filter(pk=user.pk).update(slug=bad_slug)
        user.refresh_from_db()
        return user

    def test_dry_run_does_not_write(self):
        user = self._make_oauth_user_with_bad_slug(
            "google-oauth2|111222333", "dry@x.com"
        )
        original_slug = user.slug
        out = StringIO()
        call_command("regenerate_user_slugs", "--dry-run", stdout=out)
        user.refresh_from_db()
        self.assertEqual(user.slug, original_slug)
        self.assertIn("would update", out.getvalue())

    def test_replaces_oauth_derived_slug_with_handle_slug(self):
        user = self._make_oauth_user_with_bad_slug(
            "google-oauth2|444555666", "fix@x.com"
        )
        old_slug = user.slug
        self.assertIn("google-oauth2", old_slug)

        call_command("regenerate_user_slugs", stdout=StringIO())
        user.refresh_from_db()

        self.assertNotIn("google-oauth2", user.slug)
        self.assertNotIn("444555666", user.slug)
        # New slug must be based on the user's handle.
        self.assertTrue(
            user.slug == user.handle or user.slug.startswith(user.handle + "-"),
            f"New slug {user.slug!r} not derived from handle {user.handle!r}",
        )

    def test_leaves_clean_slug_untouched(self):
        """A social user who already has a handle-based slug must not be changed."""
        user = User.objects.create_user(
            username="auth0|cleanslug",
            email="clean@x.com",
            is_social_user=True,
        )
        # After our fix, the slug is already handle-derived.
        assert user.slug is not None, "slug must be set after fix"
        original_slug: str = user.slug
        self.assertNotIn("auth0", original_slug)

        call_command("regenerate_user_slugs", stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.slug, original_slug)
