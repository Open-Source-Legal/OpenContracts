"""Regression tests for the de-joined annotation visibility predicate (#1906).

Tier 3 of #1908 rewrote ``AnnotationQuerySet.visible_to_user`` to use correlated
``EXISTS`` subqueries instead of the ``structural_set__documents`` reverse-FK
join, dropping the trailing ``.distinct()``. These tests pin the two properties
that change buys, in addition to the row-set equivalence already pinned by
``permissioning/test_authorization_invariants.py``:

  * the compiled queryset no longer sets the ``DISTINCT`` flag for any user
    class (anonymous / creator / stranger), and
  * a structural annotation shared by N documents appears **exactly once** in
    ``visible_to_user`` — the old reverse-FK join fanned it out to N rows, which
    is the only reason the predicate previously needed ``.distinct()``.

It also re-pins the structural-set visibility semantics ("visible iff ANY
document in the set is visible to the user") so the EXISTS rewrite cannot
silently widen or narrow them.
"""

import hashlib
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    StructuralAnnotationSet,
)
from opencontractserver.documents.models import Document

User = get_user_model()


def _new_set(creator) -> StructuralAnnotationSet:
    return StructuralAnnotationSet.objects.create(
        content_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        parser_name="TestParser",
        creator=creator,
    )


class AnnotationVisibilityDejoinTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="dejoin_owner", password="pw")
        cls.stranger = User.objects.create_user(
            username="dejoin_stranger", password="pw"
        )
        cls.anon = AnonymousUser()
        cls.label = AnnotationLabel.objects.create(text="L", creator=cls.owner)

    # ------------------------------------------------------------------
    # No DISTINCT
    # ------------------------------------------------------------------
    def test_visible_to_user_does_not_set_distinct_flag(self):
        """The de-joined predicate must never set the queryset DISTINCT flag.

        This is the exact regression guard for the trailing ``.distinct()``
        that #1906 removed — it is what knocked the un-scoped browse COUNT and
        ``-modified`` page off any single index.
        """
        for user in (self.owner, self.stranger, self.anon):
            qs = Annotation.objects.visible_to_user(user)
            self.assertFalse(
                qs.query.distinct,
                f"visible_to_user set DISTINCT for "
                f"{getattr(user, 'username', 'anon')} — re-introduces the "
                f"index-blocking dedup #1906 removed",
            )

    # ------------------------------------------------------------------
    # No row fan-out for shared structural sets
    # ------------------------------------------------------------------
    def test_structural_set_annotation_not_duplicated_across_documents(self):
        """A structural annotation shared by N documents appears exactly once.

        The old ``structural_set__documents`` join produced one row per matching
        document (and relied on ``.distinct()`` to collapse them). The EXISTS
        rewrite must return the annotation a single time without DISTINCT.
        """
        sset = _new_set(self.owner)
        # Three PUBLIC documents all referencing the same structural set.
        for i in range(3):
            Document.objects.create(
                title=f"Shared Doc {i}",
                creator=self.owner,
                is_public=True,
                structural_annotation_set=sset,
            )
        structural_ann = Annotation.objects.create(
            raw_text="shared structural",
            structural_set=sset,
            structural=True,
            creator=self.owner,
        )

        # Public docs ⇒ every user class can see the annotation; each must see
        # it EXACTLY once (a fan-out would yield 3 rows).
        for user in (self.owner, self.stranger, self.anon):
            pks = list(
                Annotation.objects.visible_to_user(user)
                .filter(pk=structural_ann.pk)
                .values_list("pk", flat=True)
            )
            self.assertEqual(
                pks,
                [structural_ann.pk],
                f"structural annotation duplicated for "
                f"{getattr(user, 'username', 'anon')}: saw {pks}",
            )

    # ------------------------------------------------------------------
    # Structural-set visibility follows ANY visible document
    # ------------------------------------------------------------------
    def test_structural_set_visible_only_when_a_document_is_visible(self):
        """Structural-set annotation visibility tracks document visibility.

        Visible iff at least one document referencing the set is visible to the
        user — the semantics the EXISTS subquery must preserve.
        """
        sset = _new_set(self.owner)
        # A single PRIVATE document owned by ``owner``.
        Document.objects.create(
            title="Private Shared Doc",
            creator=self.owner,
            is_public=False,
            structural_annotation_set=sset,
        )
        ann = Annotation.objects.create(
            raw_text="private structural",
            structural_set=sset,
            structural=True,
            creator=self.owner,
        )

        # Owner sees it (creator of the only — private — document in the set).
        self.assertTrue(
            Annotation.objects.visible_to_user(self.owner).filter(pk=ann.pk).exists()
        )
        # Stranger and anonymous cannot — no visible document references the set.
        self.assertFalse(
            Annotation.objects.visible_to_user(self.stranger).filter(pk=ann.pk).exists()
        )
        self.assertFalse(
            Annotation.objects.visible_to_user(self.anon).filter(pk=ann.pk).exists()
        )

        # Add a PUBLIC document to the same set — now everyone can see the
        # annotation (still exactly once).
        Document.objects.create(
            title="Public Shared Doc",
            creator=self.owner,
            is_public=True,
            structural_annotation_set=sset,
        )
        for user in (self.stranger, self.anon):
            pks = list(
                Annotation.objects.visible_to_user(user)
                .filter(pk=ann.pk)
                .values_list("pk", flat=True)
            )
            self.assertEqual(
                pks,
                [ann.pk],
                f"after adding a public doc, {getattr(user, 'username', 'anon')} "
                f"should see the structural annotation exactly once: saw {pks}",
            )

    # ------------------------------------------------------------------
    # Document-attached behaviour unchanged
    # ------------------------------------------------------------------
    def test_document_attached_visibility_unchanged(self):
        """Sanity: document-attached privacy is preserved by the rewrite."""
        public_doc = Document.objects.create(
            title="Pub", creator=self.owner, is_public=True
        )
        private_doc = Document.objects.create(
            title="Priv", creator=self.owner, is_public=False
        )
        public_ann = Annotation.objects.create(
            raw_text="pub ann",
            document=public_doc,
            annotation_label=self.label,
            creator=self.owner,
            is_public=True,
        )
        private_ann = Annotation.objects.create(
            raw_text="priv ann",
            document=private_doc,
            annotation_label=self.label,
            creator=self.owner,
            is_public=False,
        )

        owner_qs = Annotation.objects.visible_to_user(self.owner)
        self.assertIn(public_ann, owner_qs)
        self.assertIn(private_ann, owner_qs)

        stranger_qs = Annotation.objects.visible_to_user(self.stranger)
        # Public doc ⇒ the (non-structural) annotation is visible to a stranger.
        self.assertIn(public_ann, stranger_qs)
        # Private doc owned by someone else ⇒ invisible.
        self.assertNotIn(private_ann, stranger_qs)

    # ------------------------------------------------------------------
    # Corpus visibility gates the authenticated-user branch
    # ------------------------------------------------------------------
    def test_corpus_visibility_gates_authenticated_user(self):
        """A corpus-scoped annotation is hidden when its corpus is private.

        Pins the authenticated-user corpus ``EXISTS`` subquery (#1906): the
        rewrite swapped the ``corpus__*`` join for a correlated ``EXISTS`` over
        ``Corpus``. Even when the attached document is public, the annotation
        must stay hidden from a stranger while its corpus is private, and
        appear once the corpus is published — otherwise the new subquery would
        silently leak (or hide) corpus-scoped annotations. The document is kept
        public throughout so the only variable under test is corpus visibility.
        """
        from opencontractserver.corpuses.models import Corpus

        public_doc = Document.objects.create(
            title="Corpus Doc", creator=self.owner, is_public=True
        )
        private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        ann = Annotation.objects.create(
            raw_text="corpus-scoped ann",
            document=public_doc,
            corpus=private_corpus,
            annotation_label=self.label,
            creator=self.owner,
        )

        # Owner sees it — creator of the (private) corpus.
        self.assertIn(ann, Annotation.objects.visible_to_user(self.owner))
        # Stranger cannot: the document is public but the corpus is private and
        # not theirs, so the corpus EXISTS subquery excludes the row.
        self.assertNotIn(ann, Annotation.objects.visible_to_user(self.stranger))

        # Publish the corpus — the stranger now clears the corpus EXISTS gate
        # and sees the annotation exactly once (no fan-out, no DISTINCT).
        private_corpus.is_public = True
        private_corpus.save()
        stranger_pks = list(
            Annotation.objects.visible_to_user(self.stranger)
            .filter(pk=ann.pk)
            .values_list("pk", flat=True)
        )
        self.assertEqual(
            stranger_pks,
            [ann.pk],
            f"after publishing the corpus the stranger should see the "
            f"corpus-scoped annotation exactly once: saw {stranger_pks}",
        )
