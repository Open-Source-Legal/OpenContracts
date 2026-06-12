"""Service-level privacy scoping for analysis-/extract-rooted Relationships.

2026-06 permissioning audit: relationships now enforce the same
``created_by_analysis`` / ``created_by_extract`` privacy model as
annotations — in ``RelationshipManager.user_can`` and
``RelationshipManager.visible_to_user`` (pinned by
``test_authorization_invariants``) and in the document-view listing path
exercised here (``RelationshipService.get_document_relationships``, which
routes its source-visibility subqueries through
``opencontractserver.utils.source_visibility``).

The manager-surface invariants live in ``test_authorization_invariants``;
this module covers the GraphQL-facing service listing.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    AnnotationLabel,
    Relationship,
)
from opencontractserver.annotations.services import RelationshipService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class RelationshipServicePrivacyScopingTestCase(TestCase):
    """Privacy-rooted relationships in the document-view listing."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="rel_priv_owner", email="rpo@scope.test", password="x"
        )
        self.viewer = User.objects.create_user(
            username="rel_priv_viewer", email="rpv@scope.test", password="x"
        )
        self.group_viewer = User.objects.create_user(
            username="rel_priv_group_viewer", email="rpg@scope.test", password="x"
        )

        self.corpus = Corpus.objects.create(
            title="Rel Privacy Corpus", creator=self.owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Rel Privacy Doc", creator=self.owner, is_public=False
        )
        for reader in (self.viewer, self.group_viewer):
            set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])
            set_permissions_for_obj_to_user(
                reader, self.document, [PermissionTypes.READ]
            )

        self.rel_label = AnnotationLabel.objects.create(
            text="rel_priv_label", label_type="RELATIONSHIP_LABEL", creator=self.owner
        )

        self.analyzer = Analyzer.objects.create(
            id="rel_priv_analyzer",
            description="x",
            creator=self.owner,
            task_name="opencontractserver.tasks.noop",
        )
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
        )
        self.fieldset = Fieldset.objects.create(
            name="Rel Privacy Fieldset", creator=self.owner
        )
        self.extract = Extract.objects.create(
            name="Rel Privacy Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )

        # Plain relationship — visible to anyone with doc+corpus READ.
        self.plain_rel = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            structural=False,
        )
        # Privacy-rooted rows. ``analysis`` (the organizational FK) is left
        # NULL so they surface in the service's manual mode
        # (``analysis_id=None`` filters ``analysis__isnull=True``) and the
        # exclusion observed is attributable to privacy alone.
        self.rel_via_analysis = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            structural=False,
            created_by_analysis=self.analysis,
        )
        self.rel_via_extract = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            structural=False,
            created_by_extract=self.extract,
        )

    def _listed_pks(self, user) -> set[int]:
        return set(
            RelationshipService.get_document_relationships(
                document_id=self.document.id,
                user=user,
                corpus_id=self.corpus.id,
            ).values_list("pk", flat=True)
        )

    def test_viewer_without_source_access_sees_only_plain_relationship(self):
        listed = self._listed_pks(self.viewer)
        self.assertIn(self.plain_rel.pk, listed)
        self.assertNotIn(self.rel_via_analysis.pk, listed)
        self.assertNotIn(self.rel_via_extract.pk, listed)

    def test_owner_sees_all_rows(self):
        listed = self._listed_pks(self.owner)
        self.assertEqual(
            listed,
            {self.plain_rel.pk, self.rel_via_analysis.pk, self.rel_via_extract.pk},
        )

    def test_user_level_source_grant_unlocks_listing(self):
        set_permissions_for_obj_to_user(
            self.viewer, self.analysis, [PermissionTypes.READ]
        )
        listed = self._listed_pks(self.viewer)
        self.assertIn(self.rel_via_analysis.pk, listed)
        # The analysis grant must not bleed into the extract-rooted row.
        self.assertNotIn(self.rel_via_extract.pk, listed)

    def test_group_level_source_grant_unlocks_listing(self):
        group = Group.objects.create(name="rel_priv_group")
        self.group_viewer.groups.add(group)
        assign_perm("read_analysis", group, self.analysis)
        listed = self._listed_pks(self.group_viewer)
        self.assertIn(
            self.rel_via_analysis.pk,
            listed,
            "group-granted source READ must unlock the listing "
            "(source_visibility consults group object-permissions)",
        )
        self.assertNotIn(self.rel_via_extract.pk, listed)

    def test_structural_rows_bypass_privacy_in_listing(self):
        structural_private = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            structural=True,
            created_by_analysis=self.analysis,
        )
        listed = set(
            RelationshipService.get_document_relationships(
                document_id=self.document.id,
                user=self.viewer,
                corpus_id=self.corpus.id,
                structural=True,
            ).values_list("pk", flat=True)
        )
        self.assertIn(structural_private.pk, listed)
