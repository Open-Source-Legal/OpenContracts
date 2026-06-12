"""Regression pins for ``created_by_*`` privacy-gate leaks (2026-06 audit).

Three leak surfaces found during the audit review rounds, all of the same
shape — a query path that skipped the analysis/extract privacy gate:

1. ``AnnotationService.get_corpus_annotations`` skipped privacy exclusion
   entirely for ANONYMOUS viewers (the old ``if not user.is_anonymous``
   guard), exposing analysis-/extract-private annotations on public
   corpora.
2. ``AnnotationService.get_label_distribution_for_corpus`` aggregated label
   names/counts over private rows for viewers who could not see the rows.
3. ``RelationshipService.get_relationship_summary`` /
   ``get_corpus_relationships`` counted/listed private relationships
   without the gate.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer
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
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _PrivacyFixtureBase(TestCase):
    """Shared fixture: public corpus/doc + plain, analysis- and
    extract-private rows."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="pgr_owner", email="pgo@pgr.test", password="x"
        )
        self.viewer = User.objects.create_user(
            username="pgr_viewer", email="pgv@pgr.test", password="x"
        )
        self.anon = AnonymousUser()

        self.corpus = Corpus.objects.create(
            title="PGR Corpus", creator=self.owner, is_public=True
        )
        self.document = Document.objects.create(
            title="PGR Doc", creator=self.owner, is_public=True
        )
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            path="pgr-doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.viewer, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.viewer, self.document, [PermissionTypes.READ]
        )

        self.plain_label = AnnotationLabel.objects.create(
            text="pgr_plain", label_type="TOKEN_LABEL", creator=self.owner
        )
        self.secret_label = AnnotationLabel.objects.create(
            text="pgr_secret", label_type="TOKEN_LABEL", creator=self.owner
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="pgr_rel", label_type="RELATIONSHIP_LABEL", creator=self.owner
        )

        self.analyzer = Analyzer.objects.create(
            id="pgr_analyzer",
            description="x",
            creator=self.owner,
            task_name="opencontractserver.tasks.noop",
        )
        # PRIVATE analysis/extract (is_public=False) owned by owner only.
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.owner,
            is_public=False,
        )
        self.fieldset = Fieldset.objects.create(name="PGR Fieldset", creator=self.owner)
        self.extract = Extract.objects.create(
            name="PGR Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )

        self.plain_ann = Annotation.objects.create(
            raw_text="plain",
            json={"x": 1},
            page=1,
            annotation_label=self.plain_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
        )
        self.ann_via_analysis = Annotation.objects.create(
            raw_text="secret-analysis",
            json={"x": 2},
            page=1,
            annotation_label=self.secret_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
        )
        self.ann_via_extract = Annotation.objects.create(
            raw_text="secret-extract",
            json={"x": 3},
            page=1,
            annotation_label=self.secret_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            created_by_extract=self.extract,
        )


class AnonymousCorpusAnnotationLeakRegressionTestCase(_PrivacyFixtureBase):
    """Leak 1: anonymous viewers of a PUBLIC corpus must not see
    analysis-/extract-private annotations via ``get_corpus_annotations``."""

    def test_anonymous_sees_only_non_private_rows(self):
        listed = set(
            AnnotationService.get_corpus_annotations(
                corpus_id=self.corpus.id, user=self.anon
            ).values_list("pk", flat=True)
        )
        self.assertIn(self.plain_ann.pk, listed)
        self.assertNotIn(
            self.ann_via_analysis.pk,
            listed,
            "anonymous saw an analysis-private annotation on a public corpus — leak!",
        )
        self.assertNotIn(
            self.ann_via_extract.pk,
            listed,
            "anonymous saw an extract-private annotation on a public corpus — leak!",
        )

    def test_authenticated_viewer_without_source_access_matches(self):
        listed = set(
            AnnotationService.get_corpus_annotations(
                corpus_id=self.corpus.id, user=self.viewer
            ).values_list("pk", flat=True)
        )
        self.assertIn(self.plain_ann.pk, listed)
        self.assertNotIn(self.ann_via_analysis.pk, listed)
        self.assertNotIn(self.ann_via_extract.pk, listed)


class LabelDistributionPrivacyRegressionTestCase(_PrivacyFixtureBase):
    """Leak 2: aggregate label names/counts must respect the privacy gate."""

    def _labels_for(self, user) -> set[str]:
        visible_doc_ids = Document.objects.filter(pk=self.document.pk).values_list(
            "id", flat=True
        )
        rows = AnnotationService.get_label_distribution_for_corpus(
            corpus=self.corpus,
            visible_doc_ids=visible_doc_ids,
            top_n=10,
            user=user,
        )
        return {row["annotation_label__text"] for row in rows}

    def test_private_labels_hidden_from_ungranted_viewer(self):
        labels = self._labels_for(self.viewer)
        self.assertIn("pgr_plain", labels)
        self.assertNotIn(
            "pgr_secret",
            labels,
            "label aggregate disclosed a private-source label name — leak!",
        )

    def test_private_labels_hidden_from_anonymous(self):
        labels = self._labels_for(self.anon)
        self.assertIn("pgr_plain", labels)
        self.assertNotIn("pgr_secret", labels)

    def test_owner_sees_private_labels(self):
        labels = self._labels_for(self.owner)
        self.assertIn("pgr_secret", labels)


class RelationshipAggregatePrivacyRegressionTestCase(_PrivacyFixtureBase):
    """Leak 3: relationship summary counts and the MCP corpus listing must
    respect the privacy gate."""

    def setUp(self):
        super().setUp()
        self.plain_rel = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
        )
        self.rel_via_analysis = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.owner,
            document=self.document,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
        )

    def test_summary_excludes_private_rows_for_ungranted_viewer(self):
        summary = RelationshipService.get_relationship_summary(
            document_id=self.document.id, corpus_id=self.corpus.id, user=self.viewer
        )
        self.assertEqual(
            summary["total"],
            1,
            "summary counted a private relationship for an ungranted viewer — leak!",
        )

    def test_summary_includes_private_rows_for_owner(self):
        summary = RelationshipService.get_relationship_summary(
            document_id=self.document.id, corpus_id=self.corpus.id, user=self.owner
        )
        self.assertEqual(summary["total"], 2)

    def test_corpus_listing_excludes_private_rows_for_ungranted_viewer(self):
        listed = set(
            RelationshipService.get_corpus_relationships(
                corpus_id=self.corpus.id, user=self.viewer
            ).values_list("pk", flat=True)
        )
        self.assertIn(self.plain_rel.pk, listed)
        self.assertNotIn(
            self.rel_via_analysis.pk,
            listed,
            "MCP corpus listing exposed a private relationship — leak!",
        )

    def test_corpus_listing_includes_private_rows_for_owner(self):
        listed = set(
            RelationshipService.get_corpus_relationships(
                corpus_id=self.corpus.id, user=self.owner
            ).values_list("pk", flat=True)
        )
        self.assertIn(self.rel_via_analysis.pk, listed)
