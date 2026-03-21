from enum import Enum

# Canonical mapping from MIME type strings to FileTypeEnum short labels.
# This is the single source of truth for MIME ↔ enum conversion.
MIME_TO_FILE_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

# Reverse mapping: short label → MIME type
FILE_TYPE_TO_MIME: dict[str, str] = {v: k for k, v in MIME_TO_FILE_TYPE.items()}

# Human-readable labels for each file type
FILE_TYPE_LABELS: dict[str, str] = {
    "pdf": "PDF",
    "txt": "Plain Text",
    "docx": "Word Document",
}

# Legacy MIME type aliases that should be accepted as equivalent
LEGACY_MIME_ALIASES: dict[str, str] = {
    "application/txt": "text/plain",
}


if len(FILE_TYPE_TO_MIME) != len(MIME_TO_FILE_TYPE):
    raise ValueError(
        "MIME_TO_FILE_TYPE has duplicate values — each file type must map to a unique MIME type"
    )


class FileTypeEnum(str, Enum):
    PDF = "pdf"
    TXT = "txt"
    DOCX = "docx"
    # HTML = "html"  # Removed as we don't support it
    # Add more as needed

    @classmethod
    def from_mimetype(cls, mimetype: str) -> "FileTypeEnum | None":
        """
        Convert a MIME type to a FileTypeEnum.

        Args:
            mimetype: The MIME type to convert

        Returns:
            The corresponding FileTypeEnum, or None if not found
        """
        # Resolve legacy aliases first
        resolved = LEGACY_MIME_ALIASES.get(mimetype, mimetype)
        file_type_value = MIME_TO_FILE_TYPE.get(resolved)
        if file_type_value is None:
            return None
        return cls(file_type_value)

    @property
    def mimetype(self) -> str:
        """Return the canonical MIME type string for this file type."""
        try:
            return FILE_TYPE_TO_MIME[self.value]
        except KeyError:
            raise KeyError(
                f"No MIME mapping for FileTypeEnum member {self.value!r}. "
                f"Add an entry to MIME_TO_FILE_TYPE in "
                f"opencontractserver/pipeline/base/file_types.py."
            )

    @property
    def label(self) -> str:
        """Return a human-readable label for this file type."""
        return FILE_TYPE_LABELS.get(self.value, self.value.upper())


# Enforce that every FileTypeEnum member has a MIME mapping at import time,
# so the .mimetype property can never raise KeyError at runtime.
_missing = {ft.value for ft in FileTypeEnum} - set(FILE_TYPE_TO_MIME)
if _missing:
    raise ValueError(f"FileTypeEnum members missing from MIME_TO_FILE_TYPE: {_missing}")
