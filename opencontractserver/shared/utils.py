import os
from typing import Any

from opencontractserver.constants.document_processing import (
    MAX_FILENAME_EXTENSION_LENGTH,
    MAX_FILENAME_LENGTH,
)


# This was originally more complex, but I'm keeping it as a standalone, centralized function to be able to update
# file paths globally if desired
def calc_oc_file_path(instance: Any, filename: str, sub_folder: str) -> str:
    return f"uploadfiles/{sub_folder}/{filename}"


def sanitize_corpus_filename(name: str, *, fallback: str = "untitled") -> str:
    """Sanitize *name* into a single safe corpus-filesystem filename segment.

    This is the **canonical** sanitisation for the filename portion of a
    ``DocumentPath.path``. The rule (shared with ``Corpus.add_document`` and
    the text-document import tool): keep alphanumerics plus ``-``, ``_`` and
    ``.``; collapse every other character (including path separators, so the
    result can never traverse directories) to ``_``; truncate to
    :data:`MAX_FILENAME_LENGTH`. If nothing survives, fall back to
    ``fallback`` so the path stays valid.

    Truncation preserves the **extension**: the stem is trimmed so that
    ``stem + extension`` fits within :data:`MAX_FILENAME_LENGTH`, rather than
    hard-slicing the whole string (which would drop the extension off a long
    filename). This matters for the pre-parse file converter, whose
    convert-vs-skip decision keys off the stored file's extension — a
    130-char ``…annual_report.pages`` upload must not be stored as
    ``…annual_repo`` (extension lost) or it would be accepted at upload but
    silently never converted. The extension itself is capped at
    :data:`MAX_FILENAME_EXTENSION_LENGTH` so a pathological "extension" can't
    consume the whole budget.

    Note: because distinct inputs can collapse to the same output
    (``"My Doc"`` and ``"My_Doc"`` both become ``"My_Doc"``), callers that
    derive a path from this must still disambiguate against existing paths.
    Runs are **not** collapsed — each disallowed character maps to its own
    ``_`` (``"My  File"`` -> ``"My__File"``), which is intentional so the
    mapping stays char-for-char reversible-ish and predictable; do not expect
    a single separator out of multiple.
    """
    stem, ext = os.path.splitext(name or "")
    # Bound the extension first so a pathological "extension" (e.g. a filename
    # that is one long dotted token) can't eat the entire length budget and
    # starve the stem.
    ext = ext[:MAX_FILENAME_EXTENSION_LENGTH]
    stem = stem[: max(0, MAX_FILENAME_LENGTH - len(ext))]
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in (stem + ext))
    return safe or fallback
