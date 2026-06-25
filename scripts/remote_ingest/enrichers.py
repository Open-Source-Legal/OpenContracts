#!/usr/bin/env python3
"""
Pluggable pre-processing / enrichment stage for the remote-ingest worker.

After the remote worker parses a PDF (faithful Docling output) and before it
embeds + uploads it, user-supplied *enrichers* run to CALCULATE and INJECT
additional artifacts onto the document:

* typed corpus metadata         -> Column/Datacell (the UI's "document
                                   metadata", successor to legacy metadata
                                   annotations) via Enrichment.metadata /
                                   metadata_field()
* freeform document metadata    -> Document.custom_meta (a JSON blob)
* document-type labels          -> DOC_TYPE_LABEL annotations
* extra token annotations       -> labelled_text (e.g. detected clauses, dates,
                                   parties) — these get embedded + ingested just
                                   like the parser's own annotations
* annotation-to-annotation relationships

An enricher is any callable ``(EnricherContext) -> Enrichment | None`` discovered
from a dotted path (``--enricher pkg.module:func`` / ``OC_ENRICHERS``). The
context exposes correctness helpers — ``find_token_matches(regex)`` and
``token_annotation(label, match)`` — that build a *valid* ``annotation_json``
(union bounds + token indices + rawText) so injected annotations are faithful
and render correctly. ``validate_enrichment`` enforces the worker-upload rules
before upload, so a buggy enricher fails the document loudly instead of silently
shipping a broken annotation.

This module is intentionally light on imports (only ``expand_pawls_pages`` from
OpenContracts, which pulls in no Django models) so it is unit-testable without a
full Django bootstrap.

Trust model: enrichers are arbitrary Python the OPERATOR supplies and runs on
THEIR OWN worker host (``--enricher module:callable``). The worker imports and
executes them with the worker's privileges — they are first-party code, exactly
like the rest of the worker, not untrusted input. Don't load enricher modules you
didn't write. Output (``custom_meta``, annotations) is sent to the target like
any worker upload; ``custom_meta`` is stored verbatim on ``Document.custom_meta``
(GenericScalar JSON, escaped at the GraphQL/UI layer per the project's
XSS-prevention rule). Note the authority-corpus system also writes
``custom_meta`` — avoid colliding with its keys (``canonical_key``, ``authority``,
``authority_aliases``, ``source_url``) on authority corpora.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from re import Pattern
from typing import Callable, Optional

from opencontractserver.utils.compact_pawls import expand_pawls_pages

# Annotation type / label-type constants (mirrors opencontractserver.annotations).
TOKEN_LABEL = "TOKEN_LABEL"
SPAN_LABEL = "SPAN_LABEL"
DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"


# ---------------------------------------------------------------------------
# Public result + context types
# ---------------------------------------------------------------------------


@dataclass
class TokenMatch:
    """A run of PAWLs tokens on a single page that matched a query."""

    page: int
    token_indices: list[int]
    text: str


@dataclass
class Enrichment:
    """What an enricher returns. All fields optional / additive."""

    # Document-level overrides (None = leave the worker's default).
    title: str | None = None
    description: str | None = None
    # Structured metadata merged onto Document.custom_meta.
    custom_meta: dict = field(default_factory=dict)
    # Document-type label NAMES to apply, plus their definitions.
    doc_labels: list[str] = field(default_factory=list)
    doc_label_defs: dict[str, dict] = field(default_factory=dict)
    # Extra annotations (labelled_text entries) to inject, plus label defs.
    annotations: list[dict] = field(default_factory=list)
    annotation_labels: dict[str, dict] = field(default_factory=dict)
    # Annotation-to-annotation relationships referencing injected/parser ids.
    relationships: list[dict] = field(default_factory=list)
    # Typed corpus metadata (Column/Datacell — the UI's document metadata). Each
    # entry: {column_name, data_type, value, validation_config?}. Build with
    # metadata_field().
    metadata: list[dict] = field(default_factory=list)

    @classmethod
    def merge(cls, parts: Iterable[Enrichment | None]) -> Enrichment:
        """Combine several enrichers' outputs into one (last-writer-wins for
        scalar/dict fields; lists concatenated)."""
        out = cls()
        for p in parts:
            if p is None:
                continue
            if p.title is not None:
                out.title = p.title
            if p.description is not None:
                out.description = p.description
            out.custom_meta = {**out.custom_meta, **(p.custom_meta or {})}
            for name in p.doc_labels:
                if name not in out.doc_labels:
                    out.doc_labels.append(name)
            out.doc_label_defs.update(p.doc_label_defs or {})
            out.annotations.extend(p.annotations or [])
            out.annotation_labels.update(p.annotation_labels or {})
            out.relationships.extend(p.relationships or [])
            out.metadata.extend(p.metadata or [])
        return out

    def is_empty(self) -> bool:
        return not any(
            [
                self.title,
                self.description,
                self.custom_meta,
                self.doc_labels,
                self.annotations,
                self.relationships,
                self.metadata,
            ]
        )


class EnricherContext:
    """Read-only view of one parsed document, plus annotation-building helpers."""

    def __init__(self, *, rel_path: str, abs_path: str, export: dict, content: str):
        self.rel_path = rel_path
        self.abs_path = abs_path
        self.export = export
        self.content = content
        # Normalise PAWLs to the v1 (page dict) form once.
        self._pages = expand_pawls_pages(export.get("pawls_file_content") or [])
        self._page_index: dict[int, tuple[str, list[tuple[int, int, int]]]] = {}

    @property
    def pages(self) -> list[dict]:
        return self._pages

    @property
    def page_count(self) -> int:
        return self.export.get("page_count") or len(self._pages)

    def _page_token_index(self, page: int) -> tuple[str, list[tuple[int, int, int]]]:
        """Return (joined_text, [(token_index, start_char, end_char), ...]) for a page.

        Tokens are space-joined; the char spans let a regex match map back to the
        exact token indices it covers."""
        if page in self._page_index:
            return self._page_index[page]
        joined = ""
        spans: list[tuple[int, int, int]] = []
        if 0 <= page < len(self._pages):
            for idx, tok in enumerate(self._pages[page].get("tokens", [])):
                text = tok.get("text") or ""
                if tok.get("is_image"):
                    # image tokens have no text; keep index alignment with a gap
                    if joined:
                        joined += " "
                    spans.append((idx, len(joined), len(joined)))
                    continue
                if joined:
                    joined += " "
                start = len(joined)
                joined += text
                spans.append((idx, start, len(joined)))
        self._page_index[page] = (joined, spans)
        return self._page_index[page]

    def page_text(self, page: int) -> str:
        """The space-joined token text of a page (what find_token_matches searches)."""
        return self._page_token_index(page)[0]

    def find_token_matches(
        self,
        pattern: str | Pattern,
        *,
        flags: int = re.IGNORECASE,
        pages: Iterable[int] | None = None,
    ) -> list[TokenMatch]:
        """Find regex matches over each page's token text and map them back to
        token indices. Returns one TokenMatch per match."""
        rx = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
        page_iter = list(pages) if pages is not None else range(len(self._pages))
        out: list[TokenMatch] = []
        for page in page_iter:
            joined, spans = self._page_token_index(page)
            if not joined:
                continue
            for m in rx.finditer(joined):
                s, e = m.start(), m.end()
                if s == e:
                    continue
                idxs = [i for (i, ts, te) in spans if ts < e and te > s and te > ts]
                if idxs:
                    out.append(
                        TokenMatch(page=page, token_indices=idxs, text=m.group(0))
                    )
        return out

    def token_annotation(
        self,
        label: str,
        match: TokenMatch,
        *,
        raw_text: str | None = None,
        content_modalities: list[str] | None = None,
        data: dict | None = None,
        link_url: str | None = None,
    ) -> dict:
        """Build a faithful TOKEN_LABEL annotation (labelled_text entry) for a
        matched run of tokens. ``id`` is assigned later, at merge time."""
        page = match.page
        if not match.token_indices:
            raise ValueError("token_annotation requires at least one token index")
        tokens = (
            self._pages[page].get("tokens", []) if 0 <= page < len(self._pages) else []
        )
        lefts, tops, rights, bottoms = [], [], [], []
        for idx in match.token_indices:
            tok = tokens[idx]
            x, y = float(tok["x"]), float(tok["y"])
            w, h = float(tok["width"]), float(tok["height"])
            lefts.append(x)
            tops.append(y)
            rights.append(x + w)
            bottoms.append(y + h)
        bounds = {
            "left": min(lefts),
            "top": min(tops),
            "right": max(rights),
            "bottom": max(bottoms),
        }
        rtext = raw_text if raw_text is not None else match.text
        annotation: dict = {
            "annotationLabel": label,
            "rawText": rtext,
            "page": page,
            "annotation_type": TOKEN_LABEL,
            "structural": False,
            "content_modalities": content_modalities or ["TEXT"],
            "annotation_json": {
                str(page): {
                    "bounds": bounds,
                    "tokensJsons": [
                        {"pageIndex": page, "tokenIndex": idx}
                        for idx in match.token_indices
                    ],
                    "rawText": rtext,
                }
            },
        }
        if data is not None:
            annotation["data"] = data
        if link_url is not None:
            annotation["link_url"] = link_url
        return annotation


Enricher = Callable[[EnricherContext], Optional[Enrichment]]


# ---------------------------------------------------------------------------
# Label-definition helper
# ---------------------------------------------------------------------------


def label_def(
    text: str,
    label_type: str = TOKEN_LABEL,
    *,
    color: str = "#2563EB",
    description: str = "Worker enrichment label",
    icon: str = "tag",
) -> dict:
    """Build an AnnotationLabel definition dict (validated by the server's
    AnnotationLabelSerializer when auto-created)."""
    return {
        "label_type": label_type,
        "color": color,
        "description": description,
        "icon": icon,
        "text": text,
    }


# ---------------------------------------------------------------------------
# Typed corpus-metadata (Column/Datacell) helper
# ---------------------------------------------------------------------------

# The 12 metadata column data types (mirror MetadataService.METADATA_DATA_TYPES).
METADATA_DATA_TYPES = (
    "STRING",
    "TEXT",
    "BOOLEAN",
    "INTEGER",
    "FLOAT",
    "DATE",
    "DATETIME",
    "URL",
    "EMAIL",
    "CHOICE",
    "MULTI_CHOICE",
    "JSON",
)


def _infer_data_type(value) -> str:
    """Best-effort data_type for a Python value (bool before int!)."""
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "FLOAT"
    if isinstance(value, (dict, list)):
        return "JSON"
    return "STRING"


def metadata_field(
    column_name: str,
    value,
    *,
    data_type: str | None = None,
    validation_config: dict | None = None,
) -> dict:
    """Build one typed metadata entry (a Column/Datacell value) to set on the
    document. ``data_type`` is inferred from ``value`` when omitted. The value is
    type-checked against ``data_type`` server-side (and by validate_enrichment).
    """
    dt = data_type or _infer_data_type(value)
    entry: dict = {"column_name": column_name, "data_type": dt, "value": value}
    if validation_config is not None:
        entry["validation_config"] = validation_config
    return entry


def _metadata_value_error(entry: dict) -> str | None:
    """Return an error string if a metadata entry's value does not match its
    declared data_type (mirrors the server's Datacell.clean rules), else None."""
    dt = entry.get("data_type")
    value = entry.get("value")
    cfg = entry.get("validation_config") or {}
    if value is None:
        return None  # null is allowed unless the column marks it required
    if dt == "BOOLEAN" and not isinstance(value, bool):
        return "must be a boolean"
    if dt == "INTEGER" and (not isinstance(value, int) or isinstance(value, bool)):
        return "must be an integer"
    if dt == "FLOAT" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        return "must be a number"
    if dt in ("STRING", "TEXT", "URL", "EMAIL") and not isinstance(value, str):
        return "must be a string"
    if dt in ("DATE", "DATETIME") and not isinstance(value, str):
        return f"must be a {dt.lower()} string"
    if dt == "CHOICE" and value not in (cfg.get("choices") or []):
        return "must be one of the configured choices"
    if dt == "MULTI_CHOICE":
        if not isinstance(value, list):
            return "must be a list"
        bad = [v for v in value if v not in (cfg.get("choices") or [])]
        if bad:
            return "values must be from the configured choices"
    if dt == "JSON" and not isinstance(value, (dict, list)):
        return "must be a JSON object or array"
    return None


# ---------------------------------------------------------------------------
# Loading + running enrichers
# ---------------------------------------------------------------------------


def load_enrichers(specs: Iterable[str]) -> list[tuple[str, Enricher]]:
    """Resolve ``module.path:callable`` specs into callables. Raises a clear
    error if a spec is malformed or the attribute is not callable."""
    loaded: list[tuple[str, Enricher]] = []
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        if ":" not in spec:
            raise ValueError(
                f"Invalid enricher spec {spec!r}; expected 'module.path:callable'."
            )
        module_path, _, attr = spec.partition(":")
        module = importlib.import_module(module_path)
        fn = getattr(module, attr, None)
        if not callable(fn):
            raise ValueError(f"Enricher {spec!r} is not callable.")
        loaded.append((spec, fn))
    return loaded


def run_enrichers(
    enrichers: list[tuple[str, Enricher]], ctx: EnricherContext
) -> Enrichment:
    """Run every enricher over the context and merge their results."""
    parts: list[Enrichment | None] = []
    for name, fn in enrichers:
        result = fn(ctx)
        if result is not None and not isinstance(result, Enrichment):
            raise TypeError(
                f"Enricher {name!r} returned {type(result).__name__}, expected Enrichment."
            )
        parts.append(result)
    return Enrichment.merge(parts)


# ---------------------------------------------------------------------------
# Applying enrichment to the parsed export + building the metadata overlay
# ---------------------------------------------------------------------------


@dataclass
class MetadataOverlay:
    """Document-level enrichment to fold into the worker-upload metadata."""

    title: str | None = None
    description: str | None = None
    custom_meta: dict = field(default_factory=dict)
    text_label_defs: dict[str, dict] = field(default_factory=dict)
    doc_label_defs: dict[str, dict] = field(default_factory=dict)
    doc_labels: list[str] = field(default_factory=list)
    metadata: list[dict] = field(default_factory=list)


def apply_enrichment(
    export: dict, enrichment: Enrichment, *, id_prefix: str = "enr"
) -> MetadataOverlay:
    """Merge ``enrichment`` into ``export`` (in place) and return the
    document-level overlay for the metadata payload.

    Injected annotations get unique, collision-free ids (``enr-0``, ...). Their
    labels + relationships are merged into the export. Embeddings are computed
    downstream over ``export['labelled_text']`` so injected annotations are
    embedded too.
    """
    labelled = export.setdefault("labelled_text", [])
    existing_ids = {a.get("id") for a in labelled if a.get("id") is not None}

    n = 0
    for ann in enrichment.annotations:
        if not ann.get("id"):
            new_id = f"{id_prefix}-{n}"
            while new_id in existing_ids:
                n += 1
                new_id = f"{id_prefix}-{n}"
            ann["id"] = new_id
            n += 1
        existing_ids.add(ann["id"])
        labelled.append(ann)

    if enrichment.relationships:
        export.setdefault("relationships", []).extend(enrichment.relationships)

    if enrichment.doc_labels:
        doc_labels = export.setdefault("doc_labels", [])
        for name in enrichment.doc_labels:
            if name not in doc_labels:
                doc_labels.append(name)

    return MetadataOverlay(
        title=enrichment.title,
        description=enrichment.description,
        custom_meta=dict(enrichment.custom_meta),
        text_label_defs=dict(enrichment.annotation_labels),
        doc_label_defs=dict(enrichment.doc_label_defs),
        doc_labels=list(enrichment.doc_labels),
        metadata=list(enrichment.metadata),
    )


def validate_enrichment(export: dict, enrichment: Enrichment) -> list[str]:
    """Return a list of human-readable problems with the enrichment. Empty list
    means it is safe to upload. Catches the worker-upload correctness rules so a
    buggy enricher fails the document instead of shipping a broken annotation."""
    errors: list[str] = []
    pages = expand_pawls_pages(export.get("pawls_file_content") or [])
    page_token_counts = [len(p.get("tokens", [])) for p in pages]

    # Labels referenced by injected annotations must be defined (so the server
    # auto-creates them) or already present on a parser annotation.
    parser_labels = {
        a.get("annotationLabel")
        for a in export.get("labelled_text", [])
        if a.get("annotationLabel")
    }
    defined = set(enrichment.annotation_labels.keys()) | parser_labels

    # Injected annotation ids must be unique and must not collide with the
    # parser's ids: import_annotations keys its old_id->new_pk map by id, so a
    # collision silently maps two annotations to one row (and drops one
    # embedding). Auto-assigned ids are collision-safe by construction; this
    # guards explicit ids an enricher set by hand.
    parser_ids = {a.get("id") for a in export.get("labelled_text", []) if a.get("id")}
    seen_injected: set = set()

    for i, ann in enumerate(enrichment.annotations):
        where = f"annotation[{i}]"
        aid = ann.get("id")
        if aid is not None:
            if aid in parser_ids:
                errors.append(
                    f"{where}: id {aid!r} collides with a parser annotation id"
                )
            if aid in seen_injected:
                errors.append(f"{where}: duplicate injected annotation id {aid!r}")
            seen_injected.add(aid)
        label = ann.get("annotationLabel")
        if not label:
            errors.append(f"{where}: missing annotationLabel")
        elif label not in defined:
            errors.append(
                f"{where}: label {label!r} has no definition "
                f"(add it to Enrichment.annotation_labels)"
            )
        if not (ann.get("rawText") or "").strip():
            errors.append(f"{where}: rawText is empty")
        if (ann.get("annotation_type") or "") == DOC_TYPE_LABEL:
            errors.append(
                f"{where}: a DOC_TYPE_LABEL belongs in Enrichment.doc_labels, "
                f"not in annotations"
            )
        if ann.get("structural"):
            # Structural annotations are the parser's (they get migrated into the
            # StructuralAnnotationSet server-side). Enricher annotations are
            # content annotations and must stay non-structural.
            errors.append(
                f"{where}: injected annotations must be non-structural "
                f"(structural=True is parser-owned)"
            )

        aj = ann.get("annotation_json")
        atype = ann.get("annotation_type") or TOKEN_LABEL
        if atype == SPAN_LABEL:
            # text-doc span shape: {"start": int, "end": int, "text": str}
            if not isinstance(aj, dict) or "start" not in aj or "end" not in aj:
                errors.append(f"{where}: SPAN_LABEL annotation_json needs start/end")
            continue
        # TOKEN_LABEL page-keyed shape
        if not isinstance(aj, dict) or not aj:
            errors.append(
                f"{where}: TOKEN_LABEL annotation_json must be a NON-EMPTY "
                f"page-keyed dict (e.g. via ctx.token_annotation())"
            )
            continue
        for page_key, page_data in aj.items():
            try:
                page_idx = int(page_key)
            except (TypeError, ValueError):
                errors.append(f"{where}: page key {page_key!r} is not an int string")
                continue
            if page_idx < 0 or page_idx >= len(pages):
                errors.append(
                    f"{where}: page {page_idx} out of range (0..{len(pages)-1})"
                )
                continue
            bounds = (page_data or {}).get("bounds") or {}
            if not all(k in bounds for k in ("top", "bottom", "left", "right")):
                errors.append(f"{where}: bounds must have top/bottom/left/right")
            for tj in (page_data or {}).get("tokensJsons", []):
                if tj.get("pageIndex") != page_idx:
                    errors.append(
                        f"{where}: tokensJsons.pageIndex {tj.get('pageIndex')} != page {page_idx}"
                    )
                ti = tj.get("tokenIndex")
                if (
                    not isinstance(ti, int)
                    or ti < 0
                    or ti >= page_token_counts[page_idx]
                ):
                    errors.append(
                        f"{where}: tokenIndex {ti} out of range on page {page_idx} "
                        f"(0..{page_token_counts[page_idx]-1})"
                    )

    # doc_labels must be defined (server auto-creates from doc_labels_definitions).
    for name in enrichment.doc_labels:
        if name not in enrichment.doc_label_defs:
            errors.append(
                f"doc_label {name!r} has no definition (add it to Enrichment.doc_label_defs)"
            )

    # relationships must reference resolvable annotation ids + a defined label.
    # Resolve against BOTH the parser annotations already on the export AND the
    # enrichment's own injected annotations' explicit ids — validate_enrichment
    # runs BEFORE apply_enrichment merges/ids them, so a relationship that
    # references an injected annotation (by the explicit id its author set) must
    # still resolve here. (Auto-assigned ids can't be referenced anyway — the
    # author doesn't know them — so only explicit ids matter.)
    all_ids = {a.get("id") for a in export.get("labelled_text", []) if a.get("id")}
    all_ids |= {a.get("id") for a in enrichment.annotations if a.get("id")}

    # An injected annotation's parent_id must resolve to a real annotation id
    # (parser or injected) — import_annotations silently skips an unresolvable
    # parent_id, so catch it here instead of losing the hierarchy quietly.
    for i, ann in enumerate(enrichment.annotations):
        pid = ann.get("parent_id")
        if pid is not None and pid not in all_ids:
            errors.append(
                f"annotation[{i}]: parent_id {pid!r} does not resolve to any "
                f"annotation id"
            )

    rel_label_defs = {
        n
        for n, d in enrichment.annotation_labels.items()
        if d.get("label_type") == RELATIONSHIP_LABEL
    }
    for i, rel in enumerate(enrichment.relationships):
        where = f"relationship[{i}]"
        srcs = rel.get("source_annotation_ids") or []
        tgts = rel.get("target_annotation_ids") or []
        if not srcs or not tgts:
            errors.append(
                f"{where}: needs non-empty source_annotation_ids + target_annotation_ids"
            )
        for rid in list(srcs) + list(tgts):
            if rid not in all_ids:
                errors.append(f"{where}: references unknown annotation id {rid!r}")
        rlabel = rel.get("relationshipLabel")
        if rlabel and rlabel not in (rel_label_defs | _parser_rel_labels(export)):
            errors.append(
                f"{where}: relationshipLabel {rlabel!r} has no RELATIONSHIP_LABEL definition"
            )

    # Typed corpus metadata: each entry needs a column_name + a valid data_type,
    # and its value must match the data_type (server-side Datacell.clean enforces
    # the same — catch it here so the document isn't failed mid-ingest).
    for i, md in enumerate(enrichment.metadata):
        where = f"metadata[{i}]"
        if not md.get("column_name") or not isinstance(md.get("column_name"), str):
            errors.append(f"{where}: column_name is required (string)")
        if md.get("data_type") not in METADATA_DATA_TYPES:
            errors.append(
                f"{where}: data_type {md.get('data_type')!r} must be one of "
                f"{', '.join(METADATA_DATA_TYPES)}"
            )
            continue
        verr = _metadata_value_error(md)
        if verr:
            errors.append(f"{where} ({md.get('column_name')}): value {verr}")
    return errors


def _parser_rel_labels(export: dict) -> set:
    return {
        r.get("relationshipLabel")
        for r in export.get("relationships", [])
        if r.get("relationshipLabel")
    }
