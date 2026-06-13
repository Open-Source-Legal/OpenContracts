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

    def test_row_creator_exempt_from_gate_in_document_listing(self):
        """The row's own creator passes the gate without source access
        (round-17 creator exemption — service listings now agree with the
        queryset gate's ``Q(creator=user)`` disjunct instead of being the
        odd surface out)."""
        own_row = Annotation.objects.create(
            raw_text="own private-rooted row",
            json={"x": 9},
            page=1,
            annotation_label=self.token_label,
            creator=self.group_viewer,  # no analysis/extract access
            document=self.document,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
        )
        self.assertIn(
            own_row.pk,
            self._document_listing_pks(self.group_viewer),
            "creator-owned privacy-rooted row vanished from the service "
            "listing despite the creator exemption",
        )
        # Other users' private rows stay hidden.
        self.assertNotIn(
            self.ann_via_analysis.pk, self._document_listing_pks(self.group_viewer)
        )

    def test_group_analysis_grant_unlocks_document_listing(self):
        assign_perm("read_analysis", self.group, self.analysis)
        listed = self._document_listing_pks(self.group_viewer)
        self.assertIn(self.ann_via_analysis.pk, listed)
        self.assertNotIn(
            self.ann_via_extract.pk,
            listed,
            "analysis group grant unlocked an EXTRACT-rooted annotation — leak!",
        )

    def test_group_analysis_grant_unlocks_annotation_queryset(self):
        """Direct manager/queryset surface uses the same group-aware gate."""
        assign_perm("read_analysis", self.group, self.analysis)
        visible = Annotation.objects.visible_to_user(self.group_viewer)

        self.assertTrue(visible.filter(pk=self.ann_via_analysis.pk).exists())
        self.assertFalse(visible.filter(pk=self.ann_via_extract.pk).exists())

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

    def test_gate_matches_queryset_visibility_for_non_creator(self):
        """Scoped parity pin for the documented sync contract between
        ``apply_source_privacy_gate`` (the services' exclude shape) and the
        positive-Q privacy gate inside ``AnnotationQuerySet.visible_to_user``.

        Since review round 17 the gate carries the same authenticated
        creator exemption as the queryset disjunct, so the two LIST shapes
        agree for creators too (pinned separately by
        ``test_row_creator_exempt_from_gate_in_document_listing`` and
        ``test_annotation_creator_source_private_row_has_filter_check_parity``).
        This test keeps its non-creator scope to stay focused on the
        grant-driven transitions: for non-creators holding doc+corpus READ,
        queryset membership reduces to the privacy verdict — the two shapes
        must agree exactly, before and after a source grant lands.
        """
        from opencontractserver.utils.source_visibility import (
            apply_source_privacy_gate,
        )

        def gate_verdict(user, ann) -> bool:
            return apply_source_privacy_gate(
                Annotation.objects.filter(pk=ann.pk), user
            ).exists()

        def queryset_verdict(user, ann) -> bool:
            return Annotation.objects.visible_to_user(user).filter(pk=ann.pk).exists()

        private_rows = [self.ann_via_analysis, self.ann_via_extract]

        # Before any source grant: both shapes deny both private rows.
        for ann in private_rows:
            self.assertEqual(
                gate_verdict(self.group_viewer, ann),
                queryset_verdict(self.group_viewer, ann),
                f"shapes disagree pre-grant for pk={ann.pk}",
            )
            self.assertFalse(gate_verdict(self.group_viewer, ann))

        # After a group analysis grant: shapes agree row-by-row — the
        # analysis row unlocks, the extract row stays hidden.
        assign_perm("read_analysis", self.group, self.analysis)
        for ann in private_rows:
            self.assertEqual(
                gate_verdict(self.group_viewer, ann),
                queryset_verdict(self.group_viewer, ann),
                f"shapes disagree post-grant for pk={ann.pk}",
            )
        self.assertTrue(gate_verdict(self.group_viewer, self.ann_via_analysis))
        self.assertFalse(gate_verdict(self.group_viewer, self.ann_via_extract))

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
