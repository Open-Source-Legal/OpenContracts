from enum import Enum
from typing import Optional

# Metadata for each file type: (mimetype, human label, short label)
_FILE_TYPE_META: dict[str, tuple[str, str, str]] = {
    "pdf": ("application/pdf", "PDF", "PDF"),
    "txt": ("text/plain", "Plain Text", "TXT"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Word Document",
        "DOCX",
    ),
}


class FileTypeEnum(str, Enum):
    PDF = "pdf"
    TXT = "txt"
    DOCX = "docx"

    @property
    def mimetype(self) -> str:
        """Full MIME type string (e.g. 'application/pdf')."""
        return _FILE_TYPE_META[self.value][0]

    @property
    def label(self) -> str:
        """Human-readable label (e.g. 'PDF', 'Word Document')."""
        return _FILE_TYPE_META[self.value][1]

    @property
    def short_label(self) -> str:
        """Short label used for UI badges (e.g. 'PDF', 'TXT', 'DOCX')."""
        return _FILE_TYPE_META[self.value][2]

    @classmethod
    def from_mimetype(cls, mimetype: str) -> Optional["FileTypeEnum"]:
        """
        Convert a MIME type to a FileTypeEnum.

        Args:
            mimetype: The MIME type to convert

        Returns:
            The corresponding FileTypeEnum, or None if not found
        """
        for member in cls:
            if member.mimetype == mimetype:
                return member
        return None
