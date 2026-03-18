"""
Standalone validation utility for OpenContracts corpus export ZIPs.

Checks structural and referential integrity of a corpus export archive
*without* requiring Django or a running database. Can be used as a library
or run directly from the command line::

    python -m opencontractserver.utils.validate_export corpus_export.zip

Exit code 0 means the export is valid; non-zero means errors were found.
All warnings and errors are printed to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from dataclasses import dataclass, field

from opencontractserver.annotations.compact_json import (
    is_compact_format,
    is_span_format,
    iter_page_annotations,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_LABEL_TYPES = {
    "DOC_TYPE_LABEL",
    "TOKEN_LABEL",
    "RELATIONSHIP_LABEL",
    "SPAN_LABEL",
}

VALID_ANNOTATION_TYPES = {"TOKEN_LABEL", "SPAN_LABEL"}

VALID_TEXT_LABEL_TYPES = {"TOKEN_LABEL", "SPAN_LABEL", "RELATIONSHIP_LABEL"}

VALID_CONTENT_MODALITIES = {"TEXT", "IMAGE", "AUDIO", "TABLE", "VIDEO"}

KNOWN_VERSIONS = {"1.0", "2.0"}

# Maximum data.json size to load into memory (500 MB).
# Note: intentionally duplicates ZIP_MAX_TOTAL_SIZE_BYTES from
# opencontractserver/constants/zip_import.py — that module has a Django
# dependency and cannot be imported in a standalone context.
MAX_DATA_JSON_SIZE = 500 * 1024 * 1024

V2_REQUIRED_FIELDS = {
    "structural_annotation_sets",
    "folders",
    "document_paths",
    "relationships",
    "agent_config",
    "md_description",
    "md_description_revisions",
    "post_processors",
}

__all__ = ["validate_export", "validate_data_json", "ValidationResult", "main"]


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Accumulated errors and warnings from validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def summary(self) -> str:
        lines = []
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN: {w}")

        if self.ok:
            lines.append(f"  VALID ({len(self.warnings)} warning(s))")
        else:
            lines.append(
                f"  INVALID — {len(self.errors)} error(s), "
                f"{len(self.warnings)} warning(s)"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------


def _check_zip_structure(
    zip_file: zipfile.ZipFile, data: dict, result: ValidationResult
) -> None:
    """Verify every annotated_docs key has a matching file in the ZIP."""
    zip_names = set(zip_file.namelist())

    annotated_docs = data.get("annotated_docs", {})
    for filename in annotated_docs:
        if filename not in zip_names:
            result.error(
                f"annotated_docs references '{filename}' but it is not in the ZIP"
            )

    # Warn about extra files that aren't referenced (skip directory entries)
    known_files = set(annotated_docs.keys()) | {"data.json"}
    for name in zip_names:
        if name not in known_files and not name.endswith("/"):
            result.warn(f"ZIP contains unreferenced file: '{name}'")


def _check_label_definitions(data: dict, result: ValidationResult) -> None:
    """Validate label definitions have required fields and consistent types."""
    required_fields = {"id", "text", "label_type", "color", "description", "icon"}

    for section, allowed_types in [
        ("doc_labels", {"DOC_TYPE_LABEL"}),
        ("text_labels", VALID_TEXT_LABEL_TYPES),
    ]:
        labels = data.get(section, {})
        for name, label in labels.items():
            for f in required_fields:
                if f not in label:
                    result.error(f"{section}.{name}: missing required field '{f}'")

            lt = label.get("label_type", "")
            if lt not in VALID_LABEL_TYPES:
                result.error(
                    f"{section}.{name}: invalid label_type '{lt}' "
                    f"(must be one of {VALID_LABEL_TYPES})"
                )
            elif lt not in allowed_types:
                result.error(
                    f"{section}.{name}: label_type '{lt}' not allowed in "
                    f"{section} (must be one of {sorted(allowed_types)})"
                )

            if label.get("text") != name:
                result.warn(
                    f"{section}.{name}: label 'text' field ('{label.get('text')}') "
                    f"does not match map key ('{name}')"
                )


def _check_corpus_metadata(data: dict, result: ValidationResult) -> None:
    """Validate corpus metadata."""
    corpus = data.get("corpus")
    if corpus is None:
        result.error("Missing 'corpus' field")
        return

    for f in ("title", "description", "creator"):
        if f not in corpus:
            result.error(f"corpus: missing required field '{f}'")


def _check_label_set_metadata(data: dict, result: ValidationResult) -> None:
    """Validate label_set metadata."""
    label_set = data.get("label_set")
    if label_set is None:
        result.error("Missing 'label_set' field")
        return

    for f in ("title", "description", "creator", "icon_name"):
        if f not in label_set:
            result.error(f"label_set: missing required field '{f}'")


def _check_documents(data: dict, result: ValidationResult) -> set[str]:
    """
    Validate each document in annotated_docs.

    Returns the set of all annotation IDs across all documents for
    relationship validation.
    """
    all_annotation_ids: set[str] = set()
    doc_labels_map = data.get("doc_labels", {})
    text_labels_map = data.get("text_labels", {})

    annotated_docs = data.get("annotated_docs", {})
    for filename, doc in annotated_docs.items():
        prefix = f"annotated_docs['{filename}']"

        # Required fields
        for f in (
            "title",
            "content",
            "description",
            "pawls_file_content",
            "page_count",
        ):
            if f not in doc:
                result.error(f"{prefix}: missing required field '{f}'")

        # Validate page count vs PAWLs length
        pawls = doc.get("pawls_file_content", [])
        page_count = doc.get("page_count", 0)
        if len(pawls) != page_count:
            result.warn(
                f"{prefix}: page_count ({page_count}) != "
                f"pawls_file_content length ({len(pawls)})"
            )

        # Validate PAWLs pages
        _check_pawls_pages(pawls, prefix, result)

        # Validate doc_labels references
        for dl in doc.get("doc_labels", []):
            if dl not in doc_labels_map:
                result.error(
                    f"{prefix}: doc_labels references '{dl}' which is not "
                    f"defined in top-level doc_labels"
                )

        # Validate annotations (single pass, defer parent_id checks)
        local_annot_ids: set[str] = set()
        deferred_parent_checks: list[tuple[str | None, str | None]] = []
        if "labelled_text" not in doc:
            result.error(f"{prefix}: missing required field 'labelled_text'")
        for annot in doc.get("labelled_text", []):
            raw_id = annot.get("id")
            annot_id = str(raw_id) if raw_id is not None else ""
            if annot_id:
                local_annot_ids.add(annot_id)
                all_annotation_ids.add(annot_id)

            label_name = annot.get("annotationLabel", "")
            if label_name not in text_labels_map:
                result.error(
                    f"{prefix}: annotation {annot_id} references label "
                    f"'{label_name}' not in text_labels"
                )

            parent_id = annot.get("parent_id")
            if parent_id is not None:
                deferred_parent_checks.append((annot.get("id"), parent_id))

            _check_annotation(annot, pawls, prefix, result)

        # Validate parent references (deferred until local_annot_ids is complete)
        for annot_id_raw, parent_id in deferred_parent_checks:
            if str(parent_id) not in local_annot_ids:
                result.warn(
                    f"{prefix}: annotation {annot_id_raw} references "
                    f"parent_id '{parent_id}' not found in this document"
                )

        # Validate document-level relationships
        for rel in doc.get("relationships", []):
            _check_relationship_label_type(
                rel, text_labels_map, f"{prefix}.relationships", result
            )
            _check_relationship_refs(
                rel, local_annot_ids, f"{prefix}.relationships", result
            )

        # Validate structural_set_hash reference
        struct_hash = doc.get("structural_set_hash")
        if struct_hash:
            struct_sets = data.get("structural_annotation_sets", {})
            if struct_hash not in struct_sets:
                result.error(
                    f"{prefix}: structural_set_hash '{struct_hash}' not found "
                    f"in structural_annotation_sets"
                )

    return all_annotation_ids


def _check_pawls_pages(pawls: list, prefix: str, result: ValidationResult) -> None:
    """Validate PAWLs page structure."""
    for i, page_obj in enumerate(pawls):
        page_prefix = f"{prefix}.pawls[{i}]"

        page = page_obj.get("page", {})
        if "width" not in page or "height" not in page or "index" not in page:
            result.error(f"{page_prefix}: page missing width/height/index")

        if page.get("index") != i:
            result.error(
                f"{page_prefix}: page.index ({page.get('index')}) != "
                f"array position ({i}) — pages must be sequential from 0"
            )

        tokens = page_obj.get("tokens")
        if tokens is None:
            result.error(f"{page_prefix}: missing 'tokens' array")
            continue

        for j, token in enumerate(tokens):
            for f in ("x", "y", "width", "height", "text"):
                if f not in token:
                    result.error(f"{page_prefix}.tokens[{j}]: missing '{f}'")

            # Validate token coordinates are non-negative
            for coord in ("x", "y", "width", "height"):
                val = token.get(coord)
                if val is not None and isinstance(val, (int, float)) and val < 0:
                    result.error(
                        f"{page_prefix}.tokens[{j}]: token {coord} is "
                        f"negative ({val})"
                    )


def _check_annotation(
    annot: dict, pawls: list, prefix: str, result: ValidationResult
) -> None:
    """Validate a single annotation's structure and token references."""
    annot_id = annot.get("id", "?")
    ann_prefix = f"{prefix}.annotation[{annot_id}]"

    # Required fields
    for f in ("annotationLabel", "rawText", "page", "annotation_json"):
        if f not in annot:
            result.error(f"{ann_prefix}: missing required field '{f}'")

    if "structural" not in annot:
        result.warn(f"{ann_prefix}: missing 'structural' field (defaults to false)")

    # Validate annotation_type
    ann_type = annot.get("annotation_type")
    if ann_type and ann_type not in VALID_ANNOTATION_TYPES:
        result.warn(
            f"{ann_prefix}: unexpected annotation_type '{ann_type}' "
            f"(expected one of {VALID_ANNOTATION_TYPES})"
        )

    # Validate content_modalities
    modalities = annot.get("content_modalities", [])
    for mod in modalities:
        if mod not in VALID_CONTENT_MODALITIES:
            result.error(
                f"{ann_prefix}: invalid content_modality '{mod}' "
                f"(must be one of {VALID_CONTENT_MODALITIES})"
            )

    # Validate annotation_json token references and bounds.
    # Use `or {}` instead of a default so that explicit null (common in
    # exports) is normalised to an empty dict rather than silently skipping.
    # The accessor layer handles both v1 and v2 formats transparently.
    ann_json = annot.get("annotation_json") or {}

    # Span annotations ({start, end}) don't have page-keyed structure
    if isinstance(ann_json, dict) and not is_span_format(ann_json):
        # Raw-format checks before the accessor layer (catches structural
        # issues the accessor silently normalises).
        if not is_compact_format(ann_json):
            # v1 format: validate page keys are integer strings
            for page_key, page_data in ann_json.items():
                if not isinstance(page_data, dict):
                    continue
                try:
                    pk_int = int(page_key)
                except (ValueError, TypeError):
                    result.error(
                        f"{ann_prefix}: non-integer page key '{page_key}' "
                        f"in annotation_json"
                    )
                    continue

                if pawls and (pk_int < 0 or pk_int >= len(pawls)):
                    result.error(
                        f"{ann_prefix}: annotation_json page key "
                        f"'{page_key}' out of range "
                        f"(document has {len(pawls)} page(s))"
                    )

                # Validate pageIndex consistency in tokensJsons
                for tok in page_data.get("tokensJsons", []):
                    if isinstance(tok, dict):
                        pi = tok.get("pageIndex")
                        if pi is not None and pi != pk_int:
                            result.error(
                                f"{ann_prefix}: tokensJsons pageIndex "
                                f"{pi} does not match page key '{page_key}'"
                            )
                        if pi is not None and pawls and (pi < 0 or pi >= len(pawls)):
                            result.error(
                                f"{ann_prefix}: tokensJsons pageIndex "
                                f"{pi} out of range "
                                f"(document has {len(pawls)} page(s))"
                            )

        for page in iter_page_annotations(ann_json, raw_text=annot.get("rawText", "")):
            # Validate page index is within document range
            if pawls and (page.page_index < 0 or page.page_index >= len(pawls)):
                result.error(
                    f"{ann_prefix}: annotation_json page index "
                    f"'{page.page_index}' out of range "
                    f"(document has {len(pawls)} page(s))"
                )

            # Validate bounds are non-negative
            for coord in ("top", "bottom", "left", "right"):
                val = page.bounds.get(coord)
                if val is not None and isinstance(val, (int, float)) and val < 0:
                    result.error(f"{ann_prefix}: bounds.{coord} is negative ({val})")

            if not pawls:
                if page.token_indices:
                    result.error(
                        f"{ann_prefix}: page {page.page_index} references "
                        f"tokens but empty PAWLs data"
                    )
                continue

            for token_idx in page.token_indices:
                if page.page_index < 0 or page.page_index >= len(pawls):
                    # Already reported above; skip token-level checks
                    continue

                page_tokens = pawls[page.page_index].get("tokens", [])
                if token_idx < 0 or token_idx >= len(page_tokens):
                    result.error(
                        f"{ann_prefix}: tokenIndex {token_idx} out of range "
                        f"for page {page.page_index} "
                        f"(0..{max(0, len(page_tokens) - 1)})"
                    )


def _check_relationship_label_type(
    rel: dict,
    text_labels_map: dict,
    prefix: str,
    result: ValidationResult,
) -> None:
    """Check that a relationship's label exists and has RELATIONSHIP_LABEL type."""
    rel_id = rel.get("id", "?")
    label = rel.get("relationshipLabel", "")
    if label and label not in text_labels_map:
        result.error(
            f"{prefix}[{rel_id}]: relationshipLabel '{label}' not in text_labels"
        )
    elif label:
        lt = text_labels_map[label].get("label_type", "")
        if lt != "RELATIONSHIP_LABEL":
            result.error(
                f"{prefix}[{rel_id}]: label '{label}' has type '{lt}', "
                f"expected 'RELATIONSHIP_LABEL'"
            )


def _check_relationship_refs(
    rel: dict,
    valid_ids: set[str],
    prefix: str,
    result: ValidationResult,
) -> None:
    """Check that relationship source/target IDs exist in the given set."""
    rel_id = rel.get("id", "?")
    label = rel.get("relationshipLabel")
    if not label:
        result.error(f"{prefix}[{rel_id}]: missing relationshipLabel")

    for direction in ("source_annotation_ids", "target_annotation_ids"):
        ids = rel.get(direction) or []
        if not ids:
            result.error(f"{prefix}[{rel_id}]: empty {direction}")
            continue
        for ref_id in ids:
            if str(ref_id) not in valid_ids:
                # Unresolvable annotation references will cause import failure
                # at the DB layer, so this is an error, not a warning.
                result.error(
                    f"{prefix}[{rel_id}]: {direction} references "
                    f"annotation '{ref_id}' not found in scope"
                )


def _check_structural_sets(data: dict, result: ValidationResult) -> set[str]:
    """Validate structural annotation sets and return all structural annotation IDs."""
    struct_sets = data.get("structural_annotation_sets", {})
    text_labels_map = data.get("text_labels", {})
    all_struct_annot_ids: set[str] = set()

    for content_hash, sset in struct_sets.items():
        prefix = f"structural_annotation_sets['{content_hash}']"

        if sset.get("content_hash") != content_hash:
            result.error(
                f"{prefix}: content_hash field ('{sset.get('content_hash')}') "
                f"does not match map key ('{content_hash}')"
            )

        # Required fields
        for f in (
            "pawls_file_content",
            "txt_content",
            "structural_annotations",
            "structural_relationships",
        ):
            if f not in sset:
                result.error(f"{prefix}: missing required field '{f}'")

        pawls = sset.get("pawls_file_content", [])
        _check_pawls_pages(pawls, prefix, result)

        # Validate structural annotations
        local_ids: set[str] = set()
        for annot in sset.get("structural_annotations", []):
            raw_id = annot.get("id")
            annot_id = str(raw_id) if raw_id is not None else ""
            if annot_id:
                if annot_id in local_ids:
                    result.error(
                        f"{prefix}: duplicate structural annotation id '{annot_id}'"
                    )
                local_ids.add(annot_id)
                all_struct_annot_ids.add(annot_id)

            label_name = annot.get("annotationLabel", "")
            if label_name and label_name not in text_labels_map:
                result.error(
                    f"{prefix}: structural annotation {annot_id} references "
                    f"label '{label_name}' not in text_labels"
                )

            if not annot.get("structural"):
                result.warn(
                    f"{prefix}: structural annotation {annot_id} has "
                    f"structural=false (expected true)"
                )

            _check_annotation(annot, pawls, prefix, result)

        # Validate structural relationships
        for rel in sset.get("structural_relationships", []):
            struct_rel_prefix = f"{prefix}.structural_relationships"
            _check_relationship_label_type(
                rel, text_labels_map, struct_rel_prefix, result
            )
            _check_relationship_refs(rel, local_ids, struct_rel_prefix, result)

    return all_struct_annot_ids


def _check_folders(data: dict, result: ValidationResult) -> set[str]:
    """Validate folder hierarchy and return the set of folder paths."""
    folders = data.get("folders", [])
    folder_ids: set[str] = set()
    folder_paths: set[str] = set()
    folder_by_id: dict[str, dict] = {}

    for folder in folders:
        fid = folder.get("id")
        if not fid:
            result.error("folders: entry missing 'id'")
            continue

        if fid in folder_ids:
            result.error(f"folders: duplicate id '{fid}'")
            continue

        folder_ids.add(fid)
        folder_by_id[fid] = folder

        for f in ("name", "path"):
            if f not in folder:
                result.error(f"folders['{fid}']: missing required field '{f}'")

        path = folder.get("path", "")
        if "/" in folder.get("name", ""):
            result.error(f"folders['{fid}']: name '{folder.get('name')}' contains '/'")

        folder_paths.add(path)

    # Validate parent references and path consistency
    for folder in folders:
        fid = folder.get("id", "?")
        parent_id = folder.get("parent_id")

        if parent_id is not None:
            if parent_id not in folder_ids:
                result.error(f"folders['{fid}']: parent_id '{parent_id}' not found")
            else:
                # Check path consistency
                parent_path = folder_by_id[parent_id].get("path", "")
                child_path = folder.get("path", "")
                expected_prefix = parent_path + "/"
                if not child_path.startswith(expected_prefix):
                    result.warn(
                        f"folders['{fid}']: path '{child_path}' is not a "
                        f"subpath of parent path '{parent_path}'"
                    )

    # Detect circular references using a global resolved set.
    # Once a node's full ancestor chain is verified acyclic, it's added to
    # `resolved` so subsequent walks skip it. Cycles are identified when
    # we revisit a node that is on the current walk stack (not yet resolved).
    resolved: set[str] = set()
    for folder in folders:
        start = folder.get("id")
        if not start or start in resolved:
            continue

        # Nodes visited in THIS walk, in order
        walk: list[str] = []
        walk_set: set[str] = set()
        current: str | None = start
        while current and current not in resolved:
            if current in walk_set:
                # Found a cycle — extract only the cycle members
                cycle_start = walk.index(current)
                cycle = walk[cycle_start:]
                result.error(
                    f"folders: circular parent reference involving " f"'{min(cycle)}'"
                )
                # Mark cycle members as resolved (cycle already reported)
                resolved.update(cycle)
                break
            walk.append(current)
            walk_set.add(current)
            current = folder_by_id.get(current, {}).get("parent_id")
        else:
            # No cycle found — all nodes in this walk are safe
            resolved.update(walk)

    return folder_paths


def _check_document_paths(
    data: dict, folder_paths: set[str], result: ValidationResult
) -> None:
    """Validate document_paths references."""
    doc_paths = data.get("document_paths", [])
    annotated_docs_keys = set(data.get("annotated_docs", {}).keys())

    for i, dp in enumerate(doc_paths):
        prefix = f"document_paths[{i}]"

        doc_ref = dp.get("document_ref")
        if not doc_ref:
            result.error(f"{prefix}: missing document_ref")
            continue

        # document_ref should match either a filename or could be a hash.
        # We can only validate filename matches; hashes are opaque.
        # Warn if it doesn't match any known filename (it might be a hash).
        if doc_ref not in annotated_docs_keys:
            result.warn(
                f"{prefix}: document_ref '{doc_ref}' does not match any "
                f"annotated_docs key (may be a file hash — OK if so)"
            )

        folder_path = dp.get("folder_path")
        if folder_path and folder_path not in folder_paths:
            result.error(
                f"{prefix}: folder_path '{folder_path}' does not match "
                f"any known folder path"
            )

        for f in ("path", "version_number", "is_current", "is_deleted", "created"):
            if f not in dp:
                result.error(f"{prefix}: missing required field '{f}'")


def _check_corpus_level_relationships(
    data: dict, all_annot_ids: set[str], result: ValidationResult
) -> None:
    """Validate top-level (corpus-scope) relationships."""
    relationships = data.get("relationships", [])
    text_labels_map = data.get("text_labels", {})

    for rel in relationships:
        prefix = "relationships"
        _check_relationship_label_type(rel, text_labels_map, prefix, result)
        _check_relationship_refs(rel, all_annot_ids, prefix, result)


def _check_conversations(data: dict, result: ValidationResult) -> None:
    """Validate conversations, messages, and votes cross-references."""
    conversations = data.get("conversations", [])
    messages = data.get("messages", [])
    votes = data.get("message_votes", [])

    # conv_ids may be empty if "conversations" key is absent; any conversation_id
    # reference in messages is then legitimately unresolvable (error, not warning).
    conv_ids: set[str] = set()
    for conv in conversations:
        cid = conv.get("id")
        if not cid:
            result.error("conversations: entry missing 'id'")
            continue
        if cid in conv_ids:
            result.error(f"conversations: duplicate id '{cid}'")
        conv_ids.add(cid)

    msg_ids: set[str] = set()
    for msg in messages:
        mid = msg.get("id")
        if not mid:
            result.error("messages: entry missing 'id'")
            continue
        if mid in msg_ids:
            result.error(f"messages: duplicate id '{mid}'")
        msg_ids.add(mid)

        conv_ref = msg.get("conversation_id")
        if conv_ref and conv_ref not in conv_ids:
            result.error(
                f"messages['{mid}']: conversation_id '{conv_ref}' "
                f"not found in conversations"
            )

    # Second pass for parent_message references
    for msg in messages:
        mid = msg.get("id", "?")
        parent = msg.get("parent_message_id")
        if parent and parent not in msg_ids:
            result.error(
                f"messages['{mid}']: parent_message_id '{parent}' "
                f"not found in messages"
            )

    for i, vote in enumerate(votes):
        msg_ref = vote.get("message_id")
        if msg_ref and msg_ref not in msg_ids:
            result.error(
                f"message_votes[{i}]: message_id '{msg_ref}' " f"not found in messages"
            )


def _check_agent_config(data: dict, result: ValidationResult) -> None:
    """Validate agent_config structure."""
    config = data.get("agent_config")
    if config is None:
        return  # Optional in V1

    if not isinstance(config, dict):
        result.error("agent_config: expected an object")
        return

    for f in ("corpus_agent_instructions", "document_agent_instructions"):
        if f not in config:
            result.warn(f"agent_config: missing field '{f}'")


def _check_action_trail(data: dict, result: ValidationResult) -> None:
    """Validate action_trail structure."""
    trail = data.get("action_trail")
    if trail is None:
        return  # Optional

    if not isinstance(trail, dict):
        result.error("action_trail: expected an object")
        return

    for f in ("actions", "executions", "stats"):
        if f not in trail:
            result.error(f"action_trail: missing required field '{f}'")

    stats = trail.get("stats", {})
    for f in ("total_executions", "completed", "failed", "exported_count"):
        if f not in stats:
            result.error(f"action_trail.stats: missing field '{f}'")


def _check_v2_required_fields(data: dict, result: ValidationResult) -> None:
    """Verify all V2-required top-level fields are present."""
    for f in V2_REQUIRED_FIELDS:
        if f not in data:
            result.error(f"V2 export missing required field '{f}'")


# ---------------------------------------------------------------------------
# Shared validation logic (used by both validate_export and validate_data_json)
# ---------------------------------------------------------------------------


def _validate_parsed_data(data: dict, result: ValidationResult) -> None:
    """Run all data-level validations (everything except ZIP structure)."""
    version = data.get("version", "1.0")
    is_v2 = version == "2.0"

    if version not in KNOWN_VERSIONS:
        result.warn(
            f"Unrecognised version '{version}'; treating as V1. "
            f"Known versions: {sorted(KNOWN_VERSIONS)}"
        )

    _check_label_definitions(data, result)
    _check_corpus_metadata(data, result)
    _check_label_set_metadata(data, result)
    all_annot_ids = _check_documents(data, result)

    if is_v2:
        _check_v2_required_fields(data, result)
        struct_annot_ids = _check_structural_sets(data, result)
        all_annot_ids |= struct_annot_ids
        folder_paths = _check_folders(data, result)
        _check_document_paths(data, folder_paths, result)
        _check_corpus_level_relationships(data, all_annot_ids, result)
        _check_agent_config(data, result)
        _check_action_trail(data, result)

        if any(k in data for k in ("conversations", "messages", "message_votes")):
            _check_conversations(data, result)
    else:
        # V1 may still have inline relationships in docs — already checked
        # in _check_documents. Check top-level if present.
        if data.get("relationships"):
            _check_corpus_level_relationships(data, all_annot_ids, result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_export(zip_path: str | os.PathLike[str]) -> ValidationResult:
    """
    Validate an OpenContracts corpus export ZIP file.

    Checks structural integrity, referential consistency, and format
    compliance without requiring Django or a running database.

    Args:
        zip_path: Path to the ZIP file.

    Returns:
        ValidationResult with all errors and warnings.
    """
    result = ValidationResult()

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if "data.json" not in zf.namelist():
                result.error("ZIP does not contain data.json")
                return result

            try:
                with zf.open("data.json") as f:
                    max_read = MAX_DATA_JSON_SIZE + 1
                    raw = f.read(max_read)
                    if len(raw) == max_read:
                        result.error(
                            f"data.json exceeds maximum size "
                            f"({MAX_DATA_JSON_SIZE} bytes)"
                        )
                        return result
                    data = json.loads(raw.decode("utf-8"))
            except UnicodeDecodeError as e:
                result.error(f"data.json is not valid UTF-8: {e}")
                return result
            except json.JSONDecodeError as e:
                result.error(f"data.json is not valid JSON: {e}")
                return result

            _check_zip_structure(zf, data, result)
            _validate_parsed_data(data, result)

    except zipfile.BadZipFile:
        result.error(f"Not a valid ZIP file: {zip_path}")
    except FileNotFoundError:
        result.error(f"File not found: {zip_path}")

    return result


def validate_data_json(data: dict) -> ValidationResult:
    """
    Validate an already-parsed data.json dict (no ZIP required).

    This is useful when building an export programmatically and you want to
    check the data structure before writing the ZIP. Note that ZIP-level
    checks (file presence) are skipped.

    Args:
        data: The parsed data.json dictionary.

    Returns:
        ValidationResult with all errors and warnings.
    """
    result = ValidationResult()
    _validate_parsed_data(data, result)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success, 1 on validation failure."""
    args = argv if argv is not None else sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(
            "Usage: python -m opencontractserver.utils.validate_export "
            "<export.zip> [export2.zip ...]\n\n"
            "Validates OpenContracts corpus export ZIP files.\n"
            "Exit code 0 = all valid, 1 = errors found.",
        )
        return 0

    any_errors = False

    for path in args:
        print(f"Validating: {path}", file=sys.stderr)
        result = validate_export(path)
        print(result.summary(), file=sys.stderr)
        if not result.ok:
            any_errors = True
        print(file=sys.stderr)

    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())
