"""Framework-agnostic core tool functions for document and note operations.

This package preserves the public surface of the original
``opencontractserver.llms.tools.core_tools`` module — every name that used to
live in the single-file module is still importable from this path.  The
implementation has been split into category-specific submodules
(``notes``, ``descriptions``, ``annotations`` etc.) to keep individual files at
a reviewable size; the re-exports below ensure no consumer needs to update
import paths.
"""

import logging

# Re-export model classes that historically lived at the module level.  Tests
# patch attributes such as ``opencontractserver.llms.tools.core_tools.Document``
# directly, so these names must remain accessible on the package namespace.
from opencontractserver.annotations.models import Note, NoteRevision  # noqa: F401
from opencontractserver.corpuses.models import (  # noqa: F401
    Corpus,
    CorpusDescriptionRevision,
)
from opencontractserver.documents.models import Document  # noqa: F401

from ._helpers import (  # noqa: F401
    _apply_ndiff_patch,
    _db_sync_to_async,
    _token_count,
)
from .annotations import (  # noqa: F401
    AnnotationItem,
    aadd_annotations_from_exact_strings,
    add_annotations_from_exact_strings,
    aduplicate_annotations_with_label,
    duplicate_annotations_with_label,
)
from .caml_article import (  # noqa: F401
    CAML_ARTICLE_TITLE,
    aapply_caml_article_edit,
    apropose_caml_citation_match,
    aread_corpus_caml_article,
)
from .descriptions import (  # noqa: F401
    aget_corpus_description,
    aget_document_description,
    aupdate_corpus_description,
    aupdate_document_description,
    get_corpus_description,
    get_document_description,
    update_corpus_description,
    update_document_description,
)
from .document_indexing import (  # noqa: F401
    IndexEntryItem,
    acreate_document_index,
    create_document_index,
)
from .document_summaries import (  # noqa: F401
    aget_document_summary,
    aget_document_summary_at_version,
    aget_document_summary_diff,
    aget_document_summary_versions,
    aupdate_document_summary,
    get_document_summary,
    get_document_summary_at_version,
    get_document_summary_diff,
    get_document_summary_versions,
    update_document_summary,
)
from .documents import amove_document, move_document  # noqa: F401
from .links import acreate_markdown_link, create_markdown_link  # noqa: F401
from .md_summaries import (  # noqa: F401
    aget_md_summary_token_length,
    aload_document_md_summary,
    get_md_summary_token_length,
    load_document_md_summary,
)
from .memory import aget_corpus_memory, asuggest_memory_update  # noqa: F401
from .notes import (  # noqa: F401
    aadd_document_note,
    add_document_note,
    aget_note_content_token_length,
    aget_notes_for_document_corpus,
    aget_partial_note_content,
    asearch_document_notes,
    aupdate_document_note,
    get_note_content_token_length,
    get_notes_for_document_corpus,
    get_partial_note_content,
    search_document_notes,
    update_document_note,
)
from .page_images import aget_page_image, get_page_image  # noqa: F401
from .search import (  # noqa: F401
    asearch_exact_text_as_sources,
    search_exact_text_as_sources,
)
from .text_extracts import (  # noqa: F401
    _DOC_TXT_CACHE,
    aload_document_txt_extract,
    load_document_txt_extract,
)

logger = logging.getLogger(__name__)

__all__ = [
    # Helpers (kept private but historically importable from this module)
    "_DOC_TXT_CACHE",
    "_apply_ndiff_patch",
    "_db_sync_to_async",
    "_token_count",
    # Re-exported model classes (test patch targets)
    "Corpus",
    "CorpusDescriptionRevision",
    "Document",
    "Note",
    "NoteRevision",
    # md_summary file helpers
    "aget_md_summary_token_length",
    "aload_document_md_summary",
    "get_md_summary_token_length",
    "load_document_md_summary",
    # Notes
    "aadd_document_note",
    "add_document_note",
    "aget_note_content_token_length",
    "aget_notes_for_document_corpus",
    "aget_partial_note_content",
    "asearch_document_notes",
    "aupdate_document_note",
    "get_note_content_token_length",
    "get_notes_for_document_corpus",
    "get_partial_note_content",
    "search_document_notes",
    "update_document_note",
    # Plain-text extracts
    "aload_document_txt_extract",
    "load_document_txt_extract",
    # Descriptions
    "aget_corpus_description",
    "aget_document_description",
    "aupdate_corpus_description",
    "aupdate_document_description",
    "get_corpus_description",
    "get_document_description",
    "update_corpus_description",
    "update_document_description",
    # Document summary versioning
    "aget_document_summary",
    "aget_document_summary_at_version",
    "aget_document_summary_diff",
    "aget_document_summary_versions",
    "aupdate_document_summary",
    "get_document_summary",
    "get_document_summary_at_version",
    "get_document_summary_diff",
    "get_document_summary_versions",
    "update_document_summary",
    # Annotations
    "AnnotationItem",
    "aadd_annotations_from_exact_strings",
    "add_annotations_from_exact_strings",
    "aduplicate_annotations_with_label",
    "duplicate_annotations_with_label",
    # CAML article review (Readme.CAML)
    "CAML_ARTICLE_TITLE",
    "aapply_caml_article_edit",
    "apropose_caml_citation_match",
    "aread_corpus_caml_article",
    # Document indexing
    "IndexEntryItem",
    "acreate_document_index",
    "create_document_index",
    # Search
    "asearch_exact_text_as_sources",
    "search_exact_text_as_sources",
    # Page images
    "aget_page_image",
    "get_page_image",
    # Markdown links
    "acreate_markdown_link",
    "create_markdown_link",
    # Document movement
    "amove_document",
    "move_document",
    # Corpus memory
    "aget_corpus_memory",
    "asuggest_memory_update",
]
