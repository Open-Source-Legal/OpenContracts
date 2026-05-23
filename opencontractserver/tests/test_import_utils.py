from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.types.dicts import (
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.utils.importing import import_annotations, import_relationships


class TestImportUtils(TestCase):
    """
    Tests for import_annotations and import_relationships utility functions.
    """

    @classmethod
    def setUpTestData(cls):
        # Create user
        cls.user = get_user_model().objects.create(
            username="testuser", password="testpass"
        )

        # Optionally create a doc and corpus if needed
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        cls.doc = Document.objects.create(title="Test Document", creator=cls.user)
        cls.corpus = Corpus.objects.create(title="Test Corpus", creator=cls.user)

        # Create some labels and a label lookup
        cls.label_1 = AnnotationLabel.objects.create(
            text="LabelOne",
            creator=cls.user,
            label_type="TOKEN_LABEL",
        )
        cls.label_2 = AnnotationLabel.objects.create(
            text="LabelTwo",
            creator=cls.user,
            label_type="TOKEN_LABEL",
        )
        cls.rel_label = AnnotationLabel.objects.create(
            text="RelationshipLabel",
            creator=cls.user,
            label_type="RELATIONSHIP_LABEL",
        )

        cls.label_lookup = {
            "LabelOne": cls.label_1,
            "LabelTwo": cls.label_2,
            "RelationshipLabel": cls.rel_label,
        }

    def test_import_annotations(self):
        """
        Test importing annotations with parent-child relationships,
        returning a mapping from old to new annotation IDs.
        """
        annotation_data: list[OpenContractsAnnotationPythonType] = [
            {
                "id": "old-annot-1",
                "annotationLabel": "LabelOne",
                "rawText": "Sample text 1",
                "page": 1,
                "annotation_json": {"bounds": [0, 0, 10, 10]},
                "parent_id": None,
                "annotation_type": None,
                "structural": False,
            },
            {
                "id": "old-annot-2",
                "annotationLabel": "LabelTwo",
                "rawText": "Sample text 2",
                "page": 2,
                "annotation_json": {"bounds": [10, 10, 20, 20]},
                "parent_id": "old-annot-1",
                "annotation_type": None,
                "structural": True,
            },
        ]

        old_id_map = import_annotations(
            user_id=self.user.id,
            doc_obj=self.doc,
            corpus_obj=self.corpus,
            annotations_data=annotation_data,
            label_lookup=self.label_lookup,
        )

        self.assertEqual(Annotation.objects.count(), 2)
        ann1 = Annotation.objects.get(raw_text="Sample text 1")
        ann2 = Annotation.objects.get(raw_text="Sample text 2")

        # Verify old->new mapping
        self.assertIn("old-annot-1", old_id_map)
        self.assertIn("old-annot-2", old_id_map)
        self.assertEqual(ann1.pk, old_id_map["old-annot-1"])
        self.assertEqual(ann2.pk, old_id_map["old-annot-2"])

        # Check parent relationship
        self.assertIsNone(ann1.parent, "First annotation should have no parent.")
        self.assertEqual(
            ann2.parent, ann1, "Second annotation should have the first as its parent."
        )
        self.assertTrue(ann2.structural, "Second annotation should be structural.")

    def test_import_relationships(self):
        """
        Test importing relationships, referencing existing annotations via
        the dict returned from import_annotations.
        """
        # Set up annotations first
        annotation_data: list[OpenContractsAnnotationPythonType] = [
            {
                "id": "old-a1",
                "annotationLabel": "LabelOne",
                "rawText": "Ann text 1",
                "page": 1,
                "annotation_json": {"bounds": [0, 0, 10, 10]},
                "parent_id": None,
                "annotation_type": None,
                "structural": True,
            },
            {
                "id": "old-a2",
                "annotationLabel": "LabelOne",
                "rawText": "Ann text 2",
                "page": 1,
                "annotation_json": {"bounds": [10, 10, 20, 20]},
                "parent_id": None,
                "annotation_type": None,
                "structural": True,
            },
            {
                "id": "old-a3",
                "annotationLabel": "LabelTwo",
                "rawText": "Ann text 3",
                "page": 2,
                "annotation_json": {"bounds": [20, 20, 30, 30]},
                "parent_id": None,
                "annotation_type": None,
                "structural": True,
            },
        ]

        # Get annotation_id_map from import_annotations
        annotation_id_map = import_annotations(
            user_id=self.user.id,
            doc_obj=self.doc,
            corpus_obj=self.corpus,
            annotations_data=annotation_data,
            label_lookup=self.label_lookup,
        )

        # Now define relationships to import
        relationship_data: list[OpenContractsRelationshipPythonType] = [
            {
                "id": "old-rel-1",
                "relationshipLabel": "RelationshipLabel",
                "source_annotation_ids": ["old-a1"],
                "target_annotation_ids": ["old-a2", "old-a3"],
                "structural": True,
            },
            {
                "id": "old-rel-2",
                "relationshipLabel": "RelationshipLabel",
                "source_annotation_ids": ["old-a2"],
                "target_annotation_ids": ["old-a3"],
                "structural": True,
            },
        ]

        old_rel_id_map = import_relationships(
            user_id=self.user.id,
            doc_obj=self.doc,
            corpus_obj=self.corpus,
            relationships_data=relationship_data,
            label_lookup=self.label_lookup,
            annotation_id_map=annotation_id_map,
        )

        self.assertEqual(Relationship.objects.count(), 2)
        rel1 = old_rel_id_map["old-rel-1"]
        rel2 = old_rel_id_map["old-rel-2"]

        self.assertEqual(rel1.source_annotations.count(), 1)
        self.assertEqual(rel1.target_annotations.count(), 2)
        self.assertEqual(rel2.source_annotations.count(), 1)
        self.assertEqual(rel2.target_annotations.count(), 1)

        ann_ids_rel1_source = list(rel1.source_annotations.values_list("id", flat=True))
        ann_ids_rel1_targets = list(
            rel1.target_annotations.values_list("id", flat=True)
        )

        ann_ids_rel2_source = list(rel2.source_annotations.values_list("id", flat=True))
        ann_ids_rel2_targets = list(
            rel2.target_annotations.values_list("id", flat=True)
        )

        # Validate that the correct DB IDs are in place
        self.assertIn(annotation_id_map["old-a1"], ann_ids_rel1_source)
        self.assertIn(annotation_id_map["old-a2"], ann_ids_rel1_targets)
        self.assertIn(annotation_id_map["old-a3"], ann_ids_rel1_targets)

        self.assertIn(annotation_id_map["old-a2"], ann_ids_rel2_source)
        self.assertIn(annotation_id_map["old-a3"], ann_ids_rel2_targets)


class TestImportAnnotationsPermissionInvariants(TestCase):
    """Lock in the invariants that allow ``import_annotations`` to skip
    per-annotation guardian writes.

    ``AnnotationUserObjectPermission`` rows are NOT consulted by:
        * ``AnnotationQuerySet.visible_to_user`` (uses doc/corpus + structural + creator)
        * ``AnnotationService._compute_effective_permissions`` (doc/corpus only)
        * ``user_can`` for annotations (delegates to optimizer)

    These tests exist so any future regression that re-introduces a
    consumer of those rows gets caught immediately — without these
    tests, ``import_annotations`` could silently start producing wrong
    visibility for non-creator readers.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        User = get_user_model()
        cls.creator = User.objects.create_user(username="creator", password="pw")
        cls.outsider = User.objects.create_user(username="outsider", password="pw")
        cls.collaborator = User.objects.create_user(
            username="collaborator", password="pw"
        )
        cls.anonymous = AnonymousUser()
        cls.superuser = User.objects.create_superuser(
            username="root", password="pw", email="r@example.com"
        )

        # Public-doc-in-public-corpus: anyone can see; creator owns.
        cls.public_corpus = Corpus.objects.create(
            title="Public", creator=cls.creator, is_public=True
        )
        cls.public_doc = Document.objects.create(
            title="Public Doc", creator=cls.creator, is_public=True
        )
        cls.public_doc, _, _ = cls.public_corpus.add_document(
            document=cls.public_doc, user=cls.creator
        )

        # Private-doc-in-private-corpus: only creator + collaborator (via guardian).
        cls.private_corpus = Corpus.objects.create(
            title="Private", creator=cls.creator, is_public=False
        )
        cls.private_doc = Document.objects.create(
            title="Private Doc", creator=cls.creator, is_public=False
        )
        cls.private_doc, _, _ = cls.private_corpus.add_document(
            document=cls.private_doc, user=cls.creator
        )

        # Grant creator full perms on the docs/corpuses they "own". Real
        # production flows (corpus.import_content, the corpus services) call
        # set_permissions_for_obj_to_user after creation; bare
        # ``Document.objects.create(creator=...)`` only sets the FK.
        # The optimizer reads doc+corpus guardian rows, not the creator
        # FK, so we replicate the production grant here.
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        for obj in (cls.public_doc, cls.private_doc):
            set_permissions_for_obj_to_user(cls.creator, obj, [PermissionTypes.ALL])
        for obj in (cls.public_corpus, cls.private_corpus):
            set_permissions_for_obj_to_user(cls.creator, obj, [PermissionTypes.ALL])

        # Grant collaborator doc+corpus read so they can see annotations
        # via the doc/corpus path (this is the legitimate sharing flow,
        # NOT per-annotation perms).
        from guardian.shortcuts import assign_perm

        assign_perm("documents.read_document", cls.collaborator, cls.private_doc)
        assign_perm("corpuses.read_corpus", cls.collaborator, cls.private_corpus)

        cls.label = AnnotationLabel.objects.create(
            text="ParaLabel", creator=cls.creator, label_type="SPAN_LABEL"
        )

    def _ingest(self, doc, corpus, *, structural):
        """Run import_annotations on a small fixture and return the resulting Annotations."""
        annotation_data: list[OpenContractsAnnotationPythonType] = [
            {
                "id": f"a-{i}",
                "annotationLabel": "ParaLabel",
                "rawText": f"text {i}",
                "page": 1,
                "annotation_json": {"bounds": [i, 0, 10, 10]},
                "parent_id": None,
                "annotation_type": None,
                "structural": structural,
            }
            for i in range(3)
        ]
        old_to_new = import_annotations(
            user_id=self.creator.id,
            doc_obj=doc,
            corpus_obj=corpus,
            annotations_data=annotation_data,
            label_lookup={"ParaLabel": self.label},
        )
        return Annotation.objects.filter(pk__in=old_to_new.values())

    def test_creator_sees_own_imported_annotations(self):
        """The creator can always see annotations they imported."""
        annots = self._ingest(self.public_doc, self.public_corpus, structural=False)
        creator_visible = Annotation.objects.visible_to_user(self.creator)
        for a in annots:
            self.assertIn(a, creator_visible)

    def test_collaborator_sees_via_doc_and_corpus_perms_not_annotation_perms(self):
        """Non-creator visibility flows from doc+corpus permissions only.

        The collaborator was granted ``read_document`` and ``read_corpus``
        but explicitly NOT any annotation-level guardian rows. They must
        still see the annotations (because the optimizer derives perms
        from doc+corpus, not from ``AnnotationUserObjectPermission``).
        """
        annots = self._ingest(self.private_doc, self.private_corpus, structural=False)
        visible = Annotation.objects.visible_to_user(self.collaborator)
        for a in annots:
            self.assertIn(
                a,
                visible,
                "Collaborator should see annotations on a doc/corpus they "
                "have read perm on, regardless of per-annotation guardian rows.",
            )

    def test_outsider_blocked_by_doc_and_corpus_perms(self):
        """Outsider with no doc/corpus perms cannot see private annotations."""
        annots = self._ingest(self.private_doc, self.private_corpus, structural=False)
        visible = Annotation.objects.visible_to_user(self.outsider)
        for a in annots:
            self.assertNotIn(
                a,
                visible,
                "Outsider with no doc/corpus perms must not see private annotations.",
            )

    def test_anonymous_sees_only_structural_on_public_doc(self):
        """Anonymous users see structural annotations on public docs only."""
        # Public doc, structural annotations: visible to anonymous.
        struct_annots = self._ingest(
            self.public_doc, self.public_corpus, structural=True
        )
        visible = Annotation.objects.visible_to_user(self.anonymous)
        for a in struct_annots:
            self.assertIn(a, visible)

        # Private doc, structural: NOT visible to anonymous.
        struct_private = self._ingest(
            self.private_doc, self.private_corpus, structural=True
        )
        visible_private = Annotation.objects.visible_to_user(self.anonymous)
        for a in struct_private:
            self.assertNotIn(a, visible_private)

    def test_user_can_uses_doc_corpus_for_annotations(self):
        """``user_can`` for annotations consults the optimizer (doc+corpus)
        — not ``AnnotationUserObjectPermission``.
        """
        from opencontractserver.types.enums import PermissionTypes

        annots = self._ingest(self.private_doc, self.private_corpus, structural=False)
        for a in annots:
            # Creator: doc creator → has all perms via doc.
            self.assertTrue(a.user_can(self.creator, PermissionTypes.READ))
            # Collaborator: granted doc+corpus read → can read annotation.
            self.assertTrue(a.user_can(self.collaborator, PermissionTypes.READ))
            # Outsider: no doc/corpus perms → cannot read.
            self.assertFalse(a.user_can(self.outsider, PermissionTypes.READ))
            # Superuser: always.
            self.assertTrue(a.user_can(self.superuser, PermissionTypes.READ))

    def test_no_per_annotation_guardian_rows_are_required(self):
        """The annotation-level guardian table can be empty without
        affecting visibility outcomes.

        After this test passes, ``import_annotations`` is free to skip
        the per-annotation ``set_permissions_for_obj_to_user`` call —
        the annotations remain visible to readers who have doc+corpus
        access. We assert this by clearing any guardian rows that the
        ingest loop wrote and re-running visibility checks.
        """
        from opencontractserver.annotations.models import (
            AnnotationUserObjectPermission,
        )
        from opencontractserver.types.enums import PermissionTypes

        annots = list(
            self._ingest(self.private_doc, self.private_corpus, structural=False)
        )
        # Clear any per-annotation guardian rows that the import wrote.
        AnnotationUserObjectPermission.objects.filter(
            content_object__in=annots
        ).delete()

        # Visibility and perm checks must still resolve correctly via doc+corpus.
        for a in annots:
            self.assertIn(
                a,
                Annotation.objects.visible_to_user(self.creator),
                "Creator must still see their annotation without per-row perms.",
            )
            self.assertIn(
                a,
                Annotation.objects.visible_to_user(self.collaborator),
                "Collaborator must still see annotation via doc/corpus perms.",
            )
            self.assertNotIn(
                a,
                Annotation.objects.visible_to_user(self.outsider),
                "Outsider must still be blocked via doc/corpus perms.",
            )
            self.assertTrue(a.user_can(self.collaborator, PermissionTypes.READ))
            self.assertFalse(a.user_can(self.outsider, PermissionTypes.READ))
