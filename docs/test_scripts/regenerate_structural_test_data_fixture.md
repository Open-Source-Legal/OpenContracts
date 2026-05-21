# Test: Regenerate `test_data.json` in the current structural-annotation schema

## Purpose

One-time regeneration of `opencontractserver/tests/fixtures/test_data.json`
(issue #1711, test-suite optimization Phase 3).

The fixture historically stored its 1,344 structural annotations and 472
structural relationships in the legacy `Annotation.document` / `Relationship.document`
schema. `BaseFixtureTestCase.setUp()` then ran a per-test migration loop that
created a `StructuralAnnotationSet` per document and moved the annotations /
relationships onto it. Regenerating the fixture in the current schema makes
that loop dead code, so it could be deleted.

The same pass also:

- populates `Document.md_summary_file` with `files/md_summaries/{pk}_summary.md`
  so the convention-based summary discovery / placeholder regeneration in
  `setUp()` is no longer needed; and
- drops the 3,304 `guardian.userobjectpermission` rows whose content type is
  `annotations.relationship` — relationships carry no individual object
  permissions in the current permission model (they inherit from document +
  corpus), so those rows were pure dead weight.

Object count: 7,584 → 4,284.

## Prerequisites

- A clean checkout with the pre-#1711 `test_data.json`.
- Python 3 (no database required — this is a pure JSON transform).

## Steps

1. From the repository root, run the transform below. It asserts the fixture
   is in the expected pre-migration shape before rewriting it.

   ```python
   import json
   from pathlib import Path

   FIXTURE = Path("opencontractserver/tests/fixtures/test_data.json")
   data = json.loads(FIXTURE.read_text())

   docs = sorted(
       (o for o in data if o["model"] == "documents.document"), key=lambda o: o["pk"]
   )
   anns = [o for o in data if o["model"] == "annotations.annotation"]
   rels = [o for o in data if o["model"] == "annotations.relationship"]

   assert all(
       a["fields"]["structural"] and a["fields"]["structural_set"] is None
       and a["fields"]["document"] is not None for a in anns
   )
   assert all(
       r["fields"]["structural"] and r["fields"]["structural_set"] is None
       and r["fields"]["document"] is not None for r in rels
   )

   # One StructuralAnnotationSet per document. content_hash mirrors the old
   # setUp() migration: doc.pdf_file_hash or f"test_doc_{doc.pk}".
   doc_to_set_pk, new_sets = {}, []
   for i, d in enumerate(docs, start=1):
       doc_pk, f = d["pk"], d["fields"]
       doc_to_set_pk[doc_pk] = i
       new_sets.append({
           "model": "annotations.structuralannotationset",
           "pk": i,
           "fields": {
               "user_lock": None, "backend_lock": False, "is_public": True,
               "creator": ["testuser"], "created": f["created"],
               "modified": f["modified"],
               "content_hash": f.get("pdf_file_hash") or f"test_doc_{doc_pk}",
               "parser_name": "FixtureMigration", "parser_version": "1.0",
               "page_count": f["page_count"], "token_count": None,
               "pawls_parse_file": f["pawls_parse_file"],
               "txt_extract_file": f["txt_extract_file"],
           },
       })
       f["structural_annotation_set"] = i
       f["md_summary_file"] = f"files/md_summaries/{doc_pk}_summary.md"

   for a in anns:
       a["fields"]["structural_set"] = doc_to_set_pk[a["fields"]["document"]]
       a["fields"]["document"] = None
   for r in rels:
       r["fields"]["structural_set"] = doc_to_set_pk[r["fields"]["document"]]
       r["fields"]["document"] = None

   data = [
       o for o in data
       if not (o["model"] == "guardian.userobjectpermission"
               and o["fields"]["content_type"] == ["annotations", "relationship"])
   ]
   first_doc_idx = next(
       i for i, o in enumerate(data) if o["model"] == "documents.document"
   )
   data[first_doc_idx:first_doc_idx] = new_sets

   FIXTURE.write_text(json.dumps(data, indent=2) + "\n")
   ```

2. Confirm the diff only touches the migrated objects:

   ```bash
   git diff --stat opencontractserver/tests/fixtures/test_data.json
   ```

3. Validate the regenerated fixture loads cleanly by running any
   `BaseFixtureTestCase` subclass:

   ```bash
   docker compose -f test.yml run --rm --no-deps django \
     pytest opencontractserver/tests/test_note_tree.py --reuse-db
   ```

## Expected Results

- 4 `annotations.structuralannotationset` objects added (pk 1–4).
- 1,344 annotations and 472 relationships now reference `structural_set`
  instead of `document` (XOR constraint satisfied).
- 4 documents reference `structural_annotation_set` and a real
  `md_summary_file` path.
- 3,304 `guardian.userobjectpermission` rows removed; the 280 rows for
  `annotations.annotationlabel` are unchanged.
- The fixture loads without `IntegrityError` / `CheckConstraint` violations
  and the dependent tests pass.

## Cleanup

None — this is a committed, one-time fixture migration.
