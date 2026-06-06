from typing import Any

from opencontractserver.constants.document_processing import MAX_FILENAME_LENGTH


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

    Note: because distinct inputs can collapse to the same output
    (``"My Doc"`` and ``"My_Doc"`` both become ``"My_Doc"``), callers that
    derive a path from this must still disambiguate against existing paths.
    Runs are **not** collapsed — each disallowed character maps to its own
    ``_`` (``"My  File"`` -> ``"My__File"``), which is intentional so the
    mapping stays char-for-char reversible-ish and predictable; do not expect
    a single separator out of multiple.
    """
    truncated = (name or "")[:MAX_FILENAME_LENGTH]
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in truncated)
    return safe or fallback
