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
