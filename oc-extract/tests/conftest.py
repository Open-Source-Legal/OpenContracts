from __future__ import annotations

import pytest
from oc_extract.schema import FieldSet, FieldSpec
from oc_extract.store import Store

SAMPLE_CONTRACT = """MASTER SERVICES AGREEMENT

This Master Services Agreement (the "Agreement") is entered into as of
January 15, 2024 (the "Effective Date") by and between ACME Corporation,
a Delaware corporation ("Provider"), and Widgets Incorporated, a New York
corporation ("Customer").

1. TERM. This Agreement shall commence on the Effective Date and continue
for a period of three (3) years, unless earlier terminated.

2. FEES. Customer shall pay Provider a monthly fee of $12,500, due within
thirty (30) days of invoice.

3. CONFIDENTIALITY. Each party agrees to maintain the confidentiality of
the other party's Confidential Information for a period of five (5) years.

4. GOVERNING LAW. This Agreement shall be governed by the laws of the
State of Delaware.
"""


@pytest.fixture
def store(tmp_path) -> Store:
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def sample_fieldset() -> FieldSet:
    return FieldSet(
        name="Key terms",
        description="Core contract terms",
        fields=[
            FieldSpec(
                name="parties", query="Who are the parties?", extract_is_list=True
            ),
            FieldSpec(
                name="monthly_fee",
                query="What is the monthly fee?",
                output_type="float",
            ),
        ],
    )


@pytest.fixture
def seeded(store: Store, sample_fieldset: FieldSet) -> dict:
    doc_id = store.add_document("MSA", SAMPLE_CONTRACT)
    fs_id = store.create_fieldset(sample_fieldset)
    return {"store": store, "doc_id": doc_id, "fieldset_id": fs_id}
