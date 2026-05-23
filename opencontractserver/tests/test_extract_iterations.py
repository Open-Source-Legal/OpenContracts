"""Tests for the Extract iteration / diff workflow.

Covers:
  * The pure ``diff_extracts`` helper (no DB, no Graphene)
  * The ``CreateExtractIteration`` mutation across all three axes
  * The ``compareExtracts`` GraphQL resolver
"""

# Make all annotations PEP-563 strings so referencing ``User`` (the runtime
# value returned by ``get_user_model()``) as a type doesn't raise mypy's
# "valid-type" error — same pattern used by other test modules in this suite.
from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.documents.models import Document
from opencontractserver.extracts.diff import (
    DIFF_CHANGED,
    DIFF_ONLY_IN_A,
    DIFF_ONLY_IN_B,
    DIFF_UNCHANGED,
    diff_extracts,
    summarise,
)
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _Ctx:
    def __init__(self, user):
        self.user = user


def _make_doc(user, *, version_tree_id=None, title="Doc"):
    return Document.objects.create(
        title=title,
        description="",
        pdf_file="path/to/x.pdf",
        creator=user,
        version_tree_id=version_tree_id or uuid.uuid4(),
    )


def _make_extract(user, name, *, fieldset, parent=None, model_config=None):
    extract = Extract.objects.create(
        name=name,
        fieldset=fieldset,
        creator=user,
        parent_extract=parent,
        model_config=model_config or {},
    )
    return extract


class DiffHelperTestCase(TestCase):
    """Exercises ``diff_extracts`` directly so the algorithm has unit-level
    coverage independent of GraphQL plumbing."""

    # Class-level annotations so mypy can see attributes assigned by
    # setUpTestData (Django's classmethod fixture pattern); without these
    # every self.user / self.fieldset / etc. access is flagged attr-defined.
    # Typed as Any rather than the concrete classes because `User = get_user_model()`
    # is a runtime variable, not a valid mypy type, and using concrete model
    # classes here would force the same kind of django-stubs gymnastics the
    # rest of the test suite avoids by baselining.
    user: Any
    fieldset: Any
    col_a: Any
    col_b: Any
    tree: Any
    doc_v1: Any
    doc_v2: Any
    extract_a: Any
    extract_b: Any

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="diffuser", password="x")

        cls.fieldset = Fieldset.objects.create(
            name="FS", description="d", creator=cls.user
        )
        cls.col_a = Column.objects.create(
            fieldset=cls.fieldset,
            name="company",
            query="What company?",
            output_type="str",
            creator=cls.user,
        )
        cls.col_b = Column.objects.create(
            fieldset=cls.fieldset,
            name="filing_date",
            query="When?",
            output_type="str",
            creator=cls.user,
        )

        cls.tree = uuid.uuid4()
        cls.doc_v1 = _make_doc(cls.user, version_tree_id=cls.tree, title="DocV1")
        # Only one Document per version tree may have is_current=True
        # (Document.Meta unique constraint), so demote v1 before v2 is born.
        cls.doc_v1.is_current = False
        cls.doc_v1.save(update_fields=["is_current"])
        cls.doc_v2 = _make_doc(cls.user, version_tree_id=cls.tree, title="DocV2")

        cls.extract_a = _make_extract(cls.user, "A", fieldset=cls.fieldset)
        cls.extract_b = _make_extract(
            cls.user, "B", fieldset=cls.fieldset, parent=cls.extract_a
        )

        # Same logical doc tree; A on v1, B on v2 (DOCUMENT_VERSIONS axis)
        cls.extract_a.documents.add(cls.doc_v1)
        cls.extract_b.documents.add(cls.doc_v2)

        # Cells: company unchanged, filing_date changed, plus an only_in_b cell
        Datacell.objects.create(
            extract=cls.extract_a,
            column=cls.col_a,
            document=cls.doc_v1,
            data_definition="str",
            data={"value": "Acme"},
            creator=cls.user,
        )
        Datacell.objects.create(
            extract=cls.extract_b,
            column=cls.col_a,
            document=cls.doc_v2,
            data_definition="str",
            data={"value": "Acme"},
            creator=cls.user,
        )
        Datacell.objects.create(
            extract=cls.extract_a,
            column=cls.col_b,
            document=cls.doc_v1,
            data_definition="str",
            data={"value": "2024-01-01"},
            creator=cls.user,
        )
        # filing_date on B is corrected — corrected_data should win in the diff
        b_cell = Datacell.objects.create(
            extract=cls.extract_b,
            column=cls.col_b,
            document=cls.doc_v2,
            data_definition="str",
            data={"value": "2024-01-01"},
            creator=cls.user,
        )
        b_cell.corrected_data = {"value": "2024-02-15"}
        b_cell.save(update_fields=["corrected_data"])

    def test_diff_aligns_by_version_tree_and_classifies(self):
        diffs = diff_extracts(
            self.extract_a,
            self.extract_b,
            cells_a=Datacell.objects.filter(extract=self.extract_a),
            cells_b=Datacell.objects.filter(extract=self.extract_b),
        )
        # 2 columns × 1 logical doc = 2 aligned rows
        self.assertEqual(len(diffs), 2)
        by_col = {d.column_key: d for d in diffs}
        self.assertEqual(by_col["company"].status, DIFF_UNCHANGED)
        self.assertEqual(by_col["filing_date"].status, DIFF_CHANGED)
        # Both rows share the same row_key (the version tree)
        self.assertEqual(by_col["company"].row_key, by_col["filing_date"].row_key)

    def test_summary_counts(self):
        diffs = diff_extracts(
            self.extract_a,
            self.extract_b,
            cells_a=Datacell.objects.filter(extract=self.extract_a),
            cells_b=Datacell.objects.filter(extract=self.extract_b),
        )
        s = summarise(diffs)
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["unchanged"], 1)
        self.assertEqual(s["changed"], 1)
        self.assertEqual(s["only_in_a"], 0)
        self.assertEqual(s["only_in_b"], 0)

    def test_only_in_b(self):
        # Add a B-only cell on a fresh doc / column
        col_c = Column.objects.create(
            fieldset=self.fieldset,
            name="ceo",
            query="Who?",
            output_type="str",
            creator=self.user,
        )
        Datacell.objects.create(
            extract=self.extract_b,
            column=col_c,
            document=self.doc_v2,
            data_definition="str",
            data={"value": "Jane"},
            creator=self.user,
        )
        diffs = diff_extracts(
            self.extract_a,
            self.extract_b,
            cells_a=Datacell.objects.filter(extract=self.extract_a),
            cells_b=Datacell.objects.filter(extract=self.extract_b),
        )
        self.assertEqual(sum(1 for d in diffs if d.status == DIFF_ONLY_IN_B), 1)
        self.assertEqual(sum(1 for d in diffs if d.status == DIFF_ONLY_IN_A), 0)


class CreateExtractIterationMutationTestCase(TestCase):
    # graphene.test.Client lacks type stubs for `.execute`, so annotate as
    # Any to keep mypy quiet without baselining the whole file.
    client: Any

    def setUp(self):
        self.user = User.objects.create_user(username="forker", password="x")
        self.client = Client(schema, context_value=_Ctx(self.user))

        self.fieldset = Fieldset.objects.create(
            name="FS", description="d", creator=self.user
        )
        self.col = Column.objects.create(
            fieldset=self.fieldset,
            name="company",
            query="What?",
            output_type="str",
            creator=self.user,
        )
        self.tree = uuid.uuid4()
        self.doc_v1 = _make_doc(self.user, version_tree_id=self.tree, title="V1")
        # mark v1 as not current and create v2 as current to exercise the
        # DOCUMENT_VERSIONS-axis re-resolution path
        self.doc_v1.is_current = False
        self.doc_v1.save(update_fields=["is_current"])
        self.doc_v2 = _make_doc(self.user, version_tree_id=self.tree, title="V2")

        self.source = Extract.objects.create(
            name="Source", fieldset=self.fieldset, creator=self.user
        )
        # Grant CRUD on the source extract so the mutation's permission
        # checks pass.
        set_permissions_for_obj_to_user(self.user, self.source, [PermissionTypes.CRUD])
        self.source.documents.add(self.doc_v1)

    def _mutate(self, *, axis, **extra):
        gid = to_global_id("ExtractType", self.source.id)
        # Use variables so the test doesn't have to escape JSON literals.
        return self.client.execute(
            """
            mutation Run(
              $sid: ID!, $axis: String!, $name: String,
              $modelConfig: GenericScalar, $autoStart: Boolean
            ) {
              createExtractIteration(
                sourceExtractId: $sid, axis: $axis, name: $name,
                modelConfig: $modelConfig, autoStart: $autoStart
              ) {
                ok message obj { id name }
              }
            }
            """,
            variable_values={
                "sid": gid,
                "axis": axis,
                **extra,
            },
        )

    def test_model_axis_shares_fieldset_and_captures_model(self):
        result = self._mutate(
            axis="MODEL",
            modelConfig={"model": "anthropic:claude-opus-4-7"},
        )
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createExtractIteration"]["ok"])

        new = Extract.objects.exclude(pk=self.source.pk).get()
        self.assertEqual(new.parent_extract_id, self.source.pk)
        # MODEL axis must share the parent's fieldset (no clone)
        self.assertEqual(new.fieldset_id, self.source.fieldset_id)
        self.assertEqual(new.model_config.get("model"), "anthropic:claude-opus-4-7")
        # Document set is byte-identical to parent
        self.assertEqual(
            list(new.documents.values_list("id", flat=True)),
            list(self.source.documents.values_list("id", flat=True)),
        )

    def test_document_versions_axis_promotes_to_current_doc(self):
        result = self._mutate(axis="DOCUMENT_VERSIONS")
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createExtractIteration"]["ok"])
        new = Extract.objects.exclude(pk=self.source.pk).get()
        # The iteration should now point at v2 (current), not v1
        self.assertEqual(list(new.documents.all()), [self.doc_v2])

    def test_fieldset_axis_clones_columns(self):
        result = self._mutate(axis="FIELDSET")
        self.assertIsNone(result.get("errors"))
        new = Extract.objects.exclude(pk=self.source.pk).get()
        self.assertNotEqual(new.fieldset_id, self.source.fieldset_id)
        # Cloned fieldset has a column with the same name
        self.assertTrue(new.fieldset.columns.filter(name="company").exists())

    def test_unknown_axis_returns_error(self):
        result = self._mutate(axis="BOGUS")
        self.assertFalse(result["data"]["createExtractIteration"]["ok"])

    def test_default_name_increments(self):
        self._mutate(axis="MODEL")
        self._mutate(axis="MODEL")
        names = list(
            Extract.objects.filter(parent_extract=self.source)
            .order_by("created")
            .values_list("name", flat=True)
        )
        self.assertEqual(len(names), 2)
        self.assertIn("(iteration 1)", names[0])
        self.assertIn("(iteration 2)", names[1])


class CompareExtractsResolverTestCase(TestCase):
    client: Any

    def setUp(self):
        self.user = User.objects.create_user(username="cmp", password="x")
        self.client = Client(schema, context_value=_Ctx(self.user))

        self.fieldset = Fieldset.objects.create(
            name="FS", description="d", creator=self.user
        )
        self.col = Column.objects.create(
            fieldset=self.fieldset,
            name="company",
            query="?",
            output_type="str",
            creator=self.user,
        )
        self.doc = _make_doc(self.user)
        # ExtractService.get_extract_datacells filters cells by document
        # READ permission. Grant CRUD on the doc so its cells are included.
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])
        self.a = Extract.objects.create(
            name="A", fieldset=self.fieldset, creator=self.user
        )
        self.b = Extract.objects.create(
            name="B",
            fieldset=self.fieldset,
            creator=self.user,
            parent_extract=self.a,
        )
        # compareExtracts checks READ on both extracts via the same path as
        # CreateExtractIteration; grant explicit guardian perms.
        set_permissions_for_obj_to_user(self.user, self.a, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.user, self.b, [PermissionTypes.CRUD])
        self.a.documents.add(self.doc)
        self.b.documents.add(self.doc)

        Datacell.objects.create(
            extract=self.a,
            column=self.col,
            document=self.doc,
            data_definition="str",
            data={"value": "X"},
            creator=self.user,
        )
        Datacell.objects.create(
            extract=self.b,
            column=self.col,
            document=self.doc,
            data_definition="str",
            data={"value": "Y"},
            creator=self.user,
        )

    def test_compare_extracts_returns_aligned_diff(self):
        gid_a = to_global_id("ExtractType", self.a.id)
        gid_b = to_global_id("ExtractType", self.b.id)
        result = self.client.execute(
            """
            query Cmp($a: ID!, $b: ID!) {
              compareExtracts(extractAId: $a, extractBId: $b) {
                summary { unchanged changed onlyInA onlyInB total }
                cells { rowKey columnKey status }
              }
            }
            """,
            variable_values={"a": gid_a, "b": gid_b},
        )
        self.assertIsNone(result.get("errors"), result.get("errors"))
        diff = result["data"]["compareExtracts"]
        self.assertIsNotNone(diff)
        self.assertEqual(diff["summary"]["total"], 1)
        self.assertEqual(diff["summary"]["changed"], 1)
        self.assertEqual(diff["cells"][0]["status"], "CHANGED")
