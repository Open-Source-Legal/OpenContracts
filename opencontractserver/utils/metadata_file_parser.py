"""
Parser for document metadata files in ZIP imports.

This module parses CSV files that provide metadata for documents
in a ZIP archive. The metadata is applied during document import.

CSV Format:
-----------
source_path,title,description,external_id
/contracts/master.pdf,Master Agreement,The main services contract,
/contracts/amendment.pdf,Amendment #1,,cross:H022844

Columns:
- source_path: Path to document (relative to zip root) - REQUIRED
- title: Document title (optional, overrides filename-based title)
- description: Document description (optional)
- external_id: Durable identifier in the producing system (optional).
  Stored verbatim on the document's ``DocumentPath.external_id``, so it
  survives renames where the title/path do not. Producers should namespace
  values (e.g. ``cross:H022844`` for CROSS ruling numbers — the customs
  enrichment service resolves citations through that namespace first).

Notes:
- Paths use same normalization as relationships.csv
- Empty values are ignored (don't override defaults)
- Header row is required
- Columns can be omitted entirely if not needed
"""

import csv
import logging
from dataclasses import dataclass, field
from io import StringIO
from typing import Optional
from zipfile import ZipFile

from opencontractserver.utils.relationship_file_parser import normalize_path

logger = logging.getLogger(__name__)

# Valid metadata file names (checked in order)
METADATA_FILE_NAMES = [
    "meta.csv",
    "META.csv",
    "metadata.csv",
    "METADATA.csv",
]


# Matches DocumentPath.external_id (max_length=512); longer values are
# rejected per-row with a warning rather than silently truncated.
EXTERNAL_ID_MAX_LENGTH = 512


@dataclass
class DocumentMetadata:
    """Metadata for a single document."""

    source_path: str  # Normalized path (with leading /)
    title: Optional[str] = None
    description: Optional[str] = None
    external_id: Optional[str] = None


@dataclass
class MetadataFileParseResult:
    """Result of parsing a metadata file."""

    is_valid: bool
    metadata: dict[str, DocumentMetadata] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def detect_metadata_file(zip_file: ZipFile) -> Optional[str]:
    """
    Detect if zip contains a metadata file.

    Args:
        zip_file: Open ZipFile object to search in

    Returns:
        Filename if found, None otherwise.
        Checks filenames in priority order.
    """
    namelist = zip_file.namelist()
    for name in METADATA_FILE_NAMES:
        if name in namelist:
            return name
    return None


def is_metadata_file(path: str) -> bool:
    """
    Check if a path is a metadata file at the root.

    Args:
        path: File path within the zip

    Returns:
        True if this is a recognized metadata file at root level
    """
    # Must be at root (no directory separators)
    if "/" in path:
        return False
    return path in METADATA_FILE_NAMES


def parse_metadata_file(
    zip_file: ZipFile,
    filename: str,
) -> MetadataFileParseResult:
    """
    Parse a metadata CSV file from a zip archive.

    Args:
        zip_file: Open ZipFile object
        filename: Name of the metadata file within the zip

    Returns:
        MetadataFileParseResult with parsed metadata and any errors/warnings
    """
    # Local import: zip_security imports METADATA_FILE_NAMES from this module
    # at module load time, so importing it back at module level here would
    # create an import cycle. Deferring to call time breaks the cycle.
    from opencontractserver.constants.zip_import import (
        get_zip_max_single_file_size_bytes,
    )
    from opencontractserver.utils.zip_security import read_zip_member_bounded

    # Bounded read: a crafted meta.csv member whose declared size lies about
    # its true decompressed size could otherwise force an unbounded
    # allocation (see read_zip_member_bounded docstring). This file is never
    # added to validate_zip_for_import's valid_files list, so it also never
    # passes through that function's per-member declared-size check.
    content_bytes = read_zip_member_bounded(
        zip_file, filename, get_zip_max_single_file_size_bytes()
    )
    if content_bytes is None:
        error_msg = (
            f"Could not read metadata file '{filename}': exceeds "
            f"ZIP_MAX_SINGLE_FILE_SIZE_BYTES or could not be read safely"
        )
        logger.error(error_msg)
        return MetadataFileParseResult(
            is_valid=False,
            errors=[error_msg],
        )

    try:
        content = content_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decode metadata file '{filename}': {e}")
        return MetadataFileParseResult(
            is_valid=False,
            errors=[f"Could not read metadata file: {str(e)}"],
        )

    return parse_csv_metadata(content)


def parse_csv_metadata(content: str) -> MetadataFileParseResult:
    """
    Parse CSV format metadata content.

    Expected columns:
    - source_path (required)
    - title (optional)
    - description (optional)

    Args:
        content: CSV file content as string

    Returns:
        MetadataFileParseResult with parsed metadata keyed by normalized path
    """
    result = MetadataFileParseResult(is_valid=True)

    if not content.strip():
        result.warnings.append("Metadata file is empty")
        return result

    try:
        reader = csv.DictReader(StringIO(content))

        # Validate required columns exist
        if reader.fieldnames is None:
            result.is_valid = False
            result.errors.append("CSV file has no header row")
            return result

        fieldnames_lower = [f.lower().strip() for f in reader.fieldnames]

        if "source_path" not in fieldnames_lower:
            result.is_valid = False
            result.errors.append("Missing required column: source_path")
            return result

        # Build column name mapping (handle case variations)
        col_map = {}
        for original in reader.fieldnames:
            lower = original.lower().strip()
            col_map[lower] = original

        # Check which optional columns are present
        has_title = "title" in fieldnames_lower
        has_description = "description" in fieldnames_lower
        has_external_id = "external_id" in fieldnames_lower

        if not has_title and not has_description and not has_external_id:
            result.warnings.append(
                "Metadata file has no title, description, or external_id "
                "columns - no metadata will be applied"
            )

        # Parse rows
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Get source path
                source_path = row.get(col_map.get("source_path", ""), "").strip()

                # Skip empty rows
                if not source_path:
                    continue

                # Check for path traversal
                if ".." in source_path:
                    result.errors.append(
                        f"Row {row_num}: Path traversal not allowed in source_path"
                    )
                    continue

                # Normalize path
                normalized_path = normalize_path(source_path)

                # Get optional fields (empty string = None)
                title = None
                description = None
                external_id = None

                if has_title:
                    title_val = row.get(col_map.get("title", ""), "").strip()
                    if title_val:
                        title = title_val

                if has_description:
                    desc_val = row.get(col_map.get("description", ""), "").strip()
                    if desc_val:
                        description = desc_val

                if has_external_id:
                    ext_val = row.get(col_map.get("external_id", ""), "").strip()
                    if len(ext_val) > EXTERNAL_ID_MAX_LENGTH:
                        result.warnings.append(
                            f"Row {row_num}: external_id exceeds "
                            f"{EXTERNAL_ID_MAX_LENGTH} characters - ignored"
                        )
                    elif ext_val:
                        external_id = ext_val

                # Only add if there's at least one metadata value
                if (
                    title is not None
                    or description is not None
                    or external_id is not None
                ):
                    # Warn if duplicate path (later entries override)
                    if normalized_path in result.metadata:
                        result.warnings.append(
                            f"Row {row_num}: Duplicate path '{source_path}' - "
                            "later entry will override"
                        )

                    result.metadata[normalized_path] = DocumentMetadata(
                        source_path=normalized_path,
                        title=title,
                        description=description,
                        external_id=external_id,
                    )

            except Exception as e:
                result.warnings.append(f"Row {row_num}: Error parsing row: {str(e)}")

    except csv.Error as e:
        result.is_valid = False
        result.errors.append(f"CSV parsing error: {str(e)}")
    except Exception as e:
        result.is_valid = False
        result.errors.append(f"Unexpected error parsing CSV: {str(e)}")

    logger.info(
        f"Parsed metadata file: {len(result.metadata)} documents with metadata, "
        f"{len(result.errors)} errors, {len(result.warnings)} warnings"
    )

    return result
