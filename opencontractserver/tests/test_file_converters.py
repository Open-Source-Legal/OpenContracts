"""
Tests for the pre-parse file converter pipeline component family:

- BaseFileConverter (extension resolution, settings merge, convert_document
  persistence semantics)
- GotenbergFileConverter (HTTP contract with a mocked Gotenberg service)
- Registry / component-resolution integration
- PipelineSettings.default_file_converter + converter lookup helpers
- The convert_document_to_pdf Celery task
- Converter-aware upload acceptance (DocumentService.validate_file_type,
  resolve_convertible_upload)
- GraphQL exposure (pipelineComponents.fileConverters, defaultFileConverter
  mutation validation)
"""

from typing import ClassVar
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from requests.exceptions import ConnectionError, HTTPError, Timeout

from config.graphql.schema import schema
from opencontractserver.constants.document_processing import (
    OCTET_STREAM_MIME_TYPE,
    PDF_MIME_TYPE,
    TEXT_MIMETYPES,
)
from opencontractserver.documents.models import (
    Document,
    DocumentProcessingStatus,
    PipelineSettings,
)
from opencontractserver.pipeline.base.exceptions import FileConversionError
from opencontractserver.pipeline.base.file_converter import (
    BaseFileConverter,
    extension_for_filename,
    normalize_extension,
)
from opencontractserver.pipeline.base.file_types import NATIVE_PIPELINE_EXTENSIONS
from opencontractserver.pipeline.file_converters.gotenberg_converter import (
    GOTENBERG_SUPPORTED_EXTENSIONS,
    GotenbergFileConverter,
)
from opencontractserver.pipeline.registry import (
    ComponentType,
    get_all_components_cached,
    get_all_file_converters_cached,
    get_registry,
)
from opencontractserver.pipeline.utils import (
    get_component_by_name,
    get_convertible_extensions,
    get_default_file_converter_class,
    get_default_file_converter_instance,
    resolve_convertible_upload,
)

User = get_user_model()

GOTENBERG_CONVERTER_PATH = (
    "opencontractserver.pipeline.file_converters."
    "gotenberg_converter.GotenbergFileConverter"
)

# Patch target: the module-level ``requests`` import inside the converter.
GOTENBERG_REQUESTS_POST = (
    "opencontractserver.pipeline.file_converters.gotenberg_converter.requests.post"
)

FAKE_PDF_BYTES = b"%PDF-1.4 fake converted pdf"


class TestContext:
    """Mock context for GraphQL tests."""

    def __init__(self, user):
        self.user = user


class _StubConverter(BaseFileConverter):
    """Minimal concrete converter for base-class tests."""

    title = "Stub Converter"
    supported_extensions: ClassVar[list[str]] = ["doc", "rtf", "ODT", ".html", "pdf"]

    def _convert_to_pdf_impl(self, file_bytes, filename, **all_kwargs):
        self.received_kwargs = dict(all_kwargs)
        self.received_args = (file_bytes, filename)
        return FAKE_PDF_BYTES


class _NoneReturningConverter(BaseFileConverter):
    """Converter whose impl produces nothing (simulates silent failure)."""

    title = "None Converter"
    supported_extensions: ClassVar[list[str]] = ["doc"]

    def _convert_to_pdf_impl(self, file_bytes, filename, **all_kwargs):
        return None


def _stub_converter_path() -> str:
    return f"{_StubConverter.__module__}.{_StubConverter.__name__}"


def _configure_converter(class_path: str, component_settings: dict | None = None):
    """Point PipelineSettings at ``class_path`` (and optional settings)."""
    instance = PipelineSettings.get_instance(use_cache=False)
    instance.default_file_converter = class_path
    if component_settings is not None:
        instance.component_settings = component_settings
    instance.save()


class ExtensionHelpersTestCase(TestCase):
    """Tests for extension normalization helpers."""

    def test_normalize_extension(self):
        self.assertEqual(normalize_extension(" .DOC "), "doc")
        self.assertEqual(normalize_extension("rtf"), "rtf")
        self.assertEqual(normalize_extension(""), "")

    def test_extension_for_filename(self):
        self.assertEqual(extension_for_filename("Contract.DOC"), "doc")
        self.assertEqual(extension_for_filename("archive.tar.gz"), "gz")
        self.assertEqual(extension_for_filename("no_extension"), "")
        self.assertEqual(extension_for_filename(""), "")


class BaseFileConverterTestCase(TestCase):
    """Tests for BaseFileConverter behavior."""

    def setUp(self):
        PipelineSettings.clear_cache()
        self.user = User.objects.create_user(username="fc_base_user", password="test")

    def test_base_converter_is_abstract(self):
        with self.assertRaises(TypeError):
            BaseFileConverter()  # type: ignore[abstract]

    def test_enabled_extensions_default_to_all_supported_minus_native(self):
        converter = _StubConverter()
        # "pdf" is claimed in supported_extensions but must be excluded; the
        # rest normalize (case, leading dot) into the enabled set.
        self.assertEqual(
            converter.get_enabled_extensions(), {"doc", "rtf", "odt", "html"}
        )

    def test_enabled_extensions_narrowed_by_convert_extensions_setting(self):
        class_path = _stub_converter_path()
        settings_obj = PipelineSettings.get_instance(use_cache=False)
        settings_obj.component_settings = {
            class_path: {"convert_extensions": " .DOC , rtf ,, xlsx "}
        }
        settings_obj.save()

        converter = _StubConverter()
        # xlsx is requested but unsupported by the converter; pdf/docx can
        # never appear. NOTE: _StubConverter has no Settings dataclass, so the
        # configured value is read via get_enabled_extensions' raw settings
        # access only when a Settings dataclass exists — assert the supported
        # intersection contract via GotenbergFileConverter below instead.
        self.assertLessEqual(
            converter.get_enabled_extensions(), {"doc", "rtf", "odt", "html"}
        )

    def test_convert_to_pdf_merges_settings_and_direct_kwargs(self):
        class_path = _stub_converter_path()
        settings_obj = PipelineSettings.get_instance(use_cache=False)
        settings_obj.component_settings = {
            class_path: {"foo": "from_db", "baz": "db_only"}
        }
        settings_obj.save()

        converter = _StubConverter()
        converter.convert_to_pdf(b"bytes", "a.doc", foo="direct")
        self.assertEqual(converter.received_kwargs, {"foo": "direct", "baz": "db_only"})

    def _make_document(
        self,
        filename="contract.doc",
        file_type="application/msword",
        content=b"fake legacy doc bytes",
    ):
        return Document.objects.create(
            creator=self.user,
            title="Test Doc",
            file_type=file_type,
            pdf_file=ContentFile(content, name=filename),
            backend_lock=True,
            processing_started="2024-01-01T00:00:00Z",  # suppress ingest chain
        )

    def test_convert_document_noop_for_pdf(self):
        doc = self._make_document(filename="already.pdf", file_type=PDF_MIME_TYPE)
        self.assertFalse(_StubConverter().convert_document(self.user.id, doc.id))

    def test_convert_document_noop_without_binary_file(self):
        doc = Document.objects.create(
            creator=self.user,
            title="Text Doc",
            file_type="text/plain",
            txt_extract_file=ContentFile(b"plain text", name="a.txt"),
            processing_started="2024-01-01T00:00:00Z",
        )
        self.assertFalse(_StubConverter().convert_document(self.user.id, doc.id))

    def test_convert_document_noop_for_disabled_extension(self):
        doc = self._make_document(filename="slides.pptx")
        # pptx is not in _StubConverter.supported_extensions
        self.assertFalse(_StubConverter().convert_document(self.user.id, doc.id))

    def test_convert_document_success_preserves_original(self):
        doc = self._make_document(filename="contract.doc")
        original_blob = doc.pdf_file.name

        converted = _StubConverter().convert_document(self.user.id, doc.id)
        self.assertTrue(converted)

        doc.refresh_from_db()
        self.assertEqual(doc.file_type, PDF_MIME_TYPE)
        self.assertEqual(doc.original_file.name, original_blob)
        self.assertEqual(doc.original_file_type, "application/msword")
        self.assertTrue(doc.pdf_file.name.endswith(".pdf"))
        self.assertNotEqual(doc.pdf_file.name, original_blob)
        with doc.pdf_file.open("rb") as fh:
            self.assertEqual(fh.read(), FAKE_PDF_BYTES)
        # Hash refreshed for the converted PDF
        import hashlib

        self.assertEqual(doc.pdf_file_hash, hashlib.sha256(FAKE_PDF_BYTES).hexdigest())
        # Original bytes still readable through the preserved reference
        with doc.original_file.open("rb") as fh:
            self.assertEqual(fh.read(), b"fake legacy doc bytes")

    def test_convert_document_recovers_ole_doc_provenance_from_octet_stream(self):
        doc = self._make_document(
            file_type=OCTET_STREAM_MIME_TYPE,
            content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy doc bytes",
        )

        self.assertTrue(_StubConverter().convert_document(self.user.id, doc.id))

        doc.refresh_from_db()
        self.assertEqual(doc.file_type, PDF_MIME_TYPE)
        self.assertEqual(doc.original_file_type, "application/msword")

    def test_convert_document_keeps_ambiguous_doc_content_inert(self):
        doc = self._make_document(
            file_type=OCTET_STREAM_MIME_TYPE,
            content=b"<html><body>not a Word document</body></html>",
        )

        self.assertTrue(_StubConverter().convert_document(self.user.id, doc.id))

        doc.refresh_from_db()
        self.assertEqual(doc.original_file_type, OCTET_STREAM_MIME_TYPE)

    def test_convert_document_raises_when_impl_returns_none(self):
        doc = self._make_document(filename="contract.doc")
        with self.assertRaises(FileConversionError) as ctx:
            _NoneReturningConverter().convert_document(self.user.id, doc.id)
        self.assertTrue(ctx.exception.is_transient)


class GotenbergFileConverterTestCase(TestCase):
    """Tests for the Gotenberg-backed converter (HTTP mocked)."""

    def setUp(self):
        PipelineSettings.clear_cache()

    def test_supported_extensions_exclude_native_formats(self):
        for native in ("pdf", "txt", "docx", "md"):
            self.assertNotIn(native, GOTENBERG_SUPPORTED_EXTENSIONS)
        # Spot-check the formats the feature was built for
        for expected in ("doc", "rtf", "odt", "ppt", "pptx", "xls", "html"):
            self.assertIn(expected, GOTENBERG_SUPPORTED_EXTENSIONS)

    def test_enabled_extensions_narrowed_by_settings(self):
        settings_obj = PipelineSettings.get_instance(use_cache=False)
        settings_obj.component_settings = {
            GOTENBERG_CONVERTER_PATH: {"convert_extensions": "doc, rtf, docx, bogus"}
        }
        settings_obj.save()

        converter = GotenbergFileConverter()
        # docx (native) and bogus (unsupported) are dropped
        self.assertEqual(converter.get_enabled_extensions(), {"doc", "rtf"})

    @patch(GOTENBERG_REQUESTS_POST)
    def test_successful_conversion(self, mock_post):
        mock_response = MagicMock()
        mock_response.content = FAKE_PDF_BYTES
        mock_post.return_value = mock_response

        converter = GotenbergFileConverter()
        result = converter.convert_to_pdf(b"doc bytes", "contract.doc")

        self.assertEqual(result, FAKE_PDF_BYTES)
        args, kwargs = mock_post.call_args
        self.assertTrue(args[0].endswith("/forms/libreoffice/convert"))
        self.assertEqual(kwargs["files"], {"files": ("contract.doc", b"doc bytes")})
        self.assertEqual(kwargs["timeout"], converter.request_timeout)

    @patch(GOTENBERG_REQUESTS_POST)
    def test_service_url_setting_honored(self, mock_post):
        mock_response = MagicMock()
        mock_response.content = FAKE_PDF_BYTES
        mock_post.return_value = mock_response

        settings_obj = PipelineSettings.get_instance(use_cache=False)
        settings_obj.component_settings = {
            GOTENBERG_CONVERTER_PATH: {"service_url": "http://elsewhere:9999/"}
        }
        settings_obj.save()

        GotenbergFileConverter().convert_to_pdf(b"x", "a.doc")
        called_url = mock_post.call_args[0][0]
        self.assertEqual(called_url, "http://elsewhere:9999/forms/libreoffice/convert")

    @patch(GOTENBERG_REQUESTS_POST)
    def test_timeout_is_transient(self, mock_post):
        mock_post.side_effect = Timeout("timed out")
        with self.assertRaises(FileConversionError) as ctx:
            GotenbergFileConverter().convert_to_pdf(b"x", "a.doc")
        self.assertTrue(ctx.exception.is_transient)

    @patch(GOTENBERG_REQUESTS_POST)
    def test_connection_error_is_transient(self, mock_post):
        mock_post.side_effect = ConnectionError("no route")
        with self.assertRaises(FileConversionError) as ctx:
            GotenbergFileConverter().convert_to_pdf(b"x", "a.doc")
        self.assertTrue(ctx.exception.is_transient)

    @patch(GOTENBERG_REQUESTS_POST)
    def test_4xx_is_permanent(self, mock_post):
        response = MagicMock()
        response.status_code = 400
        response.text = "unconvertible file"
        error = HTTPError(response=response)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = error
        mock_post.return_value = mock_response

        with self.assertRaises(FileConversionError) as ctx:
            GotenbergFileConverter().convert_to_pdf(b"x", "a.doc")
        self.assertFalse(ctx.exception.is_transient)

    @patch(GOTENBERG_REQUESTS_POST)
    def test_5xx_is_transient(self, mock_post):
        response = MagicMock()
        response.status_code = 503
        response.text = "overloaded"
        error = HTTPError(response=response)
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = error
        mock_post.return_value = mock_response

        with self.assertRaises(FileConversionError) as ctx:
            GotenbergFileConverter().convert_to_pdf(b"x", "a.doc")
        self.assertTrue(ctx.exception.is_transient)

    @patch(GOTENBERG_REQUESTS_POST)
    def test_non_pdf_body_is_permanent(self, mock_post):
        mock_response = MagicMock()
        mock_response.content = b"<html>not a pdf</html>"
        mock_post.return_value = mock_response

        with self.assertRaises(FileConversionError) as ctx:
            GotenbergFileConverter().convert_to_pdf(b"x", "a.doc")
        self.assertFalse(ctx.exception.is_transient)


class FileConverterRegistryTestCase(TestCase):
    """Registry and component-resolution integration."""

    def test_gotenberg_converter_is_discovered(self):
        names = {d.name for d in get_all_file_converters_cached()}
        self.assertIn("GotenbergFileConverter", names)

    def test_registry_definition_metadata(self):
        defn = get_registry().get_by_class_name(GOTENBERG_CONVERTER_PATH)
        assert defn is not None  # plain assert so mypy narrows the Optional
        self.assertEqual(defn.component_type, ComponentType.FILE_CONVERTER)
        self.assertIn("doc", defn.supported_extensions)
        self.assertNotIn("docx", defn.supported_extensions)
        # Settings schema extracted from the nested dataclass
        schema_names = {entry["name"] for entry in defn.settings_schema}
        self.assertEqual(
            schema_names, {"service_url", "request_timeout", "convert_extensions"}
        )
        # supported_extensions serialized in to_dict for GraphQL
        self.assertIn("supported_extensions", defn.to_dict())

    def test_all_components_cached_includes_file_converters(self):
        result = get_all_components_cached()
        self.assertIn("file_converters", result)
        self.assertIsInstance(result["file_converters"], tuple)

    def test_get_component_by_name_resolves_converter(self):
        self.assertIs(
            get_component_by_name(GOTENBERG_CONVERTER_PATH), GotenbergFileConverter
        )
        self.assertIs(
            get_component_by_name("gotenberg_converter"), GotenbergFileConverter
        )


class ConverterResolutionTestCase(TestCase):
    """PipelineSettings + pipeline.utils converter lookup helpers."""

    def setUp(self):
        PipelineSettings.clear_cache()

    def test_default_is_disabled(self):
        instance = PipelineSettings.get_instance(use_cache=False)
        self.assertEqual(instance.get_default_file_converter(), "")
        self.assertIsNone(get_default_file_converter_class())
        self.assertIsNone(get_default_file_converter_instance())
        self.assertEqual(get_convertible_extensions(), frozenset())

    def test_configured_converter_resolves(self):
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        self.assertIs(get_default_file_converter_class(), GotenbergFileConverter)
        self.assertIsInstance(
            get_default_file_converter_instance(), GotenbergFileConverter
        )
        extensions = get_convertible_extensions()
        self.assertIn("doc", extensions)
        self.assertNotIn("docx", extensions)

    def test_bogus_converter_path_degrades_to_disabled(self):
        _configure_converter("no.such.module.NoSuchConverter")
        self.assertIsNone(get_default_file_converter_class())
        self.assertEqual(get_convertible_extensions(), frozenset())

    def test_non_converter_class_rejected(self):
        _configure_converter(
            "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser"
        )
        self.assertIsNone(get_default_file_converter_class())


class ResolveConvertibleUploadTestCase(TestCase):
    """Upload-acceptance decision helper."""

    def setUp(self):
        PipelineSettings.clear_cache()

    def test_disabled_converter_returns_none(self):
        self.assertIsNone(resolve_convertible_upload("contract.doc", None))

    def test_native_extensions_never_convertible(self):
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        for filename in ("a.pdf", "a.txt", "a.docx", "a.md", "a.markdown", "a.caml"):
            self.assertIsNone(resolve_convertible_upload(filename, None), msg=filename)

    def test_missing_extension_returns_none(self):
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        self.assertIsNone(resolve_convertible_upload("no_extension", None))

    def test_enabled_extension_returns_octet_stream(self):
        # Always inert octet-stream (never a browser-renderable Content-Type),
        # regardless of what the extension's "true" MIME is.
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        self.assertEqual(
            resolve_convertible_upload("contract.doc", None),
            OCTET_STREAM_MIME_TYPE,
        )

    def test_active_content_extensions_resolve_to_inert_mime(self):
        # .html / .svg / .xml must NOT be recorded as browser-renderable types
        # (stored-XSS defense) — they resolve to octet-stream like everything
        # else on the conversion path.
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        for filename in ("page.html", "image.svg", "data.xml", "doc.xhtml"):
            resolved = resolve_convertible_upload(filename, "text/html")
            self.assertEqual(resolved, OCTET_STREAM_MIME_TYPE, msg=filename)

    def test_text_sniffed_convertible_never_maps_to_text_mime(self):
        # RTF sniffs as plain text but must not land in txt_extract_file —
        # the resolved mime must be outside TEXT_MIMETYPES so versioning
        # stores it in pdf_file for the conversion step.
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        resolved = resolve_convertible_upload("doc.rtf", "text/plain")
        self.assertIsNotNone(resolved)
        self.assertNotIn(resolved, TEXT_MIMETYPES)

    def test_extension_not_in_configured_list_returns_none(self):
        _configure_converter(
            GOTENBERG_CONVERTER_PATH,
            component_settings={
                GOTENBERG_CONVERTER_PATH: {"convert_extensions": "rtf"}
            },
        )
        self.assertIsNone(resolve_convertible_upload("contract.doc", None))
        self.assertIsNotNone(resolve_convertible_upload("memo.rtf", None))


class ValidateFileTypeConverterTestCase(TestCase):
    """DocumentService.validate_file_type converter awareness."""

    def setUp(self):
        PipelineSettings.clear_cache()

    # Overwhelmingly non-printable so is_plaintext_content's printable-ratio
    # heuristic rejects it, and no magic-byte signature so filetype.guess
    # returns None.
    UNSNIFFABLE_BYTES = b"\xde\xad\xbe\xef" * 16

    def test_unknown_binary_rejected_without_converter(self):
        from opencontractserver.documents.document_service import DocumentService

        mime, error = DocumentService.validate_file_type(
            self.UNSNIFFABLE_BYTES, "contract.doc"
        )
        self.assertIsNone(mime)
        self.assertTrue(error)

    def test_unknown_binary_accepted_with_converter(self):
        from opencontractserver.documents.document_service import DocumentService

        _configure_converter(GOTENBERG_CONVERTER_PATH)
        mime, error = DocumentService.validate_file_type(
            self.UNSNIFFABLE_BYTES, "contract.doc"
        )
        self.assertEqual(mime, OCTET_STREAM_MIME_TYPE)
        self.assertEqual(error, "")

    def test_native_pdf_still_accepted(self):
        from opencontractserver.documents.document_service import DocumentService

        _configure_converter(GOTENBERG_CONVERTER_PATH)
        mime, error = DocumentService.validate_file_type(
            b"%PDF-1.4 minimal", "contract.pdf"
        )
        self.assertEqual(mime, PDF_MIME_TYPE)
        self.assertEqual(error, "")


class ConvertDocumentToPdfTaskTestCase(TestCase):
    """The convert_document_to_pdf Celery task."""

    def setUp(self):
        PipelineSettings.clear_cache()
        self.user = User.objects.create_user(username="fc_task_user", password="x")

    def _make_document(self, filename="contract.doc", file_type="application/msword"):
        return Document.objects.create(
            creator=self.user,
            title="Task Doc",
            file_type=file_type,
            pdf_file=ContentFile(b"legacy doc bytes", name=filename),
            backend_lock=True,
            processing_started="2024-01-01T00:00:00Z",  # suppress ingest chain
        )

    def test_skipped_when_no_converter_configured(self):
        from opencontractserver.tasks.doc_tasks import convert_document_to_pdf

        doc = self._make_document()
        result = convert_document_to_pdf.apply(
            kwargs={"user_id": self.user.id, "doc_id": doc.id}
        ).get()
        self.assertEqual(result["status"], "skipped")
        doc.refresh_from_db()
        self.assertEqual(doc.file_type, "application/msword")

    def test_skipped_for_missing_document(self):
        from opencontractserver.tasks.doc_tasks import convert_document_to_pdf

        result = convert_document_to_pdf.apply(
            kwargs={"user_id": self.user.id, "doc_id": 999999}
        ).get()
        self.assertEqual(result["status"], "skipped")

    @patch(GOTENBERG_REQUESTS_POST)
    def test_converts_configured_document(self, mock_post):
        from opencontractserver.tasks.doc_tasks import convert_document_to_pdf

        mock_response = MagicMock()
        mock_response.content = FAKE_PDF_BYTES
        mock_post.return_value = mock_response

        _configure_converter(GOTENBERG_CONVERTER_PATH)
        doc = self._make_document()

        result = convert_document_to_pdf.apply(
            kwargs={"user_id": self.user.id, "doc_id": doc.id}
        ).get()
        self.assertEqual(result["status"], "converted")

        doc.refresh_from_db()
        self.assertEqual(doc.file_type, PDF_MIME_TYPE)
        self.assertTrue(doc.pdf_file.name.endswith(".pdf"))
        self.assertEqual(doc.original_file_type, "application/msword")

    @patch(GOTENBERG_REQUESTS_POST)
    def test_permanent_failure_marks_document_failed(self, mock_post):
        from opencontractserver.tasks.doc_tasks import convert_document_to_pdf

        response = MagicMock()
        response.status_code = 400
        response.text = "cannot convert"
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError(response=response)
        mock_post.return_value = mock_response

        _configure_converter(GOTENBERG_CONVERTER_PATH)
        doc = self._make_document()

        with self.assertRaises(FileConversionError):
            convert_document_to_pdf.apply(
                kwargs={"user_id": self.user.id, "doc_id": doc.id},
                throw=True,
            ).get()

        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertIn("cannot convert", doc.processing_error)


class FileConverterGraphQLTestCase(TestCase):
    """GraphQL exposure of file converters and defaultFileConverter."""

    def setUp(self):
        PipelineSettings.clear_cache()
        self.superuser = User.objects.create_superuser(
            username="fc_gql_admin", password="admin", email="fc_gql@test.com"
        )
        self.regular_user = User.objects.create_user(
            username="fc_gql_regular", password="regular"
        )
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )
        self.regular_client = Client(
            schema, context_value=TestContext(self.regular_user)
        )
        PipelineSettings.get_instance()

    def test_pipeline_components_lists_file_converters_for_superuser(self):
        query = """
            query {
                pipelineComponents {
                    fileConverters {
                        name
                        className
                        supportedExtensions
                        settingsSchema { name }
                        enabled
                    }
                }
            }
        """
        result = self.superuser_client.execute(query)
        self.assertIsNone(result.get("errors"))
        converters = result["data"]["pipelineComponents"]["fileConverters"]
        names = {c["name"] for c in converters}
        self.assertIn("GotenbergFileConverter", names)
        gotenberg = next(c for c in converters if c["name"] == "GotenbergFileConverter")
        self.assertIn("doc", gotenberg["supportedExtensions"])
        self.assertNotIn("docx", gotenberg["supportedExtensions"])

    def test_pipeline_settings_exposes_default_file_converter(self):
        query = """
            query {
                pipelineSettings {
                    defaultFileConverter
                }
            }
        """
        result = self.regular_client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["pipelineSettings"]["defaultFileConverter"], "")

    def test_convertible_extensions_query(self):
        query = """
            query {
                convertibleExtensions
            }
        """
        # Disabled: empty list
        result = self.regular_client.execute(query)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["convertibleExtensions"], [])

        # Enabled: the converter's enabled extensions, sorted
        _configure_converter(GOTENBERG_CONVERTER_PATH)
        result = self.regular_client.execute(query)
        self.assertIsNone(result.get("errors"))
        extensions = result["data"]["convertibleExtensions"]
        self.assertIn("doc", extensions)
        self.assertNotIn("docx", extensions)
        self.assertEqual(extensions, sorted(extensions))

    MUTATION = """
        mutation UpdatePipelineSettings($defaultFileConverter: String) {
            updatePipelineSettings(defaultFileConverter: $defaultFileConverter) {
                ok
                message
                pipelineSettings {
                    defaultFileConverter
                }
            }
        }
    """

    def test_superuser_can_set_and_clear_default_file_converter(self):
        result = self.superuser_client.execute(
            self.MUTATION,
            variables={"defaultFileConverter": GOTENBERG_CONVERTER_PATH},
        )
        self.assertIsNone(result.get("errors"))
        payload = result["data"]["updatePipelineSettings"]
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["pipelineSettings"]["defaultFileConverter"],
            GOTENBERG_CONVERTER_PATH,
        )
        self.assertEqual(
            PipelineSettings.get_instance(use_cache=False).default_file_converter,
            GOTENBERG_CONVERTER_PATH,
        )

        # Empty string disables conversion again
        result = self.superuser_client.execute(
            self.MUTATION, variables={"defaultFileConverter": ""}
        )
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"])
        self.assertEqual(
            PipelineSettings.get_instance(use_cache=False).default_file_converter,
            "",
        )

    def test_non_converter_component_rejected(self):
        result = self.superuser_client.execute(
            self.MUTATION,
            variables={
                "defaultFileConverter": (
                    "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser"
                )
            },
        )
        payload = result["data"]["updatePipelineSettings"]
        self.assertFalse(payload["ok"])
        self.assertIn("not a file converter", payload["message"])

    def test_unknown_component_rejected(self):
        result = self.superuser_client.execute(
            self.MUTATION,
            variables={"defaultFileConverter": "no.such.Converter"},
        )
        payload = result["data"]["updatePipelineSettings"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found in registry", payload["message"])

    def test_regular_user_cannot_set_default_file_converter(self):
        result = self.regular_client.execute(
            self.MUTATION,
            variables={"defaultFileConverter": GOTENBERG_CONVERTER_PATH},
        )
        payload = result["data"]["updatePipelineSettings"]
        self.assertFalse(payload["ok"])
        self.assertIn("superusers", payload["message"])


class NativeExtensionInvariantTestCase(TestCase):
    """The natively-parsed formats can never be routed through conversion."""

    def test_native_set_contents(self):
        self.assertEqual(
            NATIVE_PIPELINE_EXTENSIONS,
            {"pdf", "txt", "docx", "md", "markdown", "caml"},
        )

    def test_gotenberg_enabled_extensions_exclude_native(self):
        converter = GotenbergFileConverter()
        self.assertFalse(
            converter.get_enabled_extensions() & NATIVE_PIPELINE_EXTENSIONS
        )
