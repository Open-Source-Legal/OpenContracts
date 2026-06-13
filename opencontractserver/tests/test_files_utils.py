"""Tests for opencontractserver.utils.files helpers."""

from django.test import SimpleTestCase

from opencontractserver.utils.files import read_field_file_text


class _FakeOpenedFile:
    """Stand-in for the object ``FieldFile.open()`` yields.

    Acts as a context manager whose ``read()`` returns a preset payload,
    letting us simulate both ``str`` (local FileSystemStorage) and ``bytes``
    (S3/GCS via django-storages) return values without real storage.
    """

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


class _FakeFieldFile:
    """Minimal ``FieldFile`` look-alike exposing only ``open()``."""

    def __init__(self, payload):
        self._payload = payload

    def open(self, mode="r"):
        return _FakeOpenedFile(self._payload)


class ReadFieldFileTextTests(SimpleTestCase):
    def test_decodes_bytes_from_cloud_backend(self):
        """S3Boto3Storage / GoogleCloudStorage return bytes even in 'r' mode."""
        result = read_field_file_text(_FakeFieldFile("héllo ✓".encode()))
        self.assertIsInstance(result, str)
        self.assertEqual(result, "héllo ✓")

    def test_passes_through_str_from_local_backend(self):
        """FileSystemStorage honors text mode and already returns str."""
        result = read_field_file_text(_FakeFieldFile("local text"))
        self.assertIsInstance(result, str)
        self.assertEqual(result, "local text")

    def test_respects_errors_policy(self):
        """errors='ignore' drops undecodable bytes instead of raising."""
        result = read_field_file_text(_FakeFieldFile(b"abc\xffdef"), errors="ignore")
        self.assertEqual(result, "abcdef")

    def test_strict_errors_raises_on_invalid_bytes(self):
        """Default strict policy surfaces decode errors to the caller."""
        with self.assertRaises(UnicodeDecodeError):
            read_field_file_text(_FakeFieldFile(b"abc\xffdef"))


class SharedUrlCacheTtlTests(SimpleTestCase):
    """The shared signed-URL cache must never outlive the signatures it holds.

    Regression: the AWS settings branch derived the signed-URL lifetime from
    ``_AWS_EXPIRY`` (the HTTP CacheControl max-age, 7 days) instead of the
    actual presign lifetime (``AWS_QUERYSTRING_EXPIRE``, 1 hour) — the cache
    served dead 403 links for up to 5 hours.
    """

    def test_clamps_to_half_signature_lifetime(self):
        from opencontractserver.utils.files import clamp_shared_url_cache_ttl

        self.assertEqual(clamp_shared_url_cache_ttl(21600, 3600), 1800)

    def test_passthrough_when_under_half_lifetime(self):
        from opencontractserver.utils.files import clamp_shared_url_cache_ttl

        self.assertEqual(clamp_shared_url_cache_ttl(900, 3600), 900)

    def test_unsigned_storage_passes_through(self):
        from opencontractserver.utils.files import clamp_shared_url_cache_ttl

        # LOCAL storage: URLs are unsigned; an operator-chosen TTL stands.
        self.assertEqual(clamp_shared_url_cache_ttl(1234, 0), 1234)

    def test_never_negative(self):
        from opencontractserver.utils.files import clamp_shared_url_cache_ttl

        self.assertEqual(clamp_shared_url_cache_ttl(-5, 3600), 0)
