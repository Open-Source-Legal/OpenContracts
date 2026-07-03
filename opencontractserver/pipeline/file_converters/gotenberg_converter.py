"""
Gotenberg-powered file converter.

Delegates file-to-PDF conversion to a Gotenberg service
(https://github.com/gotenberg/gotenberg) via its LibreOffice route
(``POST /forms/libreoffice/convert``). Gotenberg runs LibreOffice inside its
own container, so OpenContracts gains conversion for the full LibreOffice
import-filter catalogue (legacy Office, OpenDocument, iWork, WordPerfect,
HTML, images, ...) without bundling LibreOffice into the Django image.
"""

import logging
from dataclasses import dataclass, field

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

from opencontractserver.constants.document_processing import (
    DEFAULT_GOTENBERG_SERVICE_URL,
    GOTENBERG_CONVERTER_REQUEST_TIMEOUT_SECONDS,
)
from opencontractserver.pipeline.base.exceptions import FileConversionError
from opencontractserver.pipeline.base.file_converter import BaseFileConverter
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)

logger = logging.getLogger(__name__)

# Path of Gotenberg's LibreOffice conversion route, appended to the configured
# service URL.
LIBREOFFICE_CONVERT_ROUTE = "/forms/libreoffice/convert"

# Every extension Gotenberg's LibreOffice route accepts (see
# https://gotenberg.dev/docs/routes#office-documents-into-pdfs-route), MINUS
# the formats OpenContracts parses natively — pdf, txt, and docx stay on their
# existing parser paths and are never converted (so .doc converts, .docx does
# not). ``BaseFileConverter.get_enabled_extensions`` additionally subtracts
# NATIVE_PIPELINE_EXTENSIONS as defense in depth.
GOTENBERG_SUPPORTED_EXTENSIONS: list[str] = [
    "123",
    "602",
    "abw",
    "bib",
    "bmp",
    "cdr",
    "cgm",
    "cmx",
    "csv",
    "cwk",
    "dbf",
    "dif",
    "doc",
    "docm",
    "dot",
    "dotm",
    "dotx",
    "dxf",
    "emf",
    "eps",
    "epub",
    "fodg",
    "fodp",
    "fods",
    "fodt",
    "gif",
    "htm",
    "html",
    "hwp",
    "jpeg",
    "jpg",
    "key",
    "ltx",
    "lwp",
    "mcw",
    "met",
    "mml",
    "mw",
    "numbers",
    "odd",
    "odg",
    "odm",
    "odp",
    "ods",
    "odt",
    "otg",
    "oth",
    "otp",
    "ots",
    "ott",
    "pages",
    "pbm",
    "pcd",
    "pct",
    "pcx",
    "pdb",
    "pgm",
    "png",
    "pot",
    "potm",
    "potx",
    "ppm",
    "pps",
    "ppt",
    "pptm",
    "pptx",
    "psd",
    "psw",
    "pub",
    "pwp",
    "pxl",
    "ras",
    "rtf",
    "sda",
    "sdc",
    "sdd",
    "sdp",
    "sdw",
    "sgl",
    "slk",
    "smf",
    "stc",
    "std",
    "sti",
    "stw",
    "svg",
    "svm",
    "swf",
    "sxc",
    "sxd",
    "sxg",
    "sxi",
    "sxm",
    "sxw",
    "tga",
    "tif",
    "tiff",
    "uof",
    "uop",
    "uos",
    "uot",
    "vdx",
    "vor",
    "vsd",
    "vsdm",
    "vsdx",
    "wb2",
    "wk1",
    "wks",
    "wmf",
    "wpd",
    "wpg",
    "wps",
    "xbm",
    "xhtml",
    "xls",
    "xlsb",
    "xlsm",
    "xlsx",
    "xlt",
    "xltm",
    "xltx",
    "xlw",
    "xml",
    "xpm",
    "zabw",
]


class GotenbergFileConverter(BaseFileConverter):
    """
    Converts documents to PDF using a Gotenberg service's LibreOffice route.

    The source file is uploaded as multipart form data; Gotenberg picks the
    LibreOffice import filter from the filename extension and returns the
    converted PDF bytes in the response body.
    """

    title = "Gotenberg PDF Converter"
    description = (
        "Converts office, legacy word-processor, spreadsheet, presentation, "
        "web, and image formats to PDF using a Gotenberg service "
        "(LibreOffice route). Natively parsed formats (pdf, txt, docx, md) "
        "are never converted."
    )
    author = "OpenContracts Team"
    dependencies = ["requests"]
    supported_extensions = GOTENBERG_SUPPORTED_EXTENSIONS

    @dataclass
    class Settings:
        """Configuration schema for GotenbergFileConverter."""

        service_url: str = field(
            default=DEFAULT_GOTENBERG_SERVICE_URL,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Base URL of the Gotenberg service",
                    env_var="GOTENBERG_SERVICE_URL",
                )
            },
        )
        request_timeout: int = field(
            default=GOTENBERG_CONVERTER_REQUEST_TIMEOUT_SECONDS,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Conversion request timeout in seconds",
                    env_var="GOTENBERG_CONVERTER_TIMEOUT",
                )
            },
        )
        convert_extensions: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Comma-separated list of file extensions to convert "
                        "to PDF (e.g. 'doc, rtf, odt, ppt'). Empty means "
                        "every extension Gotenberg supports. Natively parsed "
                        "formats (pdf, txt, docx, md) are always excluded."
                    ),
                )
            },
        )

    def __init__(self):
        """Initialize the converter with settings from PipelineSettings."""
        super().__init__()
        s = self.settings if self.settings is not None else self.Settings()
        self.service_url = s.service_url or DEFAULT_GOTENBERG_SERVICE_URL
        self.request_timeout = s.request_timeout
        logger.info(
            f"GotenbergFileConverter initialized with service URL: "
            f"{self.service_url}, timeout: {self.request_timeout}s"
        )

    def _convert_to_pdf_impl(
        self, file_bytes: bytes, filename: str, **all_kwargs
    ) -> bytes:
        """
        POST the source file to Gotenberg's LibreOffice route and return the
        converted PDF bytes.

        Args:
            file_bytes: Raw bytes of the source file.
            filename: Original filename (Gotenberg selects the LibreOffice
                import filter from its extension).
            **all_kwargs: Merged component settings + call-time overrides;
                ``service_url`` and ``request_timeout`` are honored.

        Returns:
            The converted PDF bytes.

        Raises:
            FileConversionError: transient for timeouts / connection failures /
                5xx responses, permanent for 4xx responses or a non-PDF body.
        """
        service_url = str(all_kwargs.get("service_url") or self.service_url)
        request_timeout = int(all_kwargs.get("request_timeout") or self.request_timeout)
        endpoint = service_url.rstrip("/") + LIBREOFFICE_CONVERT_ROUTE

        logger.info(
            f"GotenbergFileConverter - converting '{filename}' "
            f"({len(file_bytes)} bytes) via {endpoint}"
        )

        try:
            response = requests.post(
                endpoint,
                files={"files": (filename, file_bytes)},
                timeout=request_timeout,
            )
            response.raise_for_status()
        except Timeout:
            msg = (
                f"Gotenberg conversion of '{filename}' timed out after "
                f"{request_timeout} seconds"
            )
            logger.error(msg)
            raise FileConversionError(msg, is_transient=True)
        except ConnectionError:
            msg = f"Failed to connect to Gotenberg service at {endpoint}"
            logger.error(msg)
            raise FileConversionError(msg, is_transient=True)
        except RequestException as e:
            # 4xx = the file itself is unconvertible (permanent); 5xx =
            # service-side trouble that may clear on retry (transient).
            is_transient = True
            status_code = None
            response_text = ""
            if e.response is not None:
                status_code = e.response.status_code
                response_text = e.response.text[:500]
                if 400 <= status_code < 500:
                    is_transient = False

            msg = f"Gotenberg conversion of '{filename}' failed: {e}"
            if status_code:
                msg += f" (status={status_code})"
            if response_text:
                msg += f" - Response: {response_text}"
            logger.error(msg)
            raise FileConversionError(msg, is_transient=is_transient)

        content = response.content
        if not content or not content.startswith(b"%PDF"):
            # A 200 whose body is not a PDF means the URL points at something
            # that is not Gotenberg's conversion route — retrying won't help.
            msg = (
                f"Gotenberg returned a non-PDF response for '{filename}' "
                f"({len(content)} bytes) — check the configured service URL "
                f"({endpoint})"
            )
            logger.error(msg)
            raise FileConversionError(msg, is_transient=False)

        return content
