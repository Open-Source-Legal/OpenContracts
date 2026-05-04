"""Tests for the install-wide default LabelSet feature.

Covers:
- ``opencontractserver.annotations.label_set_seeds.create_default_labelset``
  (idempotent seeding, backfill of pre-existing labelsets, no-superuser path).
- ``opencontractserver.annotations.label_set_seeds.reverse_migration``.
- ``seed_default_labelset`` management command.
- The ``defaultLabelset`` GraphQL query resolver.
- The ``CreateCorpusMutation`` pre-filling ``label_set`` from the default.
"""

from io import StringIO

from django.apps import apps as live_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from graphene_django.utils.testing import GraphQLTestCase
from graphql_relay import to_global_id

from opencontractserver.annotations.label_set_seeds import (
    DEFAULT_LABELS,
    DEFAULT_LABELSET_TITLE,
    create_default_labelset,
    reverse_migration,
)
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


def _clear_seeded_labelset() -> None:
    """Remove the seeded labelset (and orphan seed labels) for test isolation.

    The annotations 0070 data migration runs once per test database build, so
    the default labelset already exists when individual tests start. Each test
    that re-runs the seeder needs a clean slate.
    """
    label_texts = [spec["text"] for spec in DEFAULT_LABELS]
    LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).delete()
    AnnotationLabel.objects.filter(
        text__in=label_texts, included_in_labelset__isnull=True
    ).delete()


class CreateDefaultLabelsetTestCase(TestCase):
    """Direct unit tests for ``create_default_labelset`` and reverse."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="seed-superuser",
            email="seed@example.com",
            password="pw",
        )

    def setUp(self) -> None:
        _clear_seeded_labelset()

    def test_creates_labelset_with_starter_labels(self) -> None:
        create_default_labelset(live_apps, schema_editor=None)

        labelset = LabelSet.objects.get(title=DEFAULT_LABELSET_TITLE)
        self.assertTrue(labelset.is_default)
        self.assertTrue(labelset.is_public)
        self.assertEqual(labelset.creator, self.superuser)
        self.assertEqual(
            labelset.annotation_labels.count(),
            len(DEFAULT_LABELS),
        )

    def test_seed_is_idempotent(self) -> None:
        create_default_labelset(live_apps, schema_editor=None)
        create_default_labelset(live_apps, schema_editor=None)

        labelsets = LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE)
        self.assertEqual(labelsets.count(), 1)
        labelset = labelsets.get()
        self.assertEqual(
            labelset.annotation_labels.count(),
            len(DEFAULT_LABELS),
        )

    def test_promotes_pre_existing_labelset_with_same_title(self) -> None:
        existing = LabelSet.objects.create(
            title=DEFAULT_LABELSET_TITLE,
            description="legacy",
            creator=self.superuser,
            is_public=False,
            is_default=False,
        )

        create_default_labelset(live_apps, schema_editor=None)

        existing.refresh_from_db()
        self.assertTrue(existing.is_default)
        self.assertTrue(existing.is_public)
        # Starter labels are added to the pre-existing labelset.
        self.assertEqual(
            existing.annotation_labels.count(),
            len(DEFAULT_LABELS),
        )

    def test_demotes_other_default_when_promoting(self) -> None:
        # Pre-existing labelset with the seed title but is_default=False.
        target = LabelSet.objects.create(
            title=DEFAULT_LABELSET_TITLE,
            description="legacy",
            creator=self.superuser,
            is_public=False,
            is_default=False,
        )
        # Some other labelset is currently the default — must be demoted to
        # satisfy the partial unique constraint.
        other = LabelSet.objects.create(
            title="Some Other Default",
            description="prior",
            creator=self.superuser,
            is_public=True,
            is_default=True,
        )

        create_default_labelset(live_apps, schema_editor=None)

        target.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(target.is_default)
        self.assertFalse(other.is_default)

    def test_no_superuser_skips_seeding(self) -> None:
        User.objects.filter(is_superuser=True).delete()

        create_default_labelset(live_apps, schema_editor=None)

        self.assertFalse(LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).exists())

    def test_reverse_migration_removes_seed(self) -> None:
        create_default_labelset(live_apps, schema_editor=None)
        self.assertTrue(LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).exists())

        reverse_migration(live_apps, schema_editor=None)

        self.assertFalse(LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).exists())
        # Orphan starter labels should also be cleaned up.
        label_texts = [spec["text"] for spec in DEFAULT_LABELS]
        self.assertFalse(AnnotationLabel.objects.filter(text__in=label_texts).exists())

    def test_reverse_migration_preserves_shared_labels(self) -> None:
        create_default_labelset(live_apps, schema_editor=None)

        # Reuse a seed label inside a different labelset — the reverse migration
        # must keep it because it's still referenced.
        kept = LabelSet.objects.create(
            title="Other Set",
            description="other",
            creator=self.superuser,
            is_public=False,
        )
        important = AnnotationLabel.objects.get(text="Important")
        kept.annotation_labels.add(important)

        reverse_migration(live_apps, schema_editor=None)

        self.assertTrue(AnnotationLabel.objects.filter(pk=important.pk).exists())


class SeedDefaultLabelsetCommandTestCase(TestCase):
    """Run the management command and verify the side effects."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="cmd-superuser",
            email="cmd@example.com",
            password="pw",
        )

    def setUp(self) -> None:
        _clear_seeded_labelset()

    def test_command_seeds_default_labelset(self) -> None:
        out = StringIO()
        call_command("seed_default_labelset", stdout=out)

        self.assertIn("Default labelset seeded.", out.getvalue())
        labelset = LabelSet.objects.get(title=DEFAULT_LABELSET_TITLE)
        self.assertTrue(labelset.is_default)
        self.assertEqual(
            labelset.annotation_labels.count(),
            len(DEFAULT_LABELS),
        )

    def test_command_is_idempotent(self) -> None:
        call_command("seed_default_labelset", stdout=StringIO())
        call_command("seed_default_labelset", stdout=StringIO())

        self.assertEqual(
            LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).count(),
            1,
        )


class DefaultLabelsetGraphQLTestCase(GraphQLTestCase):
    GRAPHQL_URL = "/graphql/"

    QUERY = """
        query {
            defaultLabelset { id title isDefault isPublic }
        }
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = User.objects.create_user(username="gqluser", password="pw")
        cls.superuser = User.objects.filter(is_superuser=True).first()
        if cls.superuser is None:
            cls.superuser = User.objects.create_superuser(
                username="gql-super",
                email="gql-super@example.com",
                password="pw",
            )

    def setUp(self) -> None:
        _clear_seeded_labelset()
        self.client.login(username="gqluser", password="pw")

    def test_returns_seeded_default(self) -> None:
        create_default_labelset(live_apps, schema_editor=None)

        response = self.query(self.QUERY)
        self.assertResponseNoErrors(response)
        node = response.json()["data"]["defaultLabelset"]
        self.assertIsNotNone(node)
        self.assertEqual(node["title"], DEFAULT_LABELSET_TITLE)
        self.assertTrue(node["isDefault"])
        self.assertTrue(node["isPublic"])

    def test_returns_null_when_no_default_seeded(self) -> None:
        # No default exists in this test (seed was cleared in setUp).
        response = self.query(self.QUERY)
        self.assertResponseNoErrors(response)
        self.assertIsNone(response.json()["data"]["defaultLabelset"])

    def test_unauthenticated_user_gets_error(self) -> None:
        self.client.logout()
        response = self.query(self.QUERY)
        self.assertGreater(len(response.json().get("errors", [])), 0)


class CreateCorpusDefaultLabelSetTestCase(GraphQLTestCase):
    """Verify CreateCorpusMutation pre-fills label_set from the default."""

    GRAPHQL_URL = "/graphql/"

    CREATE_MUTATION = """
        mutation CreateCorpus(
            $title: String!
            $description: String!
            $labelSet: String
        ) {
            createCorpus(
                title: $title
                description: $description
                labelSet: $labelSet
            ) {
                ok
                message
                objId
            }
        }
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.user = User.objects.create_user(username="creator", password="pw")
        cls.superuser = User.objects.filter(is_superuser=True).first()
        if cls.superuser is None:
            cls.superuser = User.objects.create_superuser(
                username="create-super",
                email="create-super@example.com",
                password="pw",
            )

    def setUp(self) -> None:
        _clear_seeded_labelset()
        Corpus.objects.filter(creator=self.user).delete()
        self.client.login(username="creator", password="pw")

    def _make_default_visible_to_user(self) -> LabelSet:
        create_default_labelset(live_apps, schema_editor=None)
        return LabelSet.objects.get(title=DEFAULT_LABELSET_TITLE)

    def test_omitted_label_set_is_replaced_by_default(self) -> None:
        default = self._make_default_visible_to_user()

        response = self.query(
            self.CREATE_MUTATION,
            variables={
                "title": "My Corpus",
                "description": "Pre-filled defaults",
            },
        )
        self.assertResponseNoErrors(response)
        payload = response.json()["data"]["createCorpus"]
        self.assertTrue(payload["ok"])

        corpus = Corpus.objects.get(creator=self.user, title="My Corpus")
        self.assertIsNotNone(corpus.label_set)
        self.assertEqual(corpus.label_set_id, default.pk)

    def test_explicit_label_set_takes_precedence(self) -> None:
        self._make_default_visible_to_user()
        explicit = LabelSet.objects.create(
            title="Caller's Labels",
            description="caller",
            creator=self.user,
            is_public=False,
        )

        response = self.query(
            self.CREATE_MUTATION,
            variables={
                "title": "Has Explicit",
                "description": "explicit",
                "labelSet": to_global_id("LabelSetType", explicit.pk),
            },
        )
        self.assertResponseNoErrors(response)
        self.assertTrue(response.json()["data"]["createCorpus"]["ok"])

        corpus = Corpus.objects.get(creator=self.user, title="Has Explicit")
        self.assertEqual(corpus.label_set_id, explicit.pk)

    def test_no_default_seeded_leaves_label_set_unset(self) -> None:
        # No default exists.
        response = self.query(
            self.CREATE_MUTATION,
            variables={
                "title": "No Default",
                "description": "nope",
            },
        )
        self.assertResponseNoErrors(response)
        self.assertTrue(response.json()["data"]["createCorpus"]["ok"])

        corpus = Corpus.objects.get(creator=self.user, title="No Default")
        self.assertIsNone(corpus.label_set)
