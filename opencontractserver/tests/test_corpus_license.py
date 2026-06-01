"""
Tests for corpus license field validation and GraphQL mutations.

Covers:
- Create corpus with a standard CC license
- Create corpus with CUSTOM license + URL
- Create corpus with CUSTOM license without URL (should fail)
- Update corpus license fields
- URL scheme restriction (only http/https)
- Stale license_link cleared when switching away from CUSTOM
- license_link without license is cleared
- Model-level clean() validation
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
from graphene.test import Client as GrapheneClient
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


class TestContext:
    def __init__(self, user):
        self.user = user


CREATE_MUTATION = """
    mutation CreateCorpus(
        $title: String!,
        $description: String,
        $license: String,
        $licenseLink: String
    ) {
        createCorpus(
            title: $title,
            description: $description,
            license: $license,
            licenseLink: $licenseLink
        ) {
            ok
            message
            objId
        }
    }
"""

UPDATE_MUTATION = """
    mutation UpdateCorpus(
        $id: String!,
        $license: String,
        $licenseLink: String
    ) {
        updateCorpus(
            id: $id,
            license: $license,
            licenseLink: $licenseLink
        ) {
            ok
            message
        }
    }
"""


class TestCorpusLicenseCreate(TestCase):
    """Test license handling during corpus creation."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="licensetest", password="testpass"
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )

    def test_create_with_cc_license(self):
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "CC Licensed Corpus",
                "description": "A test corpus",
                "license": "CC-BY-4.0",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])

        corpus = Corpus.objects.get(creator=self.user, title="CC Licensed Corpus")
        self.assertEqual(corpus.license, "CC-BY-4.0")

    def test_create_with_custom_license_and_url(self):
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "Custom Licensed Corpus",
                "description": "A test corpus",
                "license": "CUSTOM",
                "licenseLink": "https://example.com/my-license",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])

        corpus = Corpus.objects.get(creator=self.user, title="Custom Licensed Corpus")
        self.assertEqual(corpus.license, "CUSTOM")
        self.assertEqual(corpus.license_link, "https://example.com/my-license")

    def test_create_custom_without_url_fails(self):
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "Missing URL Corpus",
                "description": "A test corpus",
                "license": "CUSTOM",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpus"]["ok"])
        self.assertIn("license_link", result["data"]["createCorpus"]["message"])

    def test_create_with_no_license(self):
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "No License Corpus",
                "description": "A test corpus",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])

        corpus = Corpus.objects.get(creator=self.user, title="No License Corpus")
        self.assertEqual(corpus.license, "")


class TestCorpusLicenseUpdate(TestCase):
    """Test license handling during corpus updates."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="licenseupdatetest", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Update Test Corpus",
            description="A test corpus",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )
        self.global_id = to_global_id("CorpusType", self.corpus.id)

    def test_update_to_cc_license(self):
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "license": "CC-BY-SA-4.0",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpus"]["ok"])

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license, "CC-BY-SA-4.0")

    def test_update_to_custom_with_url(self):
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "license": "CUSTOM",
                "licenseLink": "https://example.com/custom",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpus"]["ok"])

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license, "CUSTOM")
        self.assertEqual(self.corpus.license_link, "https://example.com/custom")

    def test_update_to_custom_without_url_fails(self):
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "license": "CUSTOM",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpus"]["ok"])
        self.assertIn("license_link", result["data"]["updateCorpus"]["message"])

    def test_clear_license(self):
        self.corpus.license = "CC-BY-4.0"
        self.corpus.save()

        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "license": "",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpus"]["ok"])

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license, "")


class TestCorpusLicenseLinkScheme(TestCase):
    """Test that license_link only accepts http/https URLs."""

    def setUp(self):
        self.user = User.objects.create_user(username="schemetest", password="testpass")
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )

    def test_ftp_url_rejected(self):
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "FTP License Corpus",
                "description": "A test corpus",
                "license": "CUSTOM",
                "licenseLink": "ftp://example.com/license",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpus"]["ok"])

    def test_https_url_accepted(self):
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "HTTPS License Corpus",
                "description": "A test corpus",
                "license": "CUSTOM",
                "licenseLink": "https://example.com/license",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])


class TestCorpusLicenseStaleLinkClearing(TestCase):
    """Test that stale license_link values are cleared by the backend."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stalecleantest", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Stale Link Test Corpus",
            description="A test corpus",
            creator=self.user,
            license="CUSTOM",
            license_link="https://example.com/old-license",
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )
        self.global_id = to_global_id("CorpusType", self.corpus.id)

    def test_switch_from_custom_to_standard_clears_link(self):
        """Switching from CUSTOM to a standard license should clear license_link."""
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "license": "CC-BY-4.0",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpus"]["ok"])

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license, "CC-BY-4.0")
        self.assertEqual(self.corpus.license_link, "")

    def test_clear_license_clears_link(self):
        """Clearing the license entirely should also clear license_link."""
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "license": "",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpus"]["ok"])

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license, "")
        self.assertEqual(self.corpus.license_link, "")


class TestCorpusLicenseInvalidValue(TestCase):
    """Test that invalid license values are rejected."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="invalidlicensetest", password="testpass"
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )

    def test_create_with_invalid_license_rejected(self):
        """Creating a corpus with an invalid license value should fail."""
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "Invalid License Corpus",
                "description": "A test corpus",
                "license": "MIT",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpus"]["ok"])
        self.assertIn("license", result["data"]["createCorpus"]["message"])

    def test_update_with_invalid_license_rejected(self):
        """Updating a corpus with an invalid license value should fail."""
        corpus = Corpus.objects.create(
            title="Valid Corpus",
            description="Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user,
            corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        global_id = to_global_id("CorpusType", corpus.id)

        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": global_id,
                "license": "GPL-3.0",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpus"]["ok"])
        self.assertIn("license", result["data"]["updateCorpus"]["message"])


class TestCorpusLicenseOrphanedLink(TestCase):
    """Test that license_link cannot be orphaned alongside a non-CUSTOM license."""

    def setUp(self):
        self.user = User.objects.create_user(username="orphantest", password="testpass")
        self.corpus = Corpus.objects.create(
            title="Orphan Test Corpus",
            description="A test corpus",
            creator=self.user,
            license="CC-BY-4.0",
            license_link="",
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )
        self.global_id = to_global_id("CorpusType", self.corpus.id)

    def test_license_link_without_license_when_not_custom_rejected(self):
        """Sending licenseLink without license when existing license is not CUSTOM
        should be rejected."""
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "licenseLink": "https://example.com/orphan",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["updateCorpus"]["ok"])
        self.assertIn("license_link", result["data"]["updateCorpus"]["message"])

        # Verify the link was NOT saved
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license_link, "")


class TestCorpusLicensePartialUpdate(TestCase):
    """Test partial update scenarios for license fields."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="partialupdatetest", password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Partial Update Corpus",
            description="A test corpus",
            creator=self.user,
            license="CUSTOM",
            license_link="https://example.com/original",
        )
        set_permissions_for_obj_to_user(
            self.user,
            self.corpus,
            [PermissionTypes.CRUD, PermissionTypes.PUBLISH, PermissionTypes.PERMISSION],
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )
        self.global_id = to_global_id("CorpusType", self.corpus.id)

    def test_update_only_license_link_when_custom(self):
        """Updating only licenseLink when license is already CUSTOM should work."""
        result = self.graphene_client.execute(
            UPDATE_MUTATION,
            variable_values={
                "id": self.global_id,
                "licenseLink": "https://example.com/updated",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["updateCorpus"]["ok"])

        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.license, "CUSTOM")
        self.assertEqual(self.corpus.license_link, "https://example.com/updated")


class TestCorpusLicenseURLValidation(TestCase):
    """Test URL format validation for license_link."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="urlvalidtest", password="testpass"
        )
        self.graphene_client = GrapheneClient(
            schema, context_value=TestContext(self.user)
        )

    def test_http_url_accepted(self):
        """HTTP scheme URLs should be accepted."""
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "HTTP License Corpus",
                "description": "A test corpus",
                "license": "CUSTOM",
                "licenseLink": "http://example.com/license",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])

    def test_invalid_url_format_rejected(self):
        """Non-URL strings should be rejected."""
        result = self.graphene_client.execute(
            CREATE_MUTATION,
            variable_values={
                "title": "Bad URL Corpus",
                "description": "A test corpus",
                "license": "CUSTOM",
                "licenseLink": "not-a-url",
            },
        )
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["createCorpus"]["ok"])
        self.assertIn("license_link", result["data"]["createCorpus"]["message"])


class TestCorpusLicenseModelClean(TestCase):
    """Test model-level clean() validation for license fields."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="modelcleantest", password="testpass"
        )

    def test_clean_custom_without_link_raises(self):
        """Model clean() should reject CUSTOM license without license_link."""
        corpus = Corpus(
            title="Model Clean Test",
            description="Test",
            creator=self.user,
            license="CUSTOM",
            license_link="",
        )
        with self.assertRaises(ValidationError) as ctx:
            corpus.full_clean()
        self.assertIn("license_link", ctx.exception.message_dict)

    def test_clean_custom_with_link_passes(self):
        """Model clean() should accept CUSTOM license with valid license_link."""
        corpus = Corpus(
            title="Model Clean Test OK",
            description="Test",
            creator=self.user,
            license="CUSTOM",
            license_link="https://example.com/license",
        )
        # Should not raise
        corpus.full_clean()

    def test_clean_standard_license_clears_link(self):
        """Model clean() should clear license_link for non-CUSTOM licenses."""
        corpus = Corpus(
            title="Model Clean Clear Test",
            description="Test",
            creator=self.user,
            license="CC-BY-4.0",
            license_link="https://stale.example.com",
        )
        corpus.full_clean()
        self.assertEqual(corpus.license_link, "")

    def test_clean_empty_license_clears_link(self):
        """Model clean() should clear license_link when license is empty."""
        corpus = Corpus(
            title="Model Clean Empty Test",
            description="Test",
            creator=self.user,
            license="",
            license_link="https://orphan.example.com",
        )
        corpus.full_clean()
        self.assertEqual(corpus.license_link, "")

    def test_clean_invalid_license_raises(self):
        """Model clean() should reject invalid license values."""
        corpus = Corpus(
            title="Model Clean Invalid Test",
            description="Test",
            creator=self.user,
            license="MIT",
        )
        with self.assertRaises(ValidationError) as ctx:
            corpus.full_clean()
        self.assertIn("license", ctx.exception.message_dict)

    def test_clean_standard_license_without_link_preserves_empty(self):
        """Model clean() should not modify license_link when it is already empty."""
        corpus = Corpus(
            title="Model Clean NoOp Test",
            description="Test",
            creator=self.user,
            license="CC-BY-4.0",
            license_link="",
        )
        corpus.full_clean()
        self.assertEqual(corpus.license_link, "")
