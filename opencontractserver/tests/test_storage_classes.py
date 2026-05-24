"""
Unit tests for storage classes without full Django setup.
"""

import unittest


class TestStorageClasses(unittest.TestCase):
    """Test custom storage classes."""

    def test_aws_storage_classes_exist(self):
        """Test that AWS storage classes can be imported."""
        from opencontractserver.utils.storages import (
            MediaRootS3Boto3Storage,
            StaticRootS3Boto3Storage,
        )

        # Check class attributes
        self.assertEqual(StaticRootS3Boto3Storage.location, "static")
        self.assertEqual(StaticRootS3Boto3Storage.default_acl, "public-read")

        self.assertEqual(MediaRootS3Boto3Storage.location, "media")
        self.assertFalse(MediaRootS3Boto3Storage.file_overwrite)

    def test_gcp_storage_classes_exist(self):
        """Test that GCP storage classes can be imported."""
        from opencontractserver.utils.storages import (
            MediaRootGoogleCloudStorage,
            StaticRootGoogleCloudStorage,
        )

        # Check class attributes
        self.assertEqual(StaticRootGoogleCloudStorage.location, "static")
        # default_acl is None to support GCS buckets with uniform bucket-level access
        # Public access should be configured at the bucket level via IAM policies
        self.assertIsNone(StaticRootGoogleCloudStorage.default_acl)

        self.assertEqual(MediaRootGoogleCloudStorage.location, "media")
        self.assertFalse(MediaRootGoogleCloudStorage.file_overwrite)
        self.assertIsNone(MediaRootGoogleCloudStorage.default_acl)

    def test_gcp_media_storage_security_headers(self):
        """Test that GCP media storage adds security headers."""
        from opencontractserver.utils.storages import MediaRootGoogleCloudStorage

        storage = MediaRootGoogleCloudStorage()
        params = storage.get_object_parameters("test_file.pdf")

        # Check security headers
        self.assertIn("content_disposition", params)
        self.assertIn(
            'attachment; filename="test_file.pdf"', params["content_disposition"]
        )
        self.assertIn("metadata", params)
        self.assertEqual(params["metadata"]["X-Content-Type-Options"], "nosniff")
        self.assertEqual(params["metadata"]["X-Frame-Options"], "DENY")

        # Check content type
        self.assertEqual(params.get("content_type"), "application/pdf")

    def test_gcp_static_storage_content_type(self):
        """Test that GCP static storage sets proper content types."""
        from opencontractserver.utils.storages import StaticRootGoogleCloudStorage

        storage = StaticRootGoogleCloudStorage()

        # Test CSS file
        params = storage.get_object_parameters("styles.css")
        self.assertEqual(params.get("content_type"), "text/css")

        # Test JS file. Either form is RFC-valid; Python 3.12 updated the
        # mimetypes db to return ``text/javascript`` (RFC 9239 — the legacy
        # ``application/javascript`` is deprecated but still in use on
        # Python 3.11). Accept both so the test passes on either runtime.
        params = storage.get_object_parameters("script.js")
        self.assertIn(
            params.get("content_type"),
            ("text/javascript", "application/javascript"),
        )

        # Test image file
        params = storage.get_object_parameters("logo.png")
        self.assertEqual(params.get("content_type"), "image/png")


if __name__ == "__main__":
    unittest.main()
