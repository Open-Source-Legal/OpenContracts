"""
Parser for relationship definition files in ZIP imports.

This module parses CSV files that define relationships between documents
in a ZIP archive. The relationships are created after all documents are
imported, using the document path map built during import.

CSV Format:
-----------
source_path,relationship_label,target_path,notes
/contracts/master.pdf,Parent,/contracts/amendments/amendment1.pdf,
/contracts/master.pdf,References,/exhibits/exhibit_a.pdf,See section 3

Columns:
- source_path: Path to source document (relative to zip root)
- relationship_label: Label for the relationship (e.g., "Parent", "References")
- target_path: Path to target document (relative to zip root)
- notes: Optional notes text. If provided, relationship_type will be "NOTES"

Notes:
- Paths can have optional leading slash (both "/path" and "path" work)
- Empty rows are skipped
- Header row is required
"""

import csv
import logging
import re
from dataclasses import dataclass, field
from io import StringIO
from typing import Optional
from zipfile import ZipFile

logger = logging.getLogger(__name__)

# Valid relationship file names (checked in order)
RELATIONSHIP_FILE_NAMES = [
    "relationships.csv",
    "RELATIONSHIPS.csv",
]


@dataclass
class ParsedRelationship:
    """A single relationship parsed from the relationships file."""

    source_path: str  # Normalized path (with leading /)
    target_path: str  # Normalized path (with leading /)
    label: str  # Relationship label text
    notes: Optional[str] = None  # Optional notes content
    relationship_type: str = "RELATIONSHIP"  # "RELATIONSHIP" or "NOTES"


@dataclass
class RelationshipFileParseResult:
    """Result of parsing a relationships file."""

    is_valid: bool
    relationships: list[ParsedRelationship] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def detect_relationship_file(zip_file: ZipFile) -> Optional[str]:
    """
    Detect if zip contains a relationships file.

    Args:
        zip_file: Open ZipFile object to search in

    Returns:
        Filename if found, None otherwise.
        Checks filenames in priority order.
    """
    namelist = zip_file.namelist()
    for name in RELATIONSHIP_FILE_NAMES:
        if name in namelist:
            return name
    return None


def normalize_path(path: str) -> str:
    r"""
    Normalize a path from the relationships file.

    - Strips whitespace
    - Normalizes path separators (\\ -> /)
    - Removes ./ prefix (current directory reference)
    - Removes duplicate slashes
    - Ensures leading /
    - Does NOT allow .. (parent directory traversal)

    Args:
        path: Raw path string from CSV

    Returns:
        Normalized path string with leading /
    """
    if not path:
        return ""

    normalized = path.strip()

    # Normalize separators (backslash to forward slash)
    normalized = normalized.replace("\\", "/")

    # Remove leading ./ (current directory references) using regex for efficiency
    normalized = re.sub(r"^(\./)+", "", normalized)

    # Remove duplicate slashes using regex (O(n) instead of O(n*m) with while loop)
    normalized = re.sub(r"/+", "/", normalized)

    # Remove leading slashes
    normalized = normalized.lstrip("/")

    # Ensure leading /
    normalized = "/" + normalized

    return normalized


def parse_relationship_file(
    zip_file: ZipFile,
    filename: str,
) -> RelationshipFileParseResult:
    """
    Parse a relationships CSV file from a zip archive.

    Args:
        zip_file: Open ZipFile object
        filename: Name of the relationships file within the zip

    Returns:
        RelationshipFileParseResult with parsed relationships and any errors/warnings
    """
    # Local import: zip_security imports RELATIONSHIP_FILE_NAMES from this
    # module at module load time, so importing it back at module level here
    # would create an import cycle. Deferring to call time breaks the cycle.
    from opencontractserver.constants.zip_import import (
        get_zip_max_single_file_size_bytes,
    )
    from opencontractserver.utils.zip_security import read_zip_member_bounded

    # Bounded read: a crafted relationships.csv member whose declared size
    # lies about its true decompressed size could otherwise force an
    # unbounded allocation (see read_zip_member_bounded docstring). This
    # file is never added to validate_zip_for_import's valid_files list, so
    # it also never passes through that function's per-member declared-size
    # check.
    content_bytes = read_zip_member_bounded(
        zip_file, filename, get_zip_max_single_file_size_bytes()
    )
    if content_bytes is None:
        error_msg = (
            f"Could not read relationships file '{filename}': exceeds "
            f"ZIP_MAX_SINGLE_FILE_SIZE_BYTES or could not be read safely"
        )
        logger.error(error_msg)
        return RelationshipFileParseResult(
            is_valid=False,
            errors=[error_msg],
        )

    try:
        content = content_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decode relationships file '{filename}': {e}")
        return RelationshipFileParseResult(
            is_valid=False,
            errors=[f"Could not read relationships file: {str(e)}"],
        )

    return parse_csv_relationships(content)


def parse_csv_relationships(content: str) -> RelationshipFileParseResult:
    """
    Parse CSV format relationships content.

    Expected columns:
    - source_path (required)
    - relationship_label (required)
    - target_path (required)
    - notes (optional)

    Args:
        content: CSV file content as string

    Returns:
        RelationshipFileParseResult with parsed relationships
    """
    result = RelationshipFileParseResult(is_valid=True)

    if not content.strip():
        result.warnings.append("Relationships file is empty")
        return result

    try:
        reader = csv.DictReader(StringIO(content))

        # Validate required columns exist
        if reader.fieldnames is None:
            result.is_valid = False
            result.errors.append("CSV file has no header row")
            return result

        fieldnames_lower = [f.lower().strip() for f in reader.fieldnames]
        required_columns = ["source_path", "relationship_label", "target_path"]

        for col in required_columns:
            if col not in fieldnames_lower:
                result.is_valid = False
                result.errors.append(f"Missing required column: {col}")

        if not result.is_valid:
            return result

        # Build column name mapping (handle case variations)
        col_map = {}
        for original in reader.fieldnames:
            lower = original.lower().strip()
            col_map[lower] = original

        # Parse rows
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Get values using the column mapping
                source_path = row.get(col_map.get("source_path", ""), "").strip()
                label = row.get(col_map.get("relationship_label", ""), "").strip()
                target_path = row.get(col_map.get("target_path", ""), "").strip()
                notes = row.get(col_map.get("notes", ""), "").strip() or None

                # Skip empty rows
                if not source_path and not label and not target_path:
                    continue

                # Validate required fields
                if not source_path:
                    result.errors.append(f"Row {row_num}: Missing source_path")
                    continue

                if not label:
                    result.errors.append(f"Row {row_num}: Missing relationship_label")
                    continue

                if not target_path:
                    result.errors.append(f"Row {row_num}: Missing target_path")
                    continue

                # Check for path traversal
                if ".." in source_path:
                    result.errors.append(
                        f"Row {row_num}: Path traversal not allowed in source_path"
                    )
                    continue

                if ".." in target_path:
                    result.errors.append(
                        f"Row {row_num}: Path traversal not allowed in target_path"
                    )
                    continue

                # Normalize paths
                source_path = normalize_path(source_path)
                target_path = normalize_path(target_path)

                # Determine relationship type
                relationship_type = "NOTES" if notes else "RELATIONSHIP"

                result.relationships.append(
                    ParsedRelationship(
                        source_path=source_path,
                        target_path=target_path,
                        label=label,
                        notes=notes,
                        relationship_type=relationship_type,
                    )
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
        f"Parsed relationships file: {len(result.relationships)} relationships, "
        f"{len(result.errors)} errors, {len(result.warnings)} warnings"
    )

    return result
