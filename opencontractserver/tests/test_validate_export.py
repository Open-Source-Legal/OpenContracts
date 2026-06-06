"""
Tests for the standalone export validation utility.

These tests do NOT require Django — they exercise the pure-Python validator
against in-memory data.json structures.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile

from opencontractserver.utils.validate_export import (
    ValidationResult,
    main,
    validate_data_json,
    validate_dumb_anchor_sidecar,
    validate_export,
)

# ---------------------------------------------------------------------------
# Helpers to build minimal valid exports
# ---------------------------------------------------------------------------


def _minimal_v1_data() -> dict:
    """Return a minimal valid V1 data.json."""
    return {
        "annotated_docs": {
            "sample.pdf": {
                "title": "Sample",
                "content": "Hello world",
                "description": "A test document",
                "page_count": 1,
                "pawls_file_content": [
                    {
                        "page": {"width": 612.0, "height": 792.0, "index": 0},
                        "tokens": [
                            {
                                "x": 100,
                                "y": 100,
                                "width": 50,
                                "height": 12,
                                "text": "Hello",
                            },
                            {
                                "x": 160,
                                "y": 100,
                                "width": 50,
                                "height": 12,
                                "text": "world",
                            },
                        ],
                    }
                ],
                "doc_labels": ["Contract"],
                "labelled_text": [
                    {
                        "id": "annot_1",
                        "annotationLabel": "Clause",
                        "rawText": "Hello",
                        "page": 0,
                        "annotation_json": {
                            "0": {
                                "bounds": {
                                    "top": 100,
                                    "bottom": 112,
                                    "left": 100,
                                    "right": 150,
                                },
                                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                                "rawText": "Hello",
                            }
                        },
                        "parent_id": None,
                        "annotation_type": "TOKEN_LABEL",
                        "structural": False,
                    }
                ],
            }
        },
        "doc_labels": {
            "Contract": {
                "id": "1",
                "text": "Contract",
                "label_type": "DOC_TYPE_LABEL",
                "color": "#FF0000",
                "description": "A contract",
                "icon": "document",
            }
        },
        "text_labels": {
            "Clause": {
                "id": "2",
                "text": "Clause",
                "label_type": "TOKEN_LABEL",
                "color": "#0000FF",
                "description": "A clause",
                "icon": "tag",
            },
            "RelatesTo": {
                "id": "3",
                "text": "RelatesTo",
                "label_type": "RELATIONSHIP_LABEL",
                "color": "#00FF00",
                "description": "A relationship",
                "icon": "link",
            },
        },
        "corpus": {
            "id": 1,
            "title": "Test Corpus",
            "description": "Test",
            "icon_name": "icon.png",
            "icon_data": "",
            "creator": "test@example.com",
            "label_set": "1",
        },
        "label_set": {
            "id": "1",
            "title": "Test Labels",
            "description": "Test label set",
            "icon_name": "labels.png",
            "icon_data": "",
            "creator": "test@example.com",
        },
    }


def _minimal_v2_data() -> dict:
    """Return a minimal valid V2 data.json."""
    data = _minimal_v1_data()
    data["version"] = "2.0"
    data["structural_annotation_sets"] = {}
    data["folders"] = []
    data["document_paths"] = []
    data["relationships"] = []
    data["agent_config"] = {
        "corpus_agent_instructions": None,
        "document_agent_instructions": None,
    }
    data["md_description"] = None
    data["md_description_revisions"] = []
    data["post_processors"] = []
    return data


def _make_zip(data: dict, files: dict[str, bytes] | None = None) -> bytes:
    """
    Create an in-memory ZIP with data.json and optional extra files.

    Args:
        data: The data.json dict.
        files: Optional map of filename -> bytes to include in the ZIP.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data.json", json.dumps(data))
        if files:
            for name, content in files.items():
                zf.writestr(name, content)
    return buf.getvalue()


def _write_and_validate(
    data: dict, files: dict[str, bytes] | None = None
) -> ValidationResult:
    """Write a ZIP to a temp file, validate it, clean up, and return result."""
    zip_bytes = _make_zip(data, files)
    fd, path = tempfile.mkstemp(suffix=".zip")
    try:
        os.write(fd, zip_bytes)
        os.close(fd)
        return validate_export(path)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidationResult(unittest.TestCase):
    def test_empty_is_ok(self):
        r = ValidationResult()
        assert r.ok is True

    def test_warning_still_ok(self):
        r = ValidationResult()
        r.warn("something")
        assert r.ok is True

    def test_error_not_ok(self):
        r = ValidationResult()
        r.error("something")
        assert r.ok is False

    def test_summary(self):
        r = ValidationResult()
        r.warn("w1")
        r.error("e1")
        s = r.summary()
        assert "WARN" in s
        assert "ERROR" in s
        assert "INVALID" in s

    def test_summary_errors_before_warnings(self):
        r = ValidationResult()
        r.warn("w1")
        r.error("e1")
        s = r.summary()
        error_pos = s.index("ERROR")
        warn_pos = s.index("WARN")
        assert error_pos < warn_pos, "Errors should appear before warnings in summary"


class TestMinimalValidExport(unittest.TestCase):
    def test_v1_valid(self):
        data = _minimal_v1_data()
        result = _write_and_validate(data, {"sample.pdf": b"%PDF-fake"})
        assert result.ok, result.summary()

    def test_v2_valid(self):
        data = _minimal_v2_data()
        result = _write_and_validate(data, {"sample.pdf": b"%PDF-fake"})
        assert result.ok, result.summary()

    def test_validate_data_json_v1(self):
        data = _minimal_v1_data()
        result = validate_data_json(data)
        assert result.ok, result.summary()

    def test_validate_data_json_v2(self):
        data = _minimal_v2_data()
        result = validate_data_json(data)
        assert result.ok, result.summary()


class TestZipStructure(unittest.TestCase):
    def test_missing_file_in_zip(self):
        data = _minimal_v1_data()
        # Don't include sample.pdf in the ZIP
        result = _write_and_validate(data, {})
        assert not result.ok
        assert any("sample.pdf" in e for e in result.errors)

    def test_extra_file_warns(self):
        data = _minimal_v1_data()
        result = _write_and_validate(
            data, {"sample.pdf": b"pdf", "bonus.txt": b"extra"}
        )
        assert result.ok  # extra files are warnings, not errors
        assert any("unreferenced" in w for w in result.warnings)

    def test_directory_entries_not_flagged_as_unreferenced(self):
        """ZIP directory entries (e.g. 'documents/') should not warn."""
        data = _minimal_v1_data()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("data.json", json.dumps(data))
            zf.writestr("sample.pdf", b"pdf")
            zf.mkdir("documents")
        fd, path = tempfile.mkstemp(suffix=".zip")
        try:
            os.write(fd, buf.getvalue())
            os.close(fd)
            result = validate_export(path)
        finally:
            os.unlink(path)
        assert result.ok, result.summary()
        assert not any("documents/" in w for w in result.warnings)


class TestLabelValidation(unittest.TestCase):
    def test_missing_label_fields(self):
        data = _minimal_v1_data()
        del data["doc_labels"]["Contract"]["color"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("color" in e for e in result.errors)

    def test_wrong_label_type_in_doc_labels(self):
        data = _minimal_v1_data()
        data["doc_labels"]["Contract"]["label_type"] = "TOKEN_LABEL"
        result = validate_data_json(data)
        assert not result.ok
        assert any("DOC_TYPE_LABEL" in e for e in result.errors)

    def test_invalid_label_type(self):
        data = _minimal_v1_data()
        data["text_labels"]["Clause"]["label_type"] = "BOGUS"
        result = validate_data_json(data)
        assert not result.ok
        assert any("BOGUS" in e for e in result.errors)

    def test_doc_type_label_in_text_labels_is_error(self):
        """DOC_TYPE_LABEL is not allowed in text_labels."""
        data = _minimal_v1_data()
        data["text_labels"]["BadLabel"] = {
            "id": "99",
            "text": "BadLabel",
            "label_type": "DOC_TYPE_LABEL",
            "color": "#FF0000",
            "description": "Wrong type",
            "icon": "x",
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("DOC_TYPE_LABEL" in e and "text_labels" in e for e in result.errors)


class TestDocumentValidation(unittest.TestCase):
    def test_missing_required_doc_field(self):
        data = _minimal_v1_data()
        del data["annotated_docs"]["sample.pdf"]["title"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("title" in e for e in result.errors)

    def test_page_count_mismatch_warns(self):
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["page_count"] = 3
        result = validate_data_json(data)
        assert any("page_count" in w for w in result.warnings)

    def test_bad_doc_label_reference(self):
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["doc_labels"] = ["Nonexistent"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("Nonexistent" in e for e in result.errors)


class TestAnnotationValidation(unittest.TestCase):
    def test_null_annotation_id_not_treated_as_valid(self):
        """An annotation with id=None should not add 'None' to the ID set."""
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["labelled_text"].append(
            {
                "id": None,
                "annotationLabel": "Clause",
                "rawText": "world",
                "page": 0,
                "annotation_json": {},
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
                "structural": False,
            }
        )
        # Add a relationship referencing "None" — should be unresolvable
        data["annotated_docs"]["sample.pdf"]["relationships"] = [
            {
                "id": "r1",
                "relationshipLabel": "RelatesTo",
                "source_annotation_ids": ["None"],
                "target_annotation_ids": ["annot_1"],
                "structural": False,
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("None" in e and "not found" in e for e in result.errors)

    def test_bad_text_label_reference(self):
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["labelled_text"][0][
            "annotationLabel"
        ] = "NoSuchLabel"
        result = validate_data_json(data)
        assert not result.ok
        assert any("NoSuchLabel" in e for e in result.errors)

    def test_invalid_token_index(self):
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["annotation_json"]["0"]["tokensJsons"] = [
            {"pageIndex": 0, "tokenIndex": 999}
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("tokenIndex" in e for e in result.errors)

    def test_invalid_page_index(self):
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["annotation_json"]["0"]["tokensJsons"] = [
            {"pageIndex": 5, "tokenIndex": 0}
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("pageIndex" in e for e in result.errors)

    def test_invalid_content_modality(self):
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["content_modalities"] = ["BANANA"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("BANANA" in e for e in result.errors)

    def test_negative_bounds_error(self):
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["annotation_json"]["0"]["bounds"]["top"] = -10
        result = validate_data_json(data)
        assert not result.ok
        assert any("negative" in e for e in result.errors)

    def test_empty_pawls_page_index_error(self):
        """Annotation referencing into empty PAWLs gives clear error."""
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["pawls_file_content"] = []
        data["annotated_docs"]["sample.pdf"]["page_count"] = 0
        result = validate_data_json(data)
        assert not result.ok
        assert any("empty PAWLs" in e for e in result.errors)

    def test_missing_page_field_is_error(self):
        """The 'page' field is required on annotations per the spec."""
        data = _minimal_v1_data()
        del data["annotated_docs"]["sample.pdf"]["labelled_text"][0]["page"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("page" in e for e in result.errors)

    def test_non_integer_page_key_is_error(self):
        """annotation_json keys must be valid integers."""
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["annotation_json"] = {
            "abc": {
                "bounds": {"top": 0, "bottom": 10, "left": 0, "right": 10},
                "tokensJsons": [],
                "rawText": "Hello",
            }
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("non-integer page key" in e for e in result.errors)

    def test_page_key_out_of_range_is_error(self):
        """annotation_json page key must be within 0..page_count-1."""
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["annotation_json"] = {
            "999": {
                "bounds": {"top": 0, "bottom": 10, "left": 0, "right": 10},
                "tokensJsons": [],
                "rawText": "Hello",
            }
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("out of range" in e and "999" in e for e in result.errors)

    def test_annotation_json_null_not_silently_skipped(self):
        """Explicit null annotation_json should not silently skip validation."""
        data = _minimal_v1_data()
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        annot["annotation_json"] = None
        result = validate_data_json(data)
        # Should still be valid (null is normalised to empty dict, no tokens to check)
        # but the key point is it must NOT raise or silently skip
        assert result.ok, result.summary()

    def test_missing_labelled_text_is_error(self):
        """Missing labelled_text field should be an error, not a warning."""
        data = _minimal_v1_data()
        del data["annotated_docs"]["sample.pdf"]["labelled_text"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("labelled_text" in e for e in result.errors)

    def test_span_annotation_passes_validation(self):
        """Span annotations ({start, end}) should pass without page-keyed checks."""
        data = _minimal_v1_data()
        # Add a SPAN_LABEL to text_labels
        data["text_labels"]["SpanLabel"] = {
            "id": "4",
            "text": "SpanLabel",
            "label_type": "TOKEN_LABEL",
            "color": "#FF00FF",
            "description": "A span label",
            "icon": "tag",
        }
        data["annotated_docs"]["sample.pdf"]["labelled_text"].append(
            {
                "id": "annot_span_1",
                "annotationLabel": "SpanLabel",
                "rawText": "span text",
                "page": 0,
                "annotation_json": {"start": 0, "end": 9, "text": "span text"},
                "parent_id": None,
                "annotation_type": "SPAN_LABEL",
                "structural": False,
            }
        )
        result = validate_data_json(data)
        assert result.ok, result.summary()

    def test_page_index_mismatches_page_key(self):
        """pageIndex in tokensJsons must match the containing page key."""
        data = _minimal_v1_data()
        # Add a second page so pageIndex=1 is valid range-wise
        data["annotated_docs"]["sample.pdf"]["pawls_file_content"].append(
            {
                "page": {"width": 612.0, "height": 792.0, "index": 1},
                "tokens": [{"x": 0, "y": 0, "width": 10, "height": 10, "text": "foo"}],
            }
        )
        data["annotated_docs"]["sample.pdf"]["page_count"] = 2
        annot = data["annotated_docs"]["sample.pdf"]["labelled_text"][0]
        # annotation_json key is "0" but token ref has pageIndex 1
        annot["annotation_json"]["0"]["tokensJsons"] = [
            {"pageIndex": 1, "tokenIndex": 0}
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("does not match page key" in e for e in result.errors)


class TestPawlsValidation(unittest.TestCase):
    def test_nonsequential_page_index_is_error(self):
        data = _minimal_v1_data()
        # Set page.index to 5 instead of 0
        data["annotated_docs"]["sample.pdf"]["pawls_file_content"][0]["page"][
            "index"
        ] = 5
        result = validate_data_json(data)
        assert not result.ok
        assert any("sequential" in e for e in result.errors)

    def test_negative_token_coordinates_error(self):
        """Token x, y, width, height must be non-negative."""
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["pawls_file_content"][0]["tokens"][0][
            "x"
        ] = -5
        result = validate_data_json(data)
        assert not result.ok
        assert any("negative" in e and "token" in e.lower() for e in result.errors)


class TestStructuralSetValidation(unittest.TestCase):
    def test_missing_structural_set_reference(self):
        data = _minimal_v2_data()
        data["annotated_docs"]["sample.pdf"]["structural_set_hash"] = "missing_hash"
        result = validate_data_json(data)
        assert not result.ok
        assert any("missing_hash" in e for e in result.errors)

    def test_content_hash_mismatch(self):
        data = _minimal_v2_data()
        data["structural_annotation_sets"]["hash_a"] = {
            "content_hash": "hash_b",  # Mismatch
            "pawls_file_content": [],
            "txt_content": "",
            "structural_annotations": [],
            "structural_relationships": [],
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("does not match" in e for e in result.errors)

    def test_structural_relationship_wrong_label_type(self):
        """Structural relationship labels must have RELATIONSHIP_LABEL type."""
        data = _minimal_v2_data()
        data["structural_annotation_sets"]["hash_a"] = {
            "content_hash": "hash_a",
            "pawls_file_content": [
                {
                    "page": {"width": 612, "height": 792, "index": 0},
                    "tokens": [
                        {"x": 0, "y": 0, "width": 10, "height": 10, "text": "A"}
                    ],
                }
            ],
            "txt_content": "A",
            "structural_annotations": [
                {
                    "id": "sa1",
                    "annotationLabel": "Clause",
                    "rawText": "A",
                    "page": 0,
                    "annotation_json": {},
                    "structural": True,
                },
                {
                    "id": "sa2",
                    "annotationLabel": "Clause",
                    "rawText": "A",
                    "page": 0,
                    "annotation_json": {},
                    "structural": True,
                },
            ],
            "structural_relationships": [
                {
                    "id": "sr1",
                    # "Clause" is TOKEN_LABEL, not RELATIONSHIP_LABEL
                    "relationshipLabel": "Clause",
                    "source_annotation_ids": ["sa1"],
                    "target_annotation_ids": ["sa2"],
                    "structural": True,
                }
            ],
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("RELATIONSHIP_LABEL" in e for e in result.errors)


class TestFolderValidation(unittest.TestCase):
    def test_folder_missing_parent(self):
        data = _minimal_v2_data()
        data["folders"] = [
            {
                "id": "f1",
                "name": "Child",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": "nonexistent",
                "path": "Child",
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("nonexistent" in e for e in result.errors)

    def test_folder_name_with_slash(self):
        data = _minimal_v2_data()
        data["folders"] = [
            {
                "id": "f1",
                "name": "Bad/Name",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "Bad/Name",
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("/" in e for e in result.errors)

    def test_valid_folder_hierarchy(self):
        data = _minimal_v2_data()
        data["folders"] = [
            {
                "id": "f1",
                "name": "Parent",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "Parent",
            },
            {
                "id": "f2",
                "name": "Child",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": "f1",
                "path": "Parent/Child",
            },
        ]
        result = validate_data_json(data)
        assert result.ok, result.summary()

    def test_circular_reference_single_error(self):
        """A circular folder reference should produce exactly one error."""
        data = _minimal_v2_data()
        data["folders"] = [
            {
                "id": "a",
                "name": "A",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": "b",
                "path": "A",
            },
            {
                "id": "b",
                "name": "B",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": "a",
                "path": "B",
            },
        ]
        result = validate_data_json(data)
        cycle_errors = [e for e in result.errors if "circular" in e]
        assert len(cycle_errors) == 1

    def test_indirect_cycle_single_error(self):
        """A non-cycle node leading into a cycle should produce exactly one error."""
        data = _minimal_v2_data()
        # root -> f1 -> f2 -> f1 (cycle is f1<->f2, root just leads into it)
        data["folders"] = [
            {
                "id": "root",
                "name": "Root",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "Root",
            },
            {
                "id": "f1",
                "name": "F1",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": "f2",
                "path": "Root/F1",
            },
            {
                "id": "f2",
                "name": "F2",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": "f1",
                "path": "Root/F1/F2",
            },
        ]
        result = validate_data_json(data)
        cycle_errors = [e for e in result.errors if "circular" in e]
        assert (
            len(cycle_errors) == 1
        ), f"Expected exactly 1 circular error, got {len(cycle_errors)}: {cycle_errors}"


class TestDocumentPathValidation(unittest.TestCase):
    def test_bad_folder_path_reference(self):
        data = _minimal_v2_data()
        data["document_paths"] = [
            {
                "document_ref": "sample.pdf",
                "folder_path": "NoSuchFolder",
                "path": "/docs/sample.pdf",
                "version_number": 1,
                "parent_version_number": None,
                "is_current": True,
                "is_deleted": False,
                "created": "2025-01-01T00:00:00+00:00",
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("NoSuchFolder" in e for e in result.errors)


class TestRelationshipValidation(unittest.TestCase):
    def test_corpus_level_relationship_label_missing(self):
        data = _minimal_v2_data()
        data["relationships"] = [
            {
                "id": "r1",
                "relationshipLabel": "NoSuchRelation",
                "source_annotation_ids": ["annot_1"],
                "target_annotation_ids": ["annot_1"],
                "structural": False,
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("NoSuchRelation" in e for e in result.errors)

    def test_relationship_wrong_label_type(self):
        data = _minimal_v2_data()
        # Use a TOKEN_LABEL as a relationship label — should error
        data["relationships"] = [
            {
                "id": "r1",
                "relationshipLabel": "Clause",
                "source_annotation_ids": ["annot_1"],
                "target_annotation_ids": ["annot_1"],
                "structural": False,
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("RELATIONSHIP_LABEL" in e for e in result.errors)

    def test_unresolvable_annotation_ref_is_error(self):
        """Missing annotation ID in a relationship should be an error."""
        data = _minimal_v2_data()
        data["relationships"] = [
            {
                "id": "r1",
                "relationshipLabel": "RelatesTo",
                "source_annotation_ids": ["nonexistent_annot"],
                "target_annotation_ids": ["annot_1"],
                "structural": False,
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("nonexistent_annot" in e for e in result.errors)
        # Should NOT also produce a label-type error
        assert not any("RELATIONSHIP_LABEL" in e for e in result.errors)

    def test_doc_level_relationship_wrong_label_type(self):
        """Document-level relationship with wrong label type should error."""
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["labelled_text"].append(
            {
                "id": "annot_2",
                "annotationLabel": "Clause",
                "rawText": "world",
                "page": 0,
                "annotation_json": {},
                "parent_id": None,
                "annotation_type": "TOKEN_LABEL",
                "structural": False,
            }
        )
        data["annotated_docs"]["sample.pdf"]["relationships"] = [
            {
                "id": "r1",
                "relationshipLabel": "Clause",
                "source_annotation_ids": ["annot_1"],
                "target_annotation_ids": ["annot_2"],
                "structural": False,
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("RELATIONSHIP_LABEL" in e for e in result.errors)


class TestVersionValidation(unittest.TestCase):
    def test_unknown_version_warns(self):
        data = _minimal_v1_data()
        data["version"] = "banana"
        result = validate_data_json(data)
        # Should warn but still validate as V1
        assert any("banana" in w for w in result.warnings)

    def test_future_version_warns(self):
        # 3.0 is now a known version (canonical-CAML refactor); pick a
        # version that is genuinely beyond what the validator knows
        # about so this test continues to exercise the unknown-version
        # warning path.
        data = _minimal_v1_data()
        data["version"] = "9.0"
        result = validate_data_json(data)
        assert any("9.0" in w for w in result.warnings)


class TestV2RequiredFields(unittest.TestCase):
    def test_missing_v2_required_field(self):
        data = _minimal_v2_data()
        del data["folders"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("folders" in e for e in result.errors)

    def test_missing_multiple_v2_fields(self):
        data = _minimal_v2_data()
        del data["structural_annotation_sets"]
        del data["relationships"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("structural_annotation_sets" in e for e in result.errors)
        assert any("relationships" in e for e in result.errors)

    def test_missing_md_description_is_error(self):
        """md_description is required in V2 exports (value can be null)."""
        data = _minimal_v2_data()
        del data["md_description"]
        result = validate_data_json(data)
        assert not result.ok
        assert any("md_description" in e for e in result.errors)


class TestConversationValidation(unittest.TestCase):
    def test_message_bad_conversation_ref(self):
        data = _minimal_v2_data()
        data["conversations"] = [
            {
                "id": "c1",
                "title": "Chat",
                "conversation_type": "chat",
                "is_public": False,
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
                "modified": "2025-01-01T00:00:00+00:00",
                "chat_with_corpus": True,
            }
        ]
        data["messages"] = [
            {
                "id": "m1",
                "conversation_id": "nonexistent_conv",
                "content": "Hello",
                "msg_type": "HUMAN",
                "state": "completed",
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
            }
        ]
        data["message_votes"] = []
        result = validate_data_json(data)
        assert not result.ok
        assert any("nonexistent_conv" in e for e in result.errors)

    def test_valid_conversation(self):
        data = _minimal_v2_data()
        data["conversations"] = [
            {
                "id": "c1",
                "title": "Chat",
                "conversation_type": "chat",
                "is_public": False,
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
                "modified": "2025-01-01T00:00:00+00:00",
                "chat_with_corpus": True,
            }
        ]
        data["messages"] = [
            {
                "id": "m1",
                "conversation_id": "c1",
                "content": "Hello",
                "msg_type": "HUMAN",
                "state": "completed",
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
            }
        ]
        data["message_votes"] = [
            {
                "message_id": "m1",
                "vote_type": "upvote",
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
            }
        ]
        result = validate_data_json(data)
        assert result.ok, result.summary()

    def test_messages_validated_without_conversations_key(self):
        """Messages and votes should be validated even without a conversations key."""
        data = _minimal_v2_data()
        # No "conversations" key, but messages and votes are present
        data["messages"] = [
            {
                "id": "m1",
                "conversation_id": "orphan_conv",
                "content": "Hello",
                "msg_type": "HUMAN",
                "state": "completed",
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
            }
        ]
        data["message_votes"] = [
            {
                "message_id": "orphan_msg",
                "vote_type": "upvote",
                "creator_email": "test@example.com",
                "created": "2025-01-01T00:00:00+00:00",
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        # Should catch the orphan vote referencing a non-existent message
        assert any("orphan_msg" in e for e in result.errors)


class TestActionTrailValidation(unittest.TestCase):
    def test_non_dict_action_trail_is_error(self):
        data = _minimal_v2_data()
        data["action_trail"] = "not a dict"
        result = validate_data_json(data)
        assert not result.ok
        assert any("action_trail" in e and "object" in e for e in result.errors)

    def test_missing_stats_fields(self):
        data = _minimal_v2_data()
        data["action_trail"] = {
            "actions": [],
            "executions": [],
            "stats": {},  # Missing all required stats fields
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("total_executions" in e for e in result.errors)
        assert any("completed" in e for e in result.errors)
        assert any("failed" in e for e in result.errors)
        assert any("exported_count" in e for e in result.errors)

    def test_missing_action_trail_fields(self):
        data = _minimal_v2_data()
        data["action_trail"] = {}  # Missing actions, executions, stats
        result = validate_data_json(data)
        assert not result.ok
        assert any("actions" in e for e in result.errors)
        assert any("executions" in e for e in result.errors)
        assert any("stats" in e for e in result.errors)

    def test_valid_action_trail(self):
        data = _minimal_v2_data()
        data["action_trail"] = {
            "actions": [],
            "executions": [],
            "stats": {
                "total_executions": 0,
                "completed": 0,
                "failed": 0,
                "exported_count": 0,
            },
        }
        result = validate_data_json(data)
        assert result.ok, result.summary()


class TestAgentConfigValidation(unittest.TestCase):
    def test_non_dict_agent_config_is_error(self):
        data = _minimal_v2_data()
        data["agent_config"] = "not a dict"
        result = validate_data_json(data)
        assert not result.ok
        assert any("agent_config" in e and "object" in e for e in result.errors)

    def test_missing_agent_config_fields_warns(self):
        data = _minimal_v2_data()
        data["agent_config"] = {}  # Missing both instruction fields
        result = validate_data_json(data)
        assert any("corpus_agent_instructions" in w for w in result.warnings)
        assert any("document_agent_instructions" in w for w in result.warnings)


class TestCrashPaths(unittest.TestCase):
    def test_unicode_decode_error(self):
        """Non-UTF-8 data.json should produce a clear error, not crash."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # Write raw bytes that are invalid UTF-8
            zf.writestr("data.json", b"\xff\xfe" + b"\x00" * 20)

        fd, path = tempfile.mkstemp(suffix=".zip")
        try:
            os.write(fd, buf.getvalue())
            os.close(fd)
            result = validate_export(path)
        finally:
            os.unlink(path)
        assert not result.ok
        # Should be caught as either UTF-8 or JSON error, not crash
        assert any("UTF-8" in e or "JSON" in e for e in result.errors), result.summary()

    def test_none_annotation_ids_no_crash(self):
        """None-valued source/target_annotation_ids should not TypeError."""
        data = _minimal_v1_data()
        data["annotated_docs"]["sample.pdf"]["relationships"] = [
            {
                "id": "r1",
                "relationshipLabel": "RelatesTo",
                "source_annotation_ids": None,
                "target_annotation_ids": None,
            }
        ]
        result = validate_data_json(data)
        assert not result.ok
        assert any("empty" in e for e in result.errors)

    def test_duplicate_folder_id_no_overwrite(self):
        """Duplicate folder ID should error and not overwrite the first entry."""
        data = _minimal_v2_data()
        data["folders"] = [
            {
                "id": "f1",
                "name": "First",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "First",
            },
            {
                "id": "f1",
                "name": "Second",
                "description": "",
                "color": "#000",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "Second",
            },
        ]
        result = validate_data_json(data)
        assert any("duplicate" in e for e in result.errors)

    def test_duplicate_structural_annotation_id(self):
        """Duplicate structural annotation IDs should produce an error."""
        data = _minimal_v2_data()
        data["structural_annotation_sets"]["hash_a"] = {
            "content_hash": "hash_a",
            "pawls_file_content": [
                {
                    "page": {"width": 612, "height": 792, "index": 0},
                    "tokens": [
                        {"x": 0, "y": 0, "width": 10, "height": 10, "text": "A"}
                    ],
                }
            ],
            "txt_content": "A",
            "structural_annotations": [
                {
                    "id": "sa1",
                    "annotationLabel": "Clause",
                    "rawText": "A",
                    "page": 0,
                    "annotation_json": {},
                    "structural": True,
                },
                {
                    "id": "sa1",
                    "annotationLabel": "Clause",
                    "rawText": "A",
                    "page": 0,
                    "annotation_json": {},
                    "structural": True,
                },
            ],
            "structural_relationships": [],
        }
        result = validate_data_json(data)
        assert not result.ok
        assert any("duplicate structural annotation" in e for e in result.errors)


class TestBadZipInput(unittest.TestCase):
    def test_not_a_zip(self):
        fd, path = tempfile.mkstemp(suffix=".zip")
        try:
            os.write(fd, b"this is not a zip file")
            os.close(fd)
            result = validate_export(path)
        finally:
            os.unlink(path)
        assert not result.ok
        assert any("Not a valid ZIP" in e for e in result.errors)

    def test_missing_file(self):
        result = validate_export("/nonexistent/path.zip")
        assert not result.ok
        assert any("File not found" in e for e in result.errors)

    def test_zip_without_data_json(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("other.txt", "hello")

        fd, path = tempfile.mkstemp(suffix=".zip")
        try:
            os.write(fd, buf.getvalue())
            os.close(fd)
            result = validate_export(path)
        finally:
            os.unlink(path)
        assert not result.ok
        assert any("data.json" in e for e in result.errors)


class TestSizeGuard(unittest.TestCase):
    def test_oversized_data_json_rejected(self):
        """data.json exceeding MAX_DATA_JSON_SIZE should produce an error."""
        import opencontractserver.utils.validate_export as mod

        original = mod.MAX_DATA_JSON_SIZE
        try:
            # Set a tiny limit so we can trigger it with a small payload
            mod.MAX_DATA_JSON_SIZE = 10
            data = _minimal_v1_data()
            result = _write_and_validate(data, {"sample.pdf": b"%PDF-fake"})
            assert not result.ok
            assert any("exceeds maximum size" in e for e in result.errors)
        finally:
            mod.MAX_DATA_JSON_SIZE = original

    def test_just_under_limit_passes(self):
        """data.json at exactly the limit should not be rejected."""
        import opencontractserver.utils.validate_export as mod

        data = _minimal_v1_data()
        data_bytes = json.dumps(data).encode("utf-8")
        original = mod.MAX_DATA_JSON_SIZE
        try:
            # Set limit to exactly the size of the data
            mod.MAX_DATA_JSON_SIZE = len(data_bytes)
            result = _write_and_validate(data, {"sample.pdf": b"%PDF-fake"})
            assert result.ok, result.summary()
        finally:
            mod.MAX_DATA_JSON_SIZE = original


class TestCLI(unittest.TestCase):
    def test_help_returns_zero(self):
        assert main(["--help"]) == 0

    def test_no_args_returns_zero(self):
        assert main([]) == 0

    def test_valid_zip_returns_zero(self):
        data = _minimal_v1_data()
        zip_bytes = _make_zip(data, {"sample.pdf": b"%PDF-fake"})
        fd, path = tempfile.mkstemp(suffix=".zip")
        try:
            os.write(fd, zip_bytes)
            os.close(fd)
            assert main([path]) == 0
        finally:
            os.unlink(path)

    def test_invalid_zip_returns_one(self):
        data = _minimal_v1_data()
        # Missing sample.pdf in zip -> error
        zip_bytes = _make_zip(data, {})
        fd, path = tempfile.mkstemp(suffix=".zip")
        try:
            os.write(fd, zip_bytes)
            os.close(fd)
            assert main([path]) == 1
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_one(self):
        assert main(["/nonexistent/path.zip"]) == 1


# ---------------------------------------------------------------------------
# Dumb-anchor bulk-ZIP sidecar validation
# ---------------------------------------------------------------------------


def _labels_json(
    *,
    section_label_types: dict[str, str] | None = None,
) -> dict:
    """Build a minimal labels.json. ``section_label_types`` maps label text ->
    label_type; TOKEN_LABEL/RELATIONSHIP_LABEL go to text_labels, DOC_TYPE_LABEL
    to doc_labels."""
    types = section_label_types or {"OC_SECTION": "TOKEN_LABEL"}
    text_labels: dict = {}
    doc_labels: dict = {}
    for text, lt in types.items():
        entry = {"text": text, "label_type": lt}
        if lt == "DOC_TYPE_LABEL":
            doc_labels[text] = entry
        else:
            text_labels[text] = entry
    return {"text_labels": text_labels, "doc_labels": doc_labels}


class TestDumbAnchorSidecarValidation(unittest.TestCase):
    """Validation of the new bulk-ZIP dumb-anchor sidecar format."""

    def _pdf_ann(self, **overrides) -> dict:
        ann = {
            "id": "a1",
            "label": "OC_SECTION",
            "rawText": "CHAPTER 1",
            "page": 0,
            "bbox": {"left": 8.0, "top": 8.0, "right": 110.0, "bottom": 24.0},
            "parent_id": None,
        }
        ann.update(overrides)
        return ann

    def _span_ann(self, **overrides) -> dict:
        ann = {
            "id": "s1",
            "label": "OC_SECTION",
            "rawText": "CHAPTER 1",
            "start": 0,
            "end": 9,
            "parent_id": None,
        }
        ann.update(overrides)
        return ann

    def test_valid_pdf_sidecar(self):
        sidecar = {"annotations": [self._pdf_ann()]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertTrue(result.ok, msg=result.summary())

    def test_valid_span_sidecar_with_token_label(self):
        sidecar = {"annotations": [self._span_ann()]}
        result = validate_dumb_anchor_sidecar(
            sidecar, _labels_json(section_label_types={"OC_SECTION": "TOKEN_LABEL"})
        )
        self.assertTrue(result.ok, msg=result.summary())

    def test_annotations_must_be_list(self):
        result = validate_dumb_anchor_sidecar({"annotations": {}}, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(any("must be a JSON list" in e for e in result.errors))

    def test_missing_label_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(label="")]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(any("'label' must be a non-empty" in e for e in result.errors))

    def test_missing_raw_text_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(rawText="")]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("'rawText' must be a non-empty" in e for e in result.errors)
        )

    def test_no_location_hint_is_error(self):
        ann = {"id": "x", "label": "OC_SECTION", "rawText": "hi", "parent_id": None}
        result = validate_dumb_anchor_sidecar({"annotations": [ann]}, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(any("location hint" in e for e in result.errors))

    def test_negative_page_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(page=-1)]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("'page' must be an integer >= 0" in e for e in result.errors)
        )

    def test_bbox_non_numeric_is_error(self):
        sidecar = {
            "annotations": [
                self._pdf_ann(bbox={"left": "x", "top": 0, "right": 1, "bottom": 1})
            ]
        }
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(any("bbox.left must be a number" in e for e in result.errors))

    def test_end_not_greater_than_start_is_error(self):
        sidecar = {"annotations": [self._span_ann(start=5, end=5)]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("'end' must be an integer > 'start'" in e for e in result.errors)
        )

    def test_unresolved_label_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(label="NOT_DECLARED")]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("does not resolve in labels.json" in e for e in result.errors)
        )

    def test_span_label_declared_span_label_is_error(self):
        """A text/span annotation whose label is declared SPAN_LABEL must be
        rejected — the importer only accepts TOKEN_LABEL for span imports."""
        sidecar = {"annotations": [self._span_ann()]}
        result = validate_dumb_anchor_sidecar(
            sidecar, _labels_json(section_label_types={"OC_SECTION": "SPAN_LABEL"})
        )
        self.assertFalse(result.ok)
        self.assertTrue(
            any("SPAN_LABEL" in e and "TOKEN_LABEL" in e for e in result.errors),
            msg=result.summary(),
        )

    def test_dangling_parent_id_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(parent_id="does-not-exist")]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("does not reference any annotation 'id'" in e for e in result.errors)
        )

    def test_valid_parent_id_reference(self):
        parent = self._pdf_ann(id="p1", parent_id=None)
        child = self._pdf_ann(id="c1", parent_id="p1")
        sidecar = {"annotations": [child, parent]}  # forward reference OK
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertTrue(result.ok, msg=result.summary())

    # --- link_url / data passthrough validation ---

    def test_valid_link_url_and_data(self):
        ann = self._pdf_ann(
            label="OC_URL",
            link_url="https://example.com",
            data={"canonical_name": "France", "geocoded": True},
        )
        result = validate_dumb_anchor_sidecar(
            {"annotations": [ann]},
            _labels_json(section_label_types={"OC_URL": "TOKEN_LABEL"}),
        )
        self.assertTrue(result.ok, msg=result.summary())

    def test_non_string_link_url_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(link_url=123)]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(any("'link_url' must be a string" in e for e in result.errors))

    def test_non_object_data_is_error(self):
        sidecar = {"annotations": [self._pdf_ann(data=["not", "a", "dict"])]}
        result = validate_dumb_anchor_sidecar(sidecar, _labels_json())
        self.assertFalse(result.ok)
        self.assertTrue(any("'data' must be a JSON object" in e for e in result.errors))

    # --- annotation-to-annotation relationship validation ---

    def _rel_labels(self) -> dict:
        return _labels_json(
            section_label_types={
                "OC_SECTION": "TOKEN_LABEL",
                "OC_PARENT_CHILD": "RELATIONSHIP_LABEL",
            }
        )

    def test_valid_relationship(self):
        sidecar = {
            "annotations": [
                self._pdf_ann(id="a1"),
                self._pdf_ann(id="a2"),
            ],
            "relationships": [
                {
                    "id": "r1",
                    "relationshipLabel": "OC_PARENT_CHILD",
                    "source_annotation_ids": ["a1"],
                    "target_annotation_ids": ["a2"],
                }
            ],
        }
        result = validate_dumb_anchor_sidecar(sidecar, self._rel_labels())
        self.assertTrue(result.ok, msg=result.summary())

    def test_relationships_must_be_list(self):
        sidecar = {"annotations": [self._pdf_ann()], "relationships": {}}
        result = validate_dumb_anchor_sidecar(sidecar, self._rel_labels())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("'relationships' must be a JSON list" in e for e in result.errors)
        )

    def test_relationship_missing_label_is_error(self):
        sidecar = {
            "annotations": [self._pdf_ann(id="a1"), self._pdf_ann(id="a2")],
            "relationships": [
                {"source_annotation_ids": ["a1"], "target_annotation_ids": ["a2"]}
            ],
        }
        result = validate_dumb_anchor_sidecar(sidecar, self._rel_labels())
        self.assertFalse(result.ok)
        self.assertTrue(
            any("'relationshipLabel' must be a non-empty" in e for e in result.errors)
        )

    def test_relationship_empty_endpoints_is_error(self):
        sidecar = {
            "annotations": [self._pdf_ann(id="a1")],
            "relationships": [
                {
                    "relationshipLabel": "OC_PARENT_CHILD",
                    "source_annotation_ids": ["a1"],
                    "target_annotation_ids": [],
                }
            ],
        }
        result = validate_dumb_anchor_sidecar(sidecar, self._rel_labels())
        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                "'target_annotation_ids' must be a non-empty list" in e
                for e in result.errors
            )
        )

    def test_relationship_dangling_endpoint_is_error(self):
        sidecar = {
            "annotations": [self._pdf_ann(id="a1")],
            "relationships": [
                {
                    "relationshipLabel": "OC_PARENT_CHILD",
                    "source_annotation_ids": ["a1"],
                    "target_annotation_ids": ["ghost"],
                }
            ],
        }
        result = validate_dumb_anchor_sidecar(sidecar, self._rel_labels())
        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                "references annotation id 'ghost' not present" in e
                for e in result.errors
            )
        )

    def test_relationship_label_alias_accepted(self):
        """``label`` is accepted as an alias for ``relationshipLabel``."""
        sidecar = {
            "annotations": [self._pdf_ann(id="a1"), self._pdf_ann(id="a2")],
            "relationships": [
                {
                    "label": "OC_PARENT_CHILD",
                    "source_annotation_ids": ["a1"],
                    "target_annotation_ids": ["a2"],
                }
            ],
        }
        result = validate_dumb_anchor_sidecar(sidecar, self._rel_labels())
        self.assertTrue(result.ok, msg=result.summary())
