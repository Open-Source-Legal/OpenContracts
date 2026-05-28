"""
Truncation limit constants for string previews across the application.

Centralises magic numbers used when slicing strings for tool responses,
notification payloads, and display contexts.  Having them in one place
makes it straightforward to audit the truncation policy.

See also
--------
- ``constants/document_processing.py`` for ``MAX_PROCESSING_ERROR_LENGTH``,
  ``MAX_PROCESSING_TRACEBACK_LENGTH``, ``MAX_PROCESSING_ERROR_DISPLAY_LENGTH``.
- ``constants/corpus_actions.py`` for ``MAX_DESCRIPTION_PREVIEW_LENGTH``,
  ``MAX_MESSAGE_PREVIEW_LENGTH``.
"""

# Maximum characters of Note.content included in tool response previews.
MAX_NOTE_CONTENT_PREVIEW_LENGTH = 512

# Maximum characters of a document description returned in tool update
# responses (e.g. ``update_document_description`` result dict).
MAX_DESCRIPTION_RESPONSE_PREVIEW_LENGTH = 200

# Maximum total length for markdown-link titles (annotation / entity names).
# Titles exceeding this limit are truncated with an ellipsis suffix.
MAX_LINK_TITLE_LENGTH = 100

# Maximum characters of Document.description used as a title fallback
# when Document.title is empty (e.g. in notification messages).
MAX_DOC_TITLE_FALLBACK_LENGTH = 50

# Maximum characters of an error message stored in notification data payloads.
MAX_NOTIFICATION_ERROR_LENGTH = 500

# Maximum characters of the Corpus description preview projected from the
# Readme.CAML document body into ``Corpus.description_preview``. The preview
# is the single-paragraph excerpt shown in list/card surfaces; the full plain
# text projection lives in ``Corpus.description``. See the canonical-CAML
# refactor spec at
# ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``.
MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH = 280
