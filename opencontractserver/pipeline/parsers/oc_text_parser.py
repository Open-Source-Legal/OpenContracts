import logging
from dataclasses import dataclass, field
from typing import Any, Optional, cast

from django.core.files.storage import default_storage

from opencontractserver.annotations.models import SPAN_LABEL
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.pipeline.parsers.text_chunkers import (
    SENTENCE_CHUNK_LABEL,
    BaseTextChunker,
    ChunkerSpec,
    TextChunk,
    get_chunker,
)
from opencontractserver.types.dicts import (
    AnnotationLabelPythonType,
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    TextSpanData,
)
from opencontractserver.types.enums import LabelType

logger = logging.getLogger(__name__)


# Default chunking recipe: sentence-only, matching the historical behaviour
# of TxtParser prior to the pluggable-chunker migration.
DEFAULT_CHUNKERS: list[ChunkerSpec] = [{"name": "sentence"}]


class TxtParser(BaseParser):
    """
    Parser that processes plain text documents into structural annotations.

    Chunking granularity is pluggable: the parser iterates one or more
    ``BaseTextChunker`` strategies (see ``text_chunkers``) and stores each
    chunk as a ``SPAN_LABEL`` structural annotation. The default is a
    single sentence-level chunker so existing corpora are unchanged, but
    operators can stack strategies (e.g. sentence + paragraph) to index
    multiple retrieval granularities at once.
    """

    title = "Text Parser"
    description = (
        "Parses plain text documents and splits them into configurable "
        "structural chunks (sentences, paragraphs, sliding windows)."
    )
    author = "OpenContracts"
    # SentenceChunker additionally requires the optional ``spacy`` package,
    # but that dependency is only loaded when the sentence strategy is
    # actually used; leaving the base parser's dependency list empty keeps
    # non-sentence pipelines (paragraph / sliding-window) dependency-free.
    dependencies: list[str] = []
    supported_file_types = [FileTypeEnum.TXT]

    @dataclass
    class Settings:
        """Configuration schema for :class:`TxtParser`."""

        # ``chunkers`` is a list of ``ChunkerSpec`` entries. Each entry is
        # either a bare name ("sentence") or a mapping with ``name`` plus
        # strategy-specific keyword arguments:
        #     {"name": "sliding_window", "window_size": 1200, "overlap": 200}
        # Using a list (rather than a single value) lets a single parse run
        # index the document at multiple retrieval granularities at once.
        chunkers: list[ChunkerSpec] = field(
            default_factory=lambda: list(DEFAULT_CHUNKERS),
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description=(
                        "Ordered list of chunking strategies applied to the "
                        "document text. Each entry is either a chunker name "
                        "(e.g. 'sentence') or a mapping with 'name' plus "
                        "strategy kwargs (e.g. {'name': 'sliding_window', "
                        "'window_size': 1200, 'overlap': 200}). Defaults to "
                        "['sentence']."
                    ),
                )
            },
        )

    def __init__(self) -> None:
        """Initialise the parser. Chunker instantiation is deferred to parse time."""
        super().__init__()

    def _resolve_chunkers(
        self, override: Optional[list[ChunkerSpec]] = None
    ) -> list[BaseTextChunker]:
        """
        Resolve the active list of chunker instances for a parse call.

        Resolution order: explicit ``override`` kwarg → parser settings →
        :data:`DEFAULT_CHUNKERS`. An empty list from either source also
        falls back to the default, so a misconfiguration never produces a
        document with zero structural annotations. Note that ``override=[]``
        means "caller explicitly asked for no chunkers" but we still emit
        DEFAULT_CHUNKERS (with a warning) because a zero-chunker parse is
        never useful downstream.
        """
        if override is not None:
            specs = override
        elif self.settings is not None and self.settings.chunkers:
            specs = self.settings.chunkers
        else:
            specs = DEFAULT_CHUNKERS

        if not specs:
            logger.warning(
                "TxtParser received an empty chunker list; "
                "falling back to DEFAULT_CHUNKERS."
            )
            specs = DEFAULT_CHUNKERS

        return [get_chunker(spec) for spec in specs]

    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Parse a text document into structural annotations using the
        configured chunking strategies.

        Call-time ``chunkers=[...]`` in ``all_kwargs`` overrides the
        per-component settings for this invocation only — useful for
        benchmark sweeps that want to compare strategies without touching
        ``PipelineSettings``.
        """
        logger.info(
            f"TxtParser - Parsing doc {doc_id} for user {user_id} "
            f"with effective kwargs: {all_kwargs}"
        )

        document = Document.objects.get(pk=doc_id)

        if not document.txt_extract_file.name:
            logger.error(f"No txt file found for document {doc_id}")
            return None

        txt_path = document.txt_extract_file.name
        with default_storage.open(txt_path, mode="r") as txt_file:
            text_content = txt_file.read()

        chunker_override = all_kwargs.get("chunkers")
        if chunker_override is not None and not isinstance(chunker_override, list):
            raise TypeError(
                "chunkers kwarg must be a list of ChunkerSpec (dict/string) "
                f"entries, got {type(chunker_override).__name__}"
            )
        chunkers = self._resolve_chunkers(chunker_override)
        logger.info(
            f"TxtParser - doc {doc_id}: applying {len(chunkers)} chunker(s): "
            f"{[type(c).__name__ for c in chunkers]}"
        )

        # Base envelope shared across strategies. Labels and annotations
        # are filled in as we iterate the chunkers.
        open_contracts_data: OpenContractDocExport = {
            "title": document.title or "",
            "content": text_content,
            "description": document.description or "",
            "pawls_file_content": [],  # No PAWLS data for plain text
            "page_count": 1,  # Single page
            "doc_labels": [],
            "labelled_text": [],
        }

        text_labels: dict[str, AnnotationLabelPythonType] = {}
        labelled_text: list[OpenContractsAnnotationPythonType] = []

        for chunker in chunkers:
            chunks_produced = 0
            for chunk in chunker.chunk(text_content):
                label_name = chunk.label or SENTENCE_CHUNK_LABEL
                if label_name not in text_labels:
                    text_labels[label_name] = _make_label(label_name)

                labelled_text.append(_annotation_for_chunk(chunk, label_name))
                chunks_produced += 1

            logger.debug(
                f"TxtParser - doc {doc_id}: {type(chunker).__name__} "
                f"produced {chunks_produced} chunk(s)"
            )

        # ``text_labels`` is not part of the OpenContractDocExport TypedDict
        # surface but downstream pipelines tolerate (and historically read)
        # the key off the per-doc payload, so we keep the assignment via a
        # widened cast rather than dropping it.
        cast(dict[str, Any], open_contracts_data)["text_labels"] = text_labels
        open_contracts_data["labelled_text"] = labelled_text

        return open_contracts_data


def _make_label(label_name: str) -> AnnotationLabelPythonType:
    """Build the ``AnnotationLabelPythonType`` stub used for a chunker's label.

    The caller fills in ``id`` post-import; we cast through ``dict`` so the
    placeholder ``None`` doesn't violate the strict type surface here.
    """
    label: dict[str, Any] = {
        "id": None,  # ID will be assigned when saved to the database
        "color": "grey",
        "description": f"Structural {label_name.lower()} chunk",
        "icon": "expand",
        "text": label_name,
        "label_type": LabelType(SPAN_LABEL),
        "parent_id": None,
    }
    return cast(AnnotationLabelPythonType, label)


def _annotation_for_chunk(
    chunk: TextChunk, label_name: str
) -> OpenContractsAnnotationPythonType:
    """Convert a :class:`TextChunk` into an ``OpenContractsAnnotationPythonType``."""
    span: TextSpanData = {
        "start": chunk.start,
        "end": chunk.end,
        "text": chunk.text,
    }
    annotation: OpenContractsAnnotationPythonType = {
        "id": None,
        "annotationLabel": label_name,
        "rawText": chunk.text,
        "page": 1,
        "annotation_json": span,
        "parent_id": None,
        "annotation_type": "SPAN_LABEL",
        "structural": True,
        "content_modalities": ["TEXT"],
    }
    return annotation
