"""
Pluggable text-chunking strategies for text-based parsers.

A chunker takes raw document text and emits a sequence of ``TextChunk``
objects.  Each chunk carries its character-level ``[start, end)`` span, the
raw text and the annotation-label name under which it should be stored.
Parsers convert the chunks into structural ``SPAN_LABEL`` annotations.

The strategies live behind a single abstraction so text-oriented parsers
(``TxtParser`` today, any future plain-text parser tomorrow) can select the
retrieval granularity that best matches the downstream workload — sentences
for fine-grained UI interactions, paragraphs or fixed character windows for
RAG retrieval.

Strategies are looked up by name via :func:`get_chunker`.  Adding a new
strategy is a two-line change (class definition + ``register_chunker``
decorator). ``SentenceChunker`` additionally requires the optional
``spacy`` dependency.

Example::

    from opencontractserver.pipeline.parsers.text_chunkers import get_chunker

    chunker = get_chunker({"name": "sliding_window", "window_size": 1200})
    for chunk in chunker.chunk(text):
        ...
"""

from __future__ import annotations

import logging
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Union

from opencontractserver.constants.document_processing import (
    DEFAULT_SENTENCE_CHUNKER_MODEL,
    DEFAULT_SLIDING_WINDOW_OVERLAP,
    DEFAULT_SLIDING_WINDOW_SIZE,
    MAX_WORD_BOUNDARY_SCAN_CHARS,
)

logger = logging.getLogger(__name__)


# Annotation labels used by the built-in strategies. Exposed as module-level
# constants so callers (parsers, tests, benchmarks) can refer to them without
# hard-coding the string; each label is tied to the strategy that emits it.
SENTENCE_CHUNK_LABEL = "SENTENCE"
PARAGRAPH_CHUNK_LABEL = "PARAGRAPH"
SLIDING_WINDOW_CHUNK_LABEL = "WINDOW"


@dataclass(frozen=True)
class TextChunk:
    """
    A single chunk of document text with its character offsets and label.

    Attributes:
        start: Inclusive character offset into the original text.
        end: Exclusive character offset into the original text.
        text: The text content of the chunk (``original_text[start:end]``).
        label: Annotation-label name under which the chunk is stored
            (e.g. ``"SENTENCE"``, ``"PARAGRAPH"``). Each strategy emits a
            single label so the retrieval layer can filter by granularity.
    """

    start: int
    end: int
    text: str
    label: str


# Spec for selecting + configuring a chunker. Either a bare name
# ("paragraph") or a mapping with "name" plus strategy-specific kwargs.
ChunkerSpec = Union[str, Mapping[str, Any]]


class BaseTextChunker(ABC):
    """
    Abstract base class for text-chunking strategies.

    Concrete subclasses declare a unique ``name`` (the registry key) and a
    default ``label`` (the annotation-label name for chunks they emit).
    They implement :meth:`chunk` to yield ``TextChunk`` instances.

    Subclass authors should keep :meth:`chunk` a pure function of the input
    text — no I/O, no global state. Lazy-loading heavy dependencies in
    ``__init__`` is fine.
    """

    #: Registry key. Must be unique across all registered chunkers.
    name: ClassVar[str] = ""

    #: Default annotation label for chunks produced by this strategy.
    label: ClassVar[str] = ""

    @abstractmethod
    def chunk(self, text: str) -> Iterable[TextChunk]:
        """Yield :class:`TextChunk` objects covering ``text``."""


_CHUNKER_REGISTRY: dict[str, type[BaseTextChunker]] = {}


def register_chunker(cls: type[BaseTextChunker]) -> type[BaseTextChunker]:
    """
    Class decorator that registers a chunker under its declared ``name``.

    Raises:
        ValueError: If ``cls.name`` is empty or already registered.
    """
    key = cls.name
    if not key:
        raise ValueError(
            f"Chunker {cls.__name__} must declare a non-empty 'name' class attribute"
        )
    existing = _CHUNKER_REGISTRY.get(key)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Chunker name '{key}' is already registered by "
            f"{existing.__module__}.{existing.__name__}"
        )
    _CHUNKER_REGISTRY[key] = cls
    return cls


def available_chunker_names() -> list[str]:
    """Return the sorted list of registered chunker names."""
    return sorted(_CHUNKER_REGISTRY)


def get_chunker(spec: ChunkerSpec) -> BaseTextChunker:
    """
    Instantiate a chunker from a name or a ``{"name": ..., **kwargs}`` mapping.

    ``spec`` can be:

    * ``"sentence"`` — shorthand for the default-configured strategy.
    * ``{"name": "sliding_window", "window_size": 1200, "overlap": 200}`` —
      strategy name plus keyword arguments for its ``__init__``.

    Raises:
        ValueError: If the name is unknown or the spec shape is invalid.
    """
    if isinstance(spec, str):
        name, kwargs = spec, {}
    elif isinstance(spec, Mapping):
        try:
            name = spec["name"]
        except KeyError as exc:
            raise ValueError("Chunker spec dict must contain a 'name' key") from exc
        kwargs = {k: v for k, v in spec.items() if k != "name"}
    else:
        raise ValueError(
            f"Chunker spec must be a str or a mapping with 'name', got {type(spec).__name__}"
        )

    try:
        cls = _CHUNKER_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown chunker '{name}'. Available: {available_chunker_names()}"
        ) from exc

    return cls(**kwargs)


@register_chunker
class SentenceChunker(BaseTextChunker):
    """
    Sentence-level chunker backed by spaCy.

    Preserves the existing ``TxtParser`` behaviour so existing corpora are
    unchanged. The spaCy model is cached per model name on the class so
    repeated instantiations (common in test suites and benchmark loops)
    do not reload ``en_core_web_lg`` from disk.
    """

    name: ClassVar[str] = "sentence"
    label: ClassVar[str] = SENTENCE_CHUNK_LABEL

    # Cache of loaded spaCy pipelines keyed by model name. Loading
    # en_core_web_lg takes multiple seconds, so reloading on every
    # ``get_chunker({"name": "sentence"})`` call is a real cost.
    _nlp_cache: ClassVar[dict[str, Any]] = {}
    # Guards against two concurrent constructors triggering the multi-second
    # spacy.load for the same model. Instance access after construction is
    # read-only so no lock is needed on the hot path.
    _nlp_cache_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, model: str = DEFAULT_SENTENCE_CHUNKER_MODEL) -> None:
        # Imported lazily so test suites that only exercise non-spaCy
        # strategies don't pay the import cost.
        import spacy

        self._model_name = model
        nlp = self._nlp_cache.get(model)
        if nlp is None:
            with self._nlp_cache_lock:
                nlp = self._nlp_cache.get(model)
                if nlp is None:
                    nlp = spacy.load(model)
                    self._nlp_cache[model] = nlp
        self._nlp = nlp

    def chunk(self, text: str) -> Iterator[TextChunk]:
        if not text:
            return
        doc = self._nlp(text)
        for sent in doc.sents:
            # Skip whitespace-only sentences from spaCy's segmentation.
            sentence_text = sent.text
            if not sentence_text.strip():
                continue
            # Trim leading/trailing whitespace for span hygiene, matching
            # ParagraphChunker behaviour so downstream annotation offsets
            # align regardless of which chunker produced them.
            start_char = sent.start_char + (
                len(sentence_text) - len(sentence_text.lstrip())
            )
            end_char = sent.end_char - (
                len(sentence_text) - len(sentence_text.rstrip())
            )
            trimmed = text[start_char:end_char]
            if not trimmed:
                continue
            yield TextChunk(
                start=start_char,
                end=end_char,
                text=trimmed,
                label=self.label,
            )


# Pre-compiled pattern for ParagraphChunker. A paragraph boundary is one
# or more blank lines (optionally containing whitespace). Matching the
# separator rather than splitting lets us keep accurate character offsets
# even when the separator width varies.
_PARAGRAPH_SEPARATOR_RE = re.compile(r"\n[ \t]*(?:\n[ \t]*)+")


@register_chunker
class ParagraphChunker(BaseTextChunker):
    """
    Paragraph-level chunker that splits on blank-line boundaries.

    Two adjacent ``\\n`` characters (optionally with surrounding spaces/tabs)
    mark a paragraph boundary. Character offsets are preserved so downstream
    span-highlighting still works.

    Parameters:
        min_chars: Drop paragraphs shorter than this many non-whitespace
            characters. Defaults to ``1`` (only empty paragraphs are dropped).
            Useful for filtering page headers / footers on noisy extracts.
        max_chars: If set, paragraphs longer than this are further split
            into ``max_chars``-long sub-chunks at whitespace boundaries
            (no overlap). ``None`` disables the cap. This keeps individual
            embedding inputs under tokenizer limits for pathologically long
            paragraphs without silently truncating them.
    """

    name: ClassVar[str] = "paragraph"
    label: ClassVar[str] = PARAGRAPH_CHUNK_LABEL

    def __init__(
        self,
        min_chars: int = 1,
        max_chars: int | None = None,
    ) -> None:
        if min_chars < 0:
            raise ValueError(f"min_chars must be >= 0, got {min_chars}")
        if max_chars is not None and max_chars <= 0:
            raise ValueError(f"max_chars must be > 0 when set, got {max_chars}")
        self.min_chars = min_chars
        self.max_chars = max_chars

    def chunk(self, text: str) -> Iterator[TextChunk]:
        if not text:
            return

        # Walk the separator matches so we can reconstruct each paragraph's
        # span from the offsets between separators.
        cursor = 0
        raw_spans: list[tuple[int, int]] = []
        for match in _PARAGRAPH_SEPARATOR_RE.finditer(text):
            sep_start, sep_end = match.span()
            if sep_start > cursor:
                raw_spans.append((cursor, sep_start))
            cursor = sep_end
        if cursor < len(text):
            raw_spans.append((cursor, len(text)))

        for start, end in raw_spans:
            paragraph = text[start:end]
            # Trim surrounding whitespace on a per-paragraph basis so we do
            # not count leading/trailing newlines toward min_chars.
            trimmed_start = start + (len(paragraph) - len(paragraph.lstrip()))
            trimmed_end = end - (len(paragraph) - len(paragraph.rstrip()))
            if trimmed_end <= trimmed_start:
                continue
            trimmed_text = text[trimmed_start:trimmed_end]
            if len(trimmed_text.strip()) < self.min_chars:
                continue

            if self.max_chars is None or len(trimmed_text) <= self.max_chars:
                yield TextChunk(
                    start=trimmed_start,
                    end=trimmed_end,
                    text=trimmed_text,
                    label=self.label,
                )
                continue

            # Paragraph is longer than max_chars: split at whitespace to keep
            # tokens intact. Sub-chunks inherit the paragraph label — they
            # are still paragraph-granularity retrieval units, just capped.
            yield from _split_long_span(
                text=text,
                start=trimmed_start,
                end=trimmed_end,
                window_size=self.max_chars,
                overlap=0,
                label=self.label,
                respect_word_boundaries=True,
            )


@register_chunker
class SlidingWindowChunker(BaseTextChunker):
    """
    Fixed-width sliding-window chunker with configurable overlap.

    Produces chunks of approximately ``window_size`` characters with
    ``overlap`` characters of context shared between neighbours. Matches
    the LangChain-style recipe that is common in RAG benchmarks.

    Parameters:
        window_size: Target chunk length in characters. Must be positive.
        overlap: Number of characters shared between consecutive chunks.
            Must be non-negative and strictly less than ``window_size``.
        respect_word_boundaries: If ``True`` (default), extend each window
            forward to the next whitespace boundary so words are not split
            across chunks. This makes individual chunks slightly larger
            than ``window_size`` but avoids producing fragment tokens
            that hurt embedding quality. Note: overlap is measured from
            the *snapped* boundary, so actual shared characters between
            neighbours may be smaller than ``overlap`` when a long word
            forced the boundary forward.

    The window is measured in *characters*, not tokens. Callers sizing
    against a tokenizer should pick a conservative ``window_size`` (a
    safe rule of thumb is ``tokens * 4`` for English text).
    """

    name: ClassVar[str] = "sliding_window"
    label: ClassVar[str] = SLIDING_WINDOW_CHUNK_LABEL

    def __init__(
        self,
        window_size: int = DEFAULT_SLIDING_WINDOW_SIZE,
        overlap: int = DEFAULT_SLIDING_WINDOW_OVERLAP,
        respect_word_boundaries: bool = True,
    ) -> None:
        if window_size <= 0:
            raise ValueError(f"window_size must be > 0, got {window_size}")
        if overlap < 0:
            raise ValueError(f"overlap must be >= 0, got {overlap}")
        if overlap >= window_size:
            raise ValueError(
                f"overlap ({overlap}) must be < window_size ({window_size}) "
                "to avoid infinite loops"
            )
        self.window_size = window_size
        self.overlap = overlap
        self.respect_word_boundaries = respect_word_boundaries

    def chunk(self, text: str) -> Iterator[TextChunk]:
        if not text:
            return
        yield from _split_long_span(
            text=text,
            start=0,
            end=len(text),
            window_size=self.window_size,
            overlap=self.overlap,
            label=self.label,
            respect_word_boundaries=self.respect_word_boundaries,
        )


def _split_long_span(
    *,
    text: str,
    start: int,
    end: int,
    window_size: int,
    overlap: int,
    label: str,
    respect_word_boundaries: bool,
) -> Iterator[TextChunk]:
    """
    Emit sliding-window chunks covering ``text[start:end]``.

    Shared by ``SlidingWindowChunker`` and ``ParagraphChunker``'s oversize
    fallback so both paths handle whitespace snapping identically.
    """
    # Guarded by the constructors; re-checked here because this helper is
    # exported for internal reuse and a zero step would loop forever.
    if window_size <= overlap:
        raise ValueError(f"window_size ({window_size}) must exceed overlap ({overlap})")

    cursor = start
    while cursor < end:
        window_end = min(cursor + window_size, end)

        if respect_word_boundaries and window_end < end:
            # Walk forward to the next whitespace so we don't cut a word.
            # Cap the scan so a pathological no-whitespace input can't turn
            # this into O(n²) over the span.
            extended = window_end
            scan_limit = min(end, window_end + MAX_WORD_BOUNDARY_SCAN_CHARS)
            while extended < scan_limit and not text[extended].isspace():
                extended += 1
            window_end = extended

        # Trim trailing whitespace on the emitted chunk for cleaner spans.
        trimmed_end = window_end
        while trimmed_end > cursor and text[trimmed_end - 1].isspace():
            trimmed_end -= 1
        # And trim leading whitespace so overlap-introduced leading
        # whitespace doesn't shift offsets inside the chunk.
        trimmed_start = cursor
        while trimmed_start < trimmed_end and text[trimmed_start].isspace():
            trimmed_start += 1

        if trimmed_end > trimmed_start:
            yield TextChunk(
                start=trimmed_start,
                end=trimmed_end,
                text=text[trimmed_start:trimmed_end],
                label=label,
            )

        if window_end >= end:
            break
        # Advance from the snapped window end so word-boundary extension
        # does not silently grow the overlap between neighbouring chunks.
        # ``max(cursor + 1, ...)`` protects against pathological cases where
        # a huge word pushed window_end well past cursor + window_size — we
        # must still make at least one character of forward progress.
        cursor = max(cursor + 1, window_end - overlap)
