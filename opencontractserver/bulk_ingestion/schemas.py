"""
Type definitions for bulk ingestion data interchange formats.

These TypedDicts define the JSON schemas used for:
- Pre-parsed document bundles (offline parser output)
- Batch manifests (coordinating multi-workstation parsing)
- Ingestion job source configuration
"""

from typing import Optional

from typing_extensions import NotRequired, TypedDict

from opencontractserver.types.dicts import OpenContractDocExport


class PreParsedDocumentBundle(TypedDict):
    """
    Output format from an offline parser. Contains everything needed
    to create a fully-indexed document in OpenContracts without
    running the parsing pipeline on the server.

    Produced by GPU workstations running parsers (e.g., Docling)
    directly, then imported via the bulk ingestion pipeline.

    File format: One JSON object per document, typically batched
    into JSONL files (one JSON per line) for streaming reads.
    """

    # Format version for forward compatibility
    format_version: str  # "1.0"

    # Source identification
    external_id: str  # Unique identifier for this document
    source_filename: str  # Original filename (e.g., "document_001.pdf")
    source_url: NotRequired[str]  # Original URL if applicable

    # The OpenContractDocExport (same format parsers return internally)
    parsed_data: OpenContractDocExport

    # Parser provenance
    parser_name: str  # Parser class name (e.g., "DoclingParser")
    parser_version: str  # Parser version (e.g., "2.1.0")
    parser_config: dict  # Configuration used for parsing
    parsed_at: str  # ISO 8601 timestamp
    parse_duration_seconds: float

    # File integrity
    pdf_sha256: str  # SHA-256 hash of the source PDF

    # Optional pre-generated thumbnail (skip server-side extraction)
    thumbnail_base64: NotRequired[str]  # Base64-encoded image data
    thumbnail_format: NotRequired[str]  # Image format (e.g., "png")

    # Optional custom metadata to store on the Document
    custom_meta: NotRequired[dict]

    # Error marker (for tracking parse failures in batch output)
    error: NotRequired[str]  # If present, indicates parse failure


class BatchManifest(TypedDict):
    """
    Index file for a collection of pre-parsed document batches.

    Produced by the offline parsing tool and consumed by the bulk
    ingestion pipeline to know what data is available for import.
    """

    format_version: str  # "1.0"

    # Summary
    total_documents: int
    total_batches: int
    total_failed: NotRequired[int]

    # Parser info
    parser_name: str
    parser_version: str
    parser_config: NotRequired[dict]

    # Timing
    created_at: str  # ISO 8601
    completed_at: NotRequired[str]

    # Storage location
    storage_backend: str  # "s3", "gcs", "local"
    base_path: str  # Base path/prefix for batch files

    # Batch index
    batches: list["BatchEntry"]


class BatchEntry(TypedDict):
    """Entry for a single batch file in the manifest."""

    filename: str  # Relative path to JSONL batch file
    document_count: int
    failed_count: NotRequired[int]
    first_external_id: str
    last_external_id: str
    sha256: NotRequired[str]  # Hash of the batch file for integrity


class URLPatternSourceConfig(TypedDict):
    """Source configuration for URL-pattern-based ingestion."""

    url_template: str  # URL with {id} placeholder
    id_range_start: int
    id_range_end: int
    id_format: NotRequired[str]  # e.g., "{:08d}" for zero-padded 8 digits
    file_extension: NotRequired[str]  # Default: "pdf"
    rate_limit_per_second: NotRequired[float]


class StoragePrefixSourceConfig(TypedDict):
    """Source configuration for storage-prefix-based ingestion."""

    backend: str  # "s3", "gcs", "local"
    bucket: NotRequired[str]  # S3/GCS bucket name
    prefix: str  # Key prefix / directory path
    file_pattern: NotRequired[str]  # Glob pattern for files (default: "*.pdf")


class ManifestSourceConfig(TypedDict):
    """Source configuration for manifest-based ingestion."""

    manifest_path: str  # Path to manifest JSON/CSV
    manifest_format: NotRequired[str]  # "json" or "csv" (default: "json")


class PreParsedSourceConfig(TypedDict):
    """Source configuration for pre-parsed bundle ingestion."""

    manifest_path: str  # Path to BatchManifest JSON
    pdf_storage_path: NotRequired[str]  # Where original PDFs are staged
    skip_thumbnails: NotRequired[bool]  # True if thumbnails are in bundles
    skip_embeddings: NotRequired[bool]  # True to defer embedding to later


class IngestionProgress(TypedDict):
    """Snapshot of job progress, suitable for API responses."""

    job_id: int
    status: str
    total_items: int
    downloaded_count: int
    imported_count: int
    parsed_count: int
    embedded_count: int
    failed_count: int
    skipped_count: int
    progress_fraction: float
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: str
