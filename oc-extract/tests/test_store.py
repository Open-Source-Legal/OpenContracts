from __future__ import annotations

import pytest
from oc_extract.schema import FieldSet, FieldSpec
from oc_extract.store import Store

from .conftest import SAMPLE_CONTRACT


def test_document_roundtrip_and_dedupe(store: Store):
    doc_id = store.add_document("MSA", SAMPLE_CONTRACT, meta={"source": "test"})
    again = store.add_document("MSA copy", SAMPLE_CONTRACT)
    assert again == doc_id  # deduped by content hash

    doc = store.get_document(doc_id)
    assert doc["text"] == SAMPLE_CONTRACT
    assert doc["meta"] == {"source": "test"}

    listing = store.list_documents()
    assert len(listing) == 1
    assert "text" not in listing[0]
    assert listing[0]["text_length"] == len(SAMPLE_CONTRACT)


def test_missing_document_raises(store: Store):
    with pytest.raises(KeyError):
        store.get_document(999)


def test_fieldset_roundtrip(store: Store, sample_fieldset: FieldSet):
    fs_id = store.create_fieldset(sample_fieldset)
    fs = store.get_fieldset(fs_id)
    assert fs["name"] == "Key terms"
    assert [f["name"] for f in fs["fields"]] == ["parties", "monthly_fee"]
    # Rehydration produces an equivalent FieldSpec.
    spec = Store.field_spec(fs["fields"][0])
    assert isinstance(spec, FieldSpec)
    assert spec.extract_is_list is True
    assert store.list_fieldsets()[0]["field_count"] == 2


def test_extract_and_cell_lifecycle(seeded: dict):
    store: Store = seeded["store"]
    extract_id = store.create_extract(
        "run 1", seeded["fieldset_id"], [seeded["doc_id"]], model="openai:gpt-4o-mini"
    )
    extract = store.get_extract(extract_id)
    assert extract["document_ids"] == [seeded["doc_id"]]
    assert extract["cell_counts"]["total"] == 0

    fs = store.get_fieldset(seeded["fieldset_id"])
    cell_id = store.create_cell(
        extract_id, fs["fields"][0]["id"], seeded["doc_id"], "str"
    )
    store.mark_cell_started(cell_id)
    store.mark_cell_completed(
        cell_id,
        ["ACME Corporation", "Widgets Incorporated"],
        [{"kind": "grounding", "start": 0, "end": 10, "snippet": "MASTER SER"}],
        llm_log="[]",
    )

    cell = store.get_cell(cell_id, include_llm_log=True)
    assert cell["value"] == ["ACME Corporation", "Widgets Incorporated"]
    assert cell["data"] == {"data": ["ACME Corporation", "Widgets Incorporated"]}
    assert cell["sources"][0]["kind"] == "grounding"
    assert cell["llm_log"] == "[]"
    assert cell["completed"] is not None

    cell2_id = store.create_cell(
        extract_id, fs["fields"][1]["id"], seeded["doc_id"], "float"
    )
    store.mark_cell_failed(
        cell2_id, failure_mode="usage_limit_exceeded", stacktrace="boom"
    )

    counts = store.get_extract(extract_id)["cell_counts"]
    assert counts == {"total": 2, "completed": 1, "failed": 1}

    table = store.extract_table(extract_id)
    assert len(table) == 1
    values = table[0]["values"]
    assert values["parties"]["status"] == "completed"
    assert values["monthly_fee"]["status"] == "failed"
    assert values["monthly_fee"]["failure_mode"] == "usage_limit_exceeded"


def test_create_cell_is_idempotent_reset(seeded: dict):
    store: Store = seeded["store"]
    fs = store.get_fieldset(seeded["fieldset_id"])
    extract_id = store.create_extract("run", seeded["fieldset_id"], [seeded["doc_id"]])
    cell_id = store.create_cell(
        extract_id, fs["fields"][0]["id"], seeded["doc_id"], "str"
    )
    store.mark_cell_completed(cell_id, "x", [])
    # Re-creating the same cell resets it for a re-run.
    same_id = store.create_cell(
        extract_id, fs["fields"][0]["id"], seeded["doc_id"], "str"
    )
    assert same_id == cell_id
    assert store.get_cell(cell_id)["completed"] is None


def test_create_extract_validates_references(seeded: dict):
    store: Store = seeded["store"]
    with pytest.raises(KeyError):
        store.create_extract("x", 999, [seeded["doc_id"]])
    with pytest.raises(KeyError):
        store.create_extract("x", seeded["fieldset_id"], [999])
