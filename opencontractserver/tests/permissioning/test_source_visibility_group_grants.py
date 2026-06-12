"""Group-granted source permissions unlock private rows in LIST queries.

2026-06 permissioning audit: the ``created_by_analysis`` /
``created_by_extract`` privacy gates in list paths previously consulted
only the USER object-permission tables, so a viewer whose analysis/extract
grant arrived via a Django GROUP passed ``user_can`` (which resolves group
grants by default) but never saw the private rows in lists — a
filter/check parity drift. The gates now route through
``opencontractserver.utils.source_visibility``, which joins the group
object-permission tables.

Manager-surface parity is pinned in ``test_authorization_invariants``;
this module covers the GraphQL-facing service listings
(``AnnotationService.get_document_annotations`` /
``AnnotationService.get_corpus_annotations``).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.annotations.services import AnnotationService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class AnnotationServiceGroupGrantTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="src_grp_owner", email="sgo@grp.test", password="x"
        )
        self.group_viewer = User.objects.create_user(
            username="src_grp_viewer", email="sgv@grp.test", password="x"
        )
        self.group = Group.objects.create(name="source_visibility_group")
        self.group_viewer.groups.add(self.group)

        self.corpus = Corpus.objects.create(
            title="Group Grant Corpus", creator=self.owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Group Grant Doc", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.group_viewer, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.group_viewer, self.document, [PermissionTypes.READ]
        )
        # ``get_document_annotations`` (with corpus context) and
        # ``get_corpus_annotations`` both require a current, non-deleted
        # DocumentPath for the document in the corpus.
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            path="group-grant-doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )

        self.token_label = AnnotationLabel.objects.create(
            text="grp", label_type="TOKEN_LABEL", creator=self.owner
        )

        self.analyzer = Analyzer.objects.create(
            id="src_grp_analyzer",
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
            name="Group Grant Fieldset", creator=self.owner
        )
        self.extract = Extract.objects.create(
            name="Group Grant Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )

        # ``analysis`` (organizational FK) stays NULL so the rows surface in
        # manual mode and any exclusion is attributable to privacy alone.
        self.ann_via_analysis = Annotation.objects.create(
            raw_text="via analysis",
            json={"x": 1},
            page=1,
            annotation_label=self.token_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
        )
        self.ann_via_extract = Annotation.objects.create(
            raw_text="via extract",
            json={"x": 2},
            page=1,
            annotation_label=self.token_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            created_by_extract=self.extract,
        )

    def _document_listing_pks(self, user) -> set[int]:
        return set(
            AnnotationService.get_document_annotations(
                document_id=self.document.id,
                user=user,
                corpus_id=self.corpus.id,
            ).values_list("pk", flat=True)
        )

    def _corpus_listing_pks(self, user) -> set[int]:
        return set(
            AnnotationService.get_corpus_annotations(
                corpus_id=self.corpus.id,
                user=user,
            ).values_list("pk", flat=True)
        )

    def test_no_grant_hides_private_rows_in_both_listings(self):
        self.assertEqual(self._document_listing_pks(self.group_viewer), set())
        self.assertEqual(self._corpus_listing_pks(self.group_viewer), set())

    def test_group_analysis_grant_unlocks_document_listing(self):
        assign_perm("read_analysis", self.group, self.analysis)
        listed = self._document_listing_pks(self.group_viewer)
        self.assertIn(self.ann_via_analysis.pk, listed)
        self.assertNotIn(
            self.ann_via_extract.pk,
            listed,
            "analysis group grant unlocked an EXTRACT-rooted annotation — leak!",
        )

    def test_group_extract_grant_unlocks_document_listing(self):
        assign_perm("read_extract", self.group, self.extract)
        listed = self._document_listing_pks(self.group_viewer)
        self.assertIn(self.ann_via_extract.pk, listed)
        self.assertNotIn(self.ann_via_analysis.pk, listed)

    def test_group_analysis_grant_unlocks_corpus_listing(self):
        assign_perm("read_analysis", self.group, self.analysis)
        listed = self._corpus_listing_pks(self.group_viewer)
        self.assertIn(self.ann_via_analysis.pk, listed)
        self.assertNotIn(self.ann_via_extract.pk, listed)

    def test_group_extract_grant_unlocks_corpus_listing(self):
        """Corpus-listing counterpart for the extract branch."""
        assign_perm("read_extract", self.group, self.extract)
        listed = self._corpus_listing_pks(self.group_viewer)
        self.assertIn(self.ann_via_extract.pk, listed)
        self.assertNotIn(self.ann_via_analysis.pk, listed)

    def test_listing_matches_user_can_after_group_grant(self):
        """Parity: once the group grant lands, the service listing and
        ``user_can(READ)`` agree (fresh instance to sidestep the Tier-1
        instance cache)."""
        assign_perm("read_analysis", self.group, self.analysis)
        fresh = Annotation.objects.get(pk=self.ann_via_analysis.pk)
        self.assertTrue(fresh.user_can(self.group_viewer, PermissionTypes.READ))
        self.assertIn(
            self.ann_via_analysis.pk, self._document_listing_pks(self.group_viewer)
        )
