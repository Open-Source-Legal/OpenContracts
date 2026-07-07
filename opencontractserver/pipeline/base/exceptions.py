"""
Custom exceptions for the document processing pipeline.

These exceptions provide structured error handling with metadata about
whether errors are transient (retryable) or permanent.
"""


class DocumentParsingError(Exception):
    """
    Raised when document parsing fails.

    This exception captures both the error message and whether the error
    is transient (likely to succeed on retry) or permanent (will always fail).

    Examples of transient errors:
        - Network timeouts to parsing service
        - 5xx server errors from parsing service
        - Temporary resource unavailability

    Examples of permanent errors:
        - Malformed/corrupted PDF files
        - Unsupported file formats
        - 4xx client errors (bad request, unauthorized)

    Attributes:
        is_transient: Whether the error might succeed on retry.
                     Used by Celery to determine if auto-retry should be attempted.
    """

    def __init__(self, message: str, is_transient: bool = True):
        """
        Initialize the DocumentParsingError.

        Args:
            message: Human-readable error description.
            is_transient: If True, the error might succeed on retry (default: True).
                         If False, retrying will not help.
        """
        super().__init__(message)
        self.is_transient = is_transient


class FileConversionError(Exception):
    """
    Raised when pre-parse file-to-PDF conversion fails.

    Mirrors :class:`DocumentParsingError`'s transient/permanent contract so the
    Celery conversion task can reuse the same retry semantics.

    Examples of transient errors:
        - Network timeouts to the conversion service
        - 5xx server errors from the conversion service

    Examples of permanent errors:
        - Corrupt/unconvertible source files (4xx from the service)
        - A response that is not a PDF (misconfigured service URL)

    Attributes:
        is_transient: Whether the error might succeed on retry.
    """

    def __init__(self, message: str, is_transient: bool = True):
        """
        Initialize the FileConversionError.

        Args:
            message: Human-readable error description.
            is_transient: If True, the error might succeed on retry (default: True).
                         If False, retrying will not help.
        """
        super().__init__(message)
        self.is_transient = is_transient


class DocumentThumbnailError(Exception):
    """
    Raised when thumbnail generation fails.

    This exception is separate from parsing errors since thumbnail generation
    is typically less critical and may have different retry behavior.

    Attributes:
        is_transient: Whether the error might succeed on retry.
    """

    def __init__(self, message: str, is_transient: bool = True):
        """
        Initialize the DocumentThumbnailError.

        Args:
            message: Human-readable error description.
            is_transient: If True, the error might succeed on retry (default: True).
                         If False, retrying will not help.
        """
        super().__init__(message)
        self.is_transient = is_transient


class EmbeddingClientError(Exception):
    """
    Raised for 4xx client errors from the embedding service.

    These errors indicate invalid input (malformed request, bad data) and
    should NOT be retried by Celery tasks.
    """

    pass


class EmbeddingServerError(Exception):
    """
    Raised for 5xx server errors from the embedding service.

    These errors indicate transient service issues and SHOULD be retried
    by Celery tasks with exponential backoff.
    """

    pass
