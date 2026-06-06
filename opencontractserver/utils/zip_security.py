"""
Zip file security utilities for safe extraction and import.

This module provides security validation for zip file imports, protecting against:
- Path traversal attacks (e.g., ../../../etc/passwd)
- Zip bombs (decompression bombs)
- Symlink attacks
- Resource exhaustion

All functions are designed to validate BEFORE extraction, never extracting
untrusted content to the filesystem.
"""

from __future__ import annotations

import logging
import os
import stat
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opencontractserver.constants.zip_import import (
    get_zip_max_compression_ratio,
    get_zip_max_file_count,
    get_zip_max_folder_count,
    get_zip_max_folder_depth,
    get_zip_max_path_component_length,
    get_zip_max_path_length,
    get_zip_max_single_file_size_bytes,
    get_zip_max_total_size_bytes,
)
from opencontractserver.utils.metadata_file_parser import METADATA_FILE_NAMES
from opencontractserver.utils.relationship_file_parser import RELATIONSHIP_FILE_NAMES

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ZipFileEntry:
    """Represents a validated file entry from a zip archive."""

    original_path: str  # Original path from zip
    sanitized_path: str  # Cleaned path for use
    folder_path: str  # Parent folder path (empty string for root)
    filename: str  # Just the filename
    file_size: int  # Uncompressed size in bytes
    compressed_size: int  # Compressed size in bytes
    is_oversized: bool = False  # True if exceeds size limit
    skip_reason: str = ""  # Reason for skipping, if any


@dataclass
class ZipManifest:
    """Result of validating a zip file for import."""

    is_valid: bool
    error_message: str = ""

    # Files to process
    valid_files: list[ZipFileEntry] = field(default_factory=list)

    # Files that will be skipped (with reasons)
    skipped_files: list[ZipFileEntry] = field(default_factory=list)

    # Unique folder paths to create (sorted by depth, parents first)
    folder_paths: list[str] = field(default_factory=list)

    # Special files detected
    relationship_file: str | None = None  # Path to relationships.csv if found
    metadata_file: str | None = None  # Path to meta.csv if found
    labels_file: str | None = None  # Path to labels.json if found

    # Annotation sidecar files: maps sanitized document path -> original sidecar path
    # e.g. {"contracts/master.pdf": "contracts/master.json"}
    annotation_sidecars: dict[str, str] = field(default_factory=dict)

    # Statistics
    total_files_in_zip: int = 0
    total_uncompressed_size: int = 0
    valid_files_size: int = 0


def sanitize_zip_path(path: str) -> tuple[str | None, str]:
    """
    Sanitize a path from a zip file for security.

    This function validates and cleans paths to prevent:
    - Path traversal attacks (../)
    - Absolute path injection
    - Null byte injection
    - Excessively long paths

    Args:
        path: Raw path from zip file

    Returns:
        (sanitized_path, error_message)
        - sanitized_path is None if the path is invalid/rejected
        - error_message describes why the path was rejected

    Examples:
        >>> sanitize_zip_path("docs/contracts/file.pdf")
        ("docs/contracts/file.pdf", "")

        >>> sanitize_zip_path("../../../etc/passwd")
        (None, "Path traversal detected: '..' not allowed")

        >>> sanitize_zip_path("/etc/passwd")
        (None, "Absolute paths not allowed")
    """
    if not path:
        return None, "Empty path"

    # Check for null bytes (injection attack)
    if "\x00" in path:
        return None, "Null bytes not allowed in path"

    # Normalize path separators to forward slash
    normalized = path.replace("\\", "/")

    # Remove leading/trailing slashes and whitespace
    normalized = normalized.strip().strip("/")

    if not normalized:
        return None, "Path is empty after normalization"

    # Read configurable limits at call time so settings/env overrides are
    # honoured (never frozen at import — see constants/zip_import.py).
    max_path_length = get_zip_max_path_length()
    max_component_length = get_zip_max_path_component_length()

    # Check total path length
    if len(normalized) > max_path_length:
        return None, f"Path exceeds maximum length of {max_path_length} characters"

    # Split into components and validate each
    components = normalized.split("/")

    for component in components:
        # Check for path traversal
        if component == "..":
            return None, "Path traversal detected: '..' not allowed"

        # Check for empty components (double slashes)
        if not component:
            continue  # Skip empty components from double slashes

        # Check component length
        if len(component) > max_component_length:
            return (
                None,
                f"Path component '{component[:50]}...' exceeds maximum length "
                f"of {max_component_length} characters",
            )

        # Check for hidden files/folders at any level (starts with .)
        # We'll let the caller decide if they want to skip these
        # Just normalize here

    # Rebuild path without empty components
    clean_components = [c for c in components if c]
    if not clean_components:
        return None, "Path has no valid components"

    # Check for absolute path indicators (Windows drive letters)
    first_component = clean_components[0]
    if len(first_component) == 2 and first_component[1] == ":":
        return None, "Absolute paths (drive letters) not allowed"

    sanitized = "/".join(clean_components)
    return sanitized, ""


def is_zip_entry_symlink(zip_info: zipfile.ZipInfo) -> bool:
    """
    Check if a zip entry is a symbolic link.

    Symlinks in zip files are a security risk as they can point
    outside the extraction directory.

    Args:
        zip_info: ZipInfo object from the archive

    Returns:
        True if the entry is a symlink, False otherwise
    """
    # Unix symlinks are indicated by the external_attr field
    # The high 16 bits contain the Unix file mode
    # S_IFLNK (0xA000) indicates a symbolic link
    unix_mode = zip_info.external_attr >> 16
    return stat.S_ISLNK(unix_mode) if unix_mode else False


def is_hidden_or_system_file(path: str) -> bool:
    """
    Check if a path represents a hidden or system file to skip.

    Args:
        path: Sanitized path from zip

    Returns:
        True if the file should be skipped
    """
    # Get the filename (last component)
    filename = os.path.basename(path)

    # Skip hidden files (start with .)
    if filename.startswith("."):
        return True

    # Skip macOS resource fork directory
    if "__MACOSX" in path:
        return True

    # Skip common system files
    system_files = {
        "Thumbs.db",
        "desktop.ini",
        ".DS_Store",
        ".gitkeep",
        ".gitignore",
    }
    if filename in system_files:
        return True

    return False


def is_relationship_file(path: str) -> bool:
    """
    Check if a path is the relationships metadata file.

    The relationships file must be at the root level of the zip
    (not in a subdirectory) and match one of the allowed names.

    Args:
        path: Sanitized path from zip

    Returns:
        True if this is a relationships file at root level
    """
    # Must be at root (no folder separator)
    if "/" in path:
        return False

    # Check against allowed relationship file names
    return path in RELATIONSHIP_FILE_NAMES


def is_metadata_file(path: str) -> bool:
    """
    Check if a path is a document metadata file.

    The metadata file must be at the root level of the zip
    (not in a subdirectory) and match one of the allowed names.

    Args:
        path: Sanitized path from zip

    Returns:
        True if this is a metadata file at root level
    """
    # Must be at root (no folder separator)
    if "/" in path:
        return False

    # Check against allowed metadata file names
    return path in METADATA_FILE_NAMES


# Allowed names for the labels definition file at zip root.
# Intentionally case-sensitive — only these exact names are recognised.
LABELS_FILE_NAMES = [
    "labels.json",
    "LABELS.json",
]


def is_labels_file(path: str) -> bool:
    """
    Check if a path is the labels definition file.

    The labels file must be at the root level of the zip
    (not in a subdirectory) and match one of the allowed names.

    Args:
        path: Sanitized path from zip

    Returns:
        True if this is a labels file at root level
    """
    if "/" in path:
        return False
    return path in LABELS_FILE_NAMES


def is_annotation_sidecar(path: str) -> bool:
    """
    Check if a path is a JSON annotation sidecar file.

    A sidecar is a .json file that shares the same basename as a
    document file (e.g. ``contracts/master.json`` is the sidecar for
    ``contracts/master.pdf``).  The labels file at root level is
    excluded.

    Note: This matches *any* .json file that isn't the labels file.
    The actual pairing with a document is done by stem-matching in
    ``validate_zip_for_import``.  This means a ``.json`` can pair
    with ``.txt`` or any other supported document type — not just
    PDFs — which is intentional but may be surprising.

    Args:
        path: Sanitized path from zip

    Returns:
        True if this is a .json file that could be an annotation sidecar
    """
    return path.lower().endswith(".json") and not is_labels_file(path)


def get_folder_path(file_path: str) -> str:
    """
    Extract the folder path from a file path.

    Args:
        file_path: Full path to a file

    Returns:
        Parent folder path, or empty string if file is at root

    Examples:
        >>> get_folder_path("docs/contracts/file.pdf")
        "docs/contracts"

        >>> get_folder_path("file.pdf")
        ""
    """
    if "/" not in file_path:
        return ""
    return "/".join(file_path.split("/")[:-1])


def get_folder_depth(folder_path: str) -> int:
    """
    Calculate the depth of a folder path.

    Args:
        folder_path: Folder path

    Returns:
        Depth (number of levels), 0 for root

    Examples:
        >>> get_folder_depth("")
        0

        >>> get_folder_depth("docs")
        1

        >>> get_folder_depth("docs/contracts/2024")
        3
    """
    if not folder_path:
        return 0
    return len(folder_path.split("/"))


def collect_all_folder_paths(folder_path: str) -> list[str]:
    """
    Collect all ancestor folder paths for a given path.

    Args:
        folder_path: Full folder path

    Returns:
        List of all paths from root to this folder

    Examples:
        >>> collect_all_folder_paths("docs/contracts/2024")
        ["docs", "docs/contracts", "docs/contracts/2024"]

        >>> collect_all_folder_paths("docs")
        ["docs"]

        >>> collect_all_folder_paths("")
        []
    """
    if not folder_path:
        return []

    parts = folder_path.split("/")
    paths = []
    for i in range(1, len(parts) + 1):
        paths.append("/".join(parts[:i]))
    return paths


def validate_zip_for_import(
    zip_file: zipfile.ZipFile,
    allowed_mimetypes: list[str] | None = None,
) -> ZipManifest:
    """
    Validate entire zip file for security issues before extraction.

    This function performs comprehensive security validation without
    extracting any content. It builds a manifest of files to process
    and folders to create.

    Args:
        zip_file: Open ZipFile object in read mode
        allowed_mimetypes: Optional list of allowed MIME types (not checked here,
                          just for documentation - actual MIME check happens during
                          extraction since we need file bytes)

    Returns:
        ZipManifest with validation results and file/folder lists

    Security checks performed:
        - Total file count within limits
        - Total uncompressed size within limits
        - Individual file sizes (marks oversized for skipping)
        - Compression ratio (flags suspicious files)
        - Symlink detection
        - Path sanitization for all entries
        - Folder depth validation
        - Folder count validation
    """
    manifest = ZipManifest(is_valid=True)

    # Read configurable limits once at call time so @override_settings and
    # env/deployment overrides are honoured (never frozen at import — see
    # opencontractserver/constants/zip_import.py for why).
    max_file_count = get_zip_max_file_count()
    max_total_size_bytes = get_zip_max_total_size_bytes()
    max_single_file_size_bytes = get_zip_max_single_file_size_bytes()
    max_compression_ratio = get_zip_max_compression_ratio()
    max_folder_depth = get_zip_max_folder_depth()
    max_folder_count = get_zip_max_folder_count()

    try:
        info_list = zip_file.infolist()
    except Exception as e:
        logger.warning(f"Failed to read zip file info: {e}")
        return ZipManifest(is_valid=False, error_message=f"Invalid zip file: {e}")

    manifest.total_files_in_zip = len(info_list)

    # Check total file count
    if manifest.total_files_in_zip > max_file_count:
        return ZipManifest(
            is_valid=False,
            error_message=(
                f"Zip contains {manifest.total_files_in_zip} files, "
                f"maximum allowed is {max_file_count}"
            ),
            total_files_in_zip=manifest.total_files_in_zip,
        )

    folder_paths_set: set[str] = set()
    total_size = 0

    for info in info_list:
        # Skip directories (they end with /)
        if info.filename.endswith("/"):
            continue

        # Check for symlinks
        if is_zip_entry_symlink(info):
            manifest.skipped_files.append(
                ZipFileEntry(
                    original_path=info.filename,
                    sanitized_path="",
                    folder_path="",
                    filename="",
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                    skip_reason="Symlinks not allowed",
                )
            )
            continue

        # Sanitize path
        sanitized_path, path_error = sanitize_zip_path(info.filename)
        if not sanitized_path:
            manifest.skipped_files.append(
                ZipFileEntry(
                    original_path=info.filename,
                    sanitized_path="",
                    folder_path="",
                    filename="",
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                    skip_reason=f"Invalid path: {path_error}",
                )
            )
            continue

        # Check for hidden/system files
        if is_hidden_or_system_file(sanitized_path):
            manifest.skipped_files.append(
                ZipFileEntry(
                    original_path=info.filename,
                    sanitized_path=sanitized_path,
                    folder_path="",
                    filename=os.path.basename(sanitized_path),
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                    skip_reason="Hidden or system file",
                )
            )
            continue

        # Check for relationship metadata file (only at root level)
        if is_relationship_file(sanitized_path):
            # Track the first relationship file found (lowercase takes priority
            # based on RELATIONSHIP_FILE_NAMES order)
            if manifest.relationship_file is None:
                manifest.relationship_file = info.filename
                logger.info(f"Found relationships file in zip: {info.filename}")
            else:
                logger.warning(
                    f"Multiple relationship files found in zip. "
                    f"Using {manifest.relationship_file}, ignoring {info.filename}"
                )
            # Don't add to valid_files - will be processed separately
            continue

        # Check for document metadata file (only at root level)
        if is_metadata_file(sanitized_path):
            # Track the first metadata file found (lowercase takes priority
            # based on METADATA_FILE_NAMES order)
            if manifest.metadata_file is None:
                manifest.metadata_file = info.filename
                logger.info(f"Found metadata file in zip: {info.filename}")
            else:
                logger.warning(
                    f"Multiple metadata files found in zip. "
                    f"Using {manifest.metadata_file}, ignoring {info.filename}"
                )
            # Don't add to valid_files - will be processed separately
            continue

        # Check for labels definition file (only at root level)
        if is_labels_file(sanitized_path):
            if manifest.labels_file is None:
                manifest.labels_file = info.filename
                logger.info(f"Found labels file in zip: {info.filename}")
            else:
                logger.warning(
                    f"Multiple labels files found in zip. "
                    f"Using {manifest.labels_file}, ignoring {info.filename}"
                )
            # Don't add to valid_files - will be processed separately
            continue

        # Get folder path and validate depth
        folder_path = get_folder_path(sanitized_path)
        if folder_path:
            depth = get_folder_depth(folder_path)
            if depth > max_folder_depth:
                manifest.skipped_files.append(
                    ZipFileEntry(
                        original_path=info.filename,
                        sanitized_path=sanitized_path,
                        folder_path=folder_path,
                        filename=os.path.basename(sanitized_path),
                        file_size=info.file_size,
                        compressed_size=info.compress_size,
                        skip_reason=(
                            f"Folder depth {depth} exceeds maximum of "
                            f"{max_folder_depth}"
                        ),
                    )
                )
                continue

            # Collect all ancestor folder paths
            all_paths = collect_all_folder_paths(folder_path)
            folder_paths_set.update(all_paths)

        # Track total size
        total_size += info.file_size

        # Check if total size exceeded
        if total_size > max_total_size_bytes:
            size_mb = max_total_size_bytes / (1024 * 1024)
            return ZipManifest(
                is_valid=False,
                error_message=(
                    f"Zip uncompressed size exceeds maximum of {size_mb:.0f}MB"
                ),
                total_files_in_zip=manifest.total_files_in_zip,
                total_uncompressed_size=total_size,
            )

        # Check individual file size
        is_oversized = info.file_size > max_single_file_size_bytes
        skip_reason = ""
        if is_oversized:
            size_mb = info.file_size / (1024 * 1024)
            limit_mb = max_single_file_size_bytes / (1024 * 1024)
            skip_reason = (
                f"File size ({size_mb:.1f}MB) exceeds limit ({limit_mb:.0f}MB)"
            )

        # Check compression ratio (potential zip bomb indicator)
        # We log but don't reject because:
        # 1. High ratios can be legitimate (e.g., highly compressible text)
        # 2. Total uncompressed size is already bounded by ZIP_MAX_TOTAL_SIZE_BYTES
        # 3. Individual file size is bounded by ZIP_MAX_SINGLE_FILE_SIZE_BYTES
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > max_compression_ratio:
                logger.warning(
                    f"High compression ratio ({ratio:.1f}:1) for file: "
                    f"{sanitized_path} - monitoring for potential zip bomb"
                )

        entry = ZipFileEntry(
            original_path=info.filename,
            sanitized_path=sanitized_path,
            folder_path=folder_path,
            filename=os.path.basename(sanitized_path),
            file_size=info.file_size,
            compressed_size=info.compress_size,
            is_oversized=is_oversized,
            skip_reason=skip_reason,
        )

        if is_oversized:
            manifest.skipped_files.append(entry)
        else:
            manifest.valid_files.append(entry)
            manifest.valid_files_size += info.file_size

    # Build annotation sidecar map: match .json files to document files.
    # A sidecar "foo/bar.json" pairs with "foo/bar.pdf" (or .docx, .txt, etc.)
    # by sharing the same stem (basename without extension) in the same folder.
    json_entries: list[ZipFileEntry] = []
    doc_entries: list[ZipFileEntry] = []
    for entry in manifest.valid_files:
        if is_annotation_sidecar(entry.sanitized_path):
            json_entries.append(entry)
        else:
            doc_entries.append(entry)

    if json_entries:
        # Build a lookup of stem (without extension) -> sanitized_path for docs
        doc_stems: dict[str, str] = {}
        for entry in doc_entries:
            stem = os.path.splitext(entry.sanitized_path)[0]
            doc_stems[stem] = entry.sanitized_path

        remaining_valid: list[ZipFileEntry] = list(doc_entries)
        for json_entry in json_entries:
            json_stem = os.path.splitext(json_entry.sanitized_path)[0]
            if json_stem in doc_stems:
                # This JSON is a sidecar for a document.
                # We store original_path (not sanitized_path) because
                # ZipFile.open() needs the exact entry name from the
                # central directory.  This is safe: ZipFile.open() does
                # a name lookup — it cannot perform filesystem traversal.
                manifest.annotation_sidecars[doc_stems[json_stem]] = (
                    json_entry.original_path
                )
                logger.info(
                    f"Found annotation sidecar: {json_entry.sanitized_path} "
                    f"-> {doc_stems[json_stem]}"
                )
                # Don't include the sidecar JSON in valid_files
            else:
                # Standalone JSON file with no matching document - keep it
                remaining_valid.append(json_entry)

        manifest.valid_files = remaining_valid

    # Check folder count
    if len(folder_paths_set) > max_folder_count:
        return ZipManifest(
            is_valid=False,
            error_message=(
                f"Zip contains {len(folder_paths_set)} folders, "
                f"maximum allowed is {max_folder_count}"
            ),
            total_files_in_zip=manifest.total_files_in_zip,
            total_uncompressed_size=total_size,
        )

    # Sort folder paths by depth (parents before children)
    manifest.folder_paths = sorted(folder_paths_set, key=lambda p: (p.count("/"), p))
    manifest.total_uncompressed_size = total_size

    logger.info(
        f"Zip validation complete: {len(manifest.valid_files)} valid files, "
        f"{len(manifest.skipped_files)} skipped, "
        f"{len(manifest.folder_paths)} folders to create"
    )

    return manifest
