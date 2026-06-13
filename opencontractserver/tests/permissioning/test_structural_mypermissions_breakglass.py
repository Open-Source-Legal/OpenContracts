"""Pre-computed myPermissions mirror the structural-write break-glass.

The structural-write break-glass (``AnnotationManager.user_can`` /
``RelationshipManager.user_can``) lets superusers — and ONLY superusers —
write structural rows. The list services annotate per-row
``_can_update`` / ``_can_delete`` values that feed GraphQL
``myPermissions``; after the scoped-admin migration removed the superuser
short-circuit from ``_compute_effective_permissions``, the annotation-side
mask hardcoded ``False`` on structural rows for everyone (under-reporting
for superusers) and the relationship-side annotate had no structural mask
at all (over-reporting doc+corpus writes for normal users). 2026-06
permissioning audit: both services now mask structural rows to
``user.is_superuser``, matching what mutations will actually allow.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.annotations.services import (
    AnnotationService,
    RelationshipService,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class StructuralMyPermissionsBreakGlassTestCase(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="bg_admin", email="bga@bg.test", password="x"
        )
        self.owner = User.objects.create_user(
            username="bg_owner", email="bgo@bg.test", password="x"
        )

        # The superuser is the corpus/document CREATOR so it can read the
        # rows like a normal user (scoped admin access — no blanket
        # visibility); the break-glass under test is the WRITE mask only.
        self.corpus = Corpus.objects.create(
            title="BG Corpus", creator=self.superuser, is_public=False
        )
        self.document = Document.objects.create(
            title="BG Doc", creator=self.superuser, is_public=False
        )
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            path="bg-doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.superuser,
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )

        self.token_label = AnnotationLabel.objects.create(
            text="bg", label_type="TOKEN_LABEL", creator=self.superuser
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="bg_rel", label_type="RELATIONSHIP_LABEL", creator=self.superuser
        )

        self.structural_ann = Annotation.objects.create(
            raw_text="structural",
            json={"x": 1},
            page=1,
            annotation_label=self.token_label,
            creator=self.superuser,
            document=self.document,
            corpus=self.corpus,
            structural=True,
        )
        self.normal_ann = Annotation.objects.create(
            raw_text="normal",
            json={"x": 2},
            page=1,
            annotation_label=self.token_label,
            creator=self.superuser,
            document=self.document,
            corpus=self.corpus,
        )
        self.structural_rel = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.superuser,
            document=self.document,
            corpus=self.corpus,
            structural=True,
        )
        self.normal_rel = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.superuser,
            document=self.document,
            corpus=self.corpus,
        )

    def _annotation_perm_map(self, user) -> dict[int, tuple[bool, bool, bool]]:
        rows = AnnotationService.get_document_annotations(
            document_id=self.document.id,
            user=user,
            corpus_id=self.corpus.id,
        )
        return {row.pk: (row._can_read, row._can_update, row._can_delete) for row in rows}

    def _relationship_perm_map(self, user) -> dict[int, tuple[bool, bool, bool]]:
        rows = RelationshipService.get_document_relationships(
            document_id=self.document.id,
            user=user,
            corpus_id=self.corpus.id,
        )
        return {row.pk: (row._can_read, row._can_update, row._can_delete) for row in rows}

    def test_superuser_sees_structural_writes_via_breakglass(self):
        perms = self._annotation_perm_map(self.superuser)
        self.assertEqual(perms[self.structural_ann.pk], (True, True, True))
        self.assertEqual(perms[self.normal_ann.pk], (True, True, True))
        # myPermissions must agree with what the mutation gate will allow.
        self.assertTrue(
            self.structural_ann.user_can(self.superuser, PermissionTypes.UPDATE)
        )

    def test_owner_with_crud_is_masked_on_structural_annotation(self):
        perms = self._annotation_perm_map(self.owner)
        self.assertEqual(
            perms[self.structural_ann.pk],
            (True, False, False),
            "non-superuser shown structural write affordances — UI would "
            "offer an edit the mutation gate denies",
        )
        self.assertEqual(perms[self.normal_ann.pk], (True, True, True))
        self.assertFalse(
            self.structural_ann.user_can(self.owner, PermissionTypes.UPDATE)
        )

    def test_superuser_sees_structural_relationship_writes_via_breakglass(self):
        perms = self._relationship_perm_map(self.superuser)
        self.assertEqual(perms[self.structural_rel.pk], (True, True, True))
        self.assertEqual(perms[self.normal_rel.pk], (True, True, True))
        self.assertTrue(
            self.structural_rel.user_can(self.superuser, PermissionTypes.UPDATE)
        )

    def test_owner_with_crud_is_masked_on_structural_relationship(self):
        perms = self._relationship_perm_map(self.owner)
        self.assertEqual(
            perms[self.structural_rel.pk],
            (True, False, False),
            "relationship listing previously reported raw doc+corpus writes "
            "on structural rows — must be masked like annotations",
        )
        self.assertEqual(perms[self.normal_rel.pk], (True, True, True))
        self.assertFalse(
            self.structural_rel.user_can(self.owner, PermissionTypes.UPDATE)
        )
