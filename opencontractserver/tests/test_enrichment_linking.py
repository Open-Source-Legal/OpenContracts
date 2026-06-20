"""Tests for the cross-corpus resolution pass (EXTERNAL law refs -> RESOLVED)."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis
from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
)
from opencontractserver.enrichment.services import EnrichmentService
from opencontractserver.types.enums import JobStatus

User = get_user_model()

S1_TEXT = (
    "We are governed by Section 203 of the Delaware General Corporation Law. "
    "Indemnification is provided per Section 145 of the Delaware General "
    "Corporation Law. The offering relies on Section 4(a)(2) of the "
    "Securities Act."
)


class CrossCorpusLinkingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = Corpus.objects.create(title="S-1 Corpus", creator=self.user)
        doc = Document.objects.create(title="Acme S-1 primary", creator=self.user)
        doc.txt_extract_file.save("s1.txt", ContentFile(S1_TEXT.encode("utf-8")))
        self.corpus.add_document(document=doc, user=self.user)

    def _bootstrap_dgcl(self, user=None):
        return AuthorityCorpusBootstrapper().bootstrap(
            creator_id=(user or self.user).id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                AuthoritySection(key="dgcl:145", heading="DGCL § 145", text="..145.."),
                AuthoritySection(key="dgcl:203", heading="DGCL § 203", text="..203.."),
            ],
        )

    def test_link_upgrades_external_law_refs(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap_dgcl()

        out = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 2

        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_corpus_id == auth["corpus_id"]
        assert ref.target_document is not None
        # Canonical in-app document path INTO THE AUTHORITY CORPUS (the slug
        # shape the frontend router serves: /d/:userIdent/:corpusIdent/:docIdent).
        auth_corpus = Corpus.objects.select_related("creator").get(pk=auth["corpus_id"])
        assert ref.source_annotation.link_url == (
            f"/d/{auth_corpus.creator.slug}/{auth_corpus.slug}"
            f"/{ref.target_document.slug}"
        )
        # No DGCL doc for the Securities Act citation -> still external.
        sa = CorpusReference.objects.get(
            corpus=self.corpus, canonical_key="securities-act:4(a)(2)"
        )
        assert sa.resolution_status == C.STATUS_EXTERNAL
        assert sa.target_document is None

    def test_apply_links_automatically_when_authority_exists(self):
        self._bootstrap_dgcl()
        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 2

    def test_link_pass_repairs_stale_link_urls(self):
        """``link_url`` is a cached projection of the resolved target's slug
        path — slug drift (corpus rename) must be repaired by the next
        linking pass, not 404 forever."""
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap_dgcl()
        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )

        auth_corpus = Corpus.objects.select_related("creator").get(pk=auth["corpus_id"])
        auth_corpus.slug = "renamed-dgcl"
        auth_corpus.save()

        out = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["links_restamped"] >= 2  # dgcl:145 and dgcl:203 mentions

        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.target_document is not None
        assert ref.source_annotation.link_url == (
            f"/d/{auth_corpus.creator.slug}/renamed-dgcl/{ref.target_document.slug}"
        )

    def test_link_is_idempotent(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        self._bootstrap_dgcl()
        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        again = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert again["law_references_linked"] == 0

    def test_self_referential_statute_corpus_links_internally(self):
        """Enrichment ON an authority corpus: '§ X of this title' citations in
        statute text resolve to sibling sections of the same corpus."""
        auth = AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=[
                AuthoritySection(
                    key="dgcl:251",
                    heading="DGCL § 251",
                    text=(
                        "Any 2 or more corporations may merge into a single "
                        "corporation. Notice shall be given as provided in "
                        "§ 222 of this title."
                    ),
                ),
                AuthoritySection(
                    key="dgcl:222",
                    heading="DGCL § 222",
                    text="Whenever stockholders are required to take action...",
                ),
            ],
        )

        out = EnrichmentService().apply(
            corpus_id=auth["corpus_id"], creator_id=self.user.id
        )
        assert out["law_references_linked"] == 1

        ref = CorpusReference.objects.get(
            corpus_id=auth["corpus_id"], canonical_key="dgcl:222"
        )
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_corpus_id == auth["corpus_id"]
        assert ref.target_document is not None
        assert (ref.target_document.custom_meta or {})["canonical_key"] == "dgcl:222"
        assert (ref.normalized_data or {})["relative"] is True

    def test_link_raises_doesnotexist_for_missing_and_invisible_corpus(self):
        # Visibility-scoped corpus fetch: a nonexistent corpus and a corpus
        # the caller cannot see raise the SAME ``Corpus.DoesNotExist`` — no
        # existence oracle for callers passing arbitrary PKs.
        stranger = User.objects.create_user(username="stranger", password="p")

        with self.assertRaises(Corpus.DoesNotExist):
            EnrichmentService().link_external_references(
                corpus_id=999_999, creator_id=self.user.id
            )
        with self.assertRaises(Corpus.DoesNotExist):
            EnrichmentService().link_external_references(
                corpus_id=self.corpus.id, creator_id=stranger.id
            )

    def test_bootstrap_raises_doesnotexist_for_invisible_corpus_id(self):
        # Same visibility-scoped semantics for the bootstrapper's explicit
        # ``corpus_id`` path.
        stranger = User.objects.create_user(username="stranger2", password="p")
        with self.assertRaises(Corpus.DoesNotExist):
            AuthorityCorpusBootstrapper().bootstrap(
                creator_id=stranger.id,
                corpus_title="ignored",
                sections=[],
                corpus_id=self.corpus.id,
            )

    def test_link_respects_authority_visibility(self):
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        other = User.objects.create_user(username="other", password="p")
        self._bootstrap_dgcl(user=other)  # private to `other`

        out = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 0
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_EXTERNAL

    def test_public_corpus_demotes_owner_only_visible_authority(self):
        """Audience floor: a public source corpus resolves under the ANONYMOUS
        audience (``audience = None``), so a private authority the *owner* can
        see must NOT stay linked — anonymous visitors would hit a broken link.

        Exercises the ``audience = None if corpus.is_public else user`` branch
        and confirms ``find_authority_target(key, None)`` runs through
        ``visible_to_user(None)`` without raising.
        """
        # Private source corpus + private authority owned by the same user: the
        # owner is the audience, so the citation resolves.
        self._bootstrap_dgcl()  # make_public defaults to False
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED

        # Publish the source corpus -> audience floor drops to anonymous -> the
        # private authority is no longer audience-visible -> the ref demotes so
        # the public corpus never renders a broken link.
        self.corpus.is_public = True
        self.corpus.save()
        out = EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["links_demoted"] >= 1
        ref.refresh_from_db()
        assert ref.resolution_status == C.STATUS_EXTERNAL
        assert ref.target_document_id is None
        # The mention stops rendering as a clickable link (restamp clears it).
        assert ref.source_annotation.link_url is None

    def test_public_corpus_links_public_authority(self):
        """The flip side of the audience floor: a *public* authority IS visible
        to the anonymous audience, so a public source corpus resolves its
        citation against it."""
        self.corpus.is_public = True
        self.corpus.save()
        auth = self._bootstrap_dgcl()
        # Publish the authority the production way (``Corpus.save`` propagates
        # is_public to its documents) so it is visible to the anonymous floor.
        auth_corpus = Corpus.objects.get(pk=auth["corpus_id"])
        auth_corpus.is_public = True
        auth_corpus.save(update_fields=["is_public", "modified"])

        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 2
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED
        assert ref.target_document is not None

    # -- #1996 regressions -------------------------------------------------- #

    @staticmethod
    def _mirror_path(document, corpus, user, path):
        """Give ``document`` an additional current path in ``corpus``.

        Authority documents can have current paths in more than one corpus;
        ``add_document`` makes corpus-isolated copies, so the multi-corpus state
        is materialised directly via the path record (the shape #1996 hits).
        """
        return DocumentPath.objects.create(
            document=document,
            corpus=corpus,
            path=path,
            version_number=1,
            parent=None,
            is_current=True,
            is_deleted=False,
            creator=user,
        )

    def test_apply_marks_analysis_failed_when_linking_raises(self):
        """Provenance integrity (#1996): when ``_link_external`` raises, the
        Analysis must end FAILED — not stranded COMPLETED with
        ``law_references_linked=0``. Linking now runs inside ``apply()``'s
        try/except, after ``writer.write`` and before the COMPLETED stamp.
        """
        with mock.patch.object(
            EnrichmentService, "_link_external", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                EnrichmentService().apply(
                    corpus_id=self.corpus.id, creator_id=self.user.id
                )

        analysis = (
            Analysis.objects.filter(analyzed_corpus=self.corpus).order_by("-id").first()
        )
        assert analysis is not None
        assert analysis.status == JobStatus.FAILED.value

    def test_link_target_corpus_is_deterministic_for_multi_corpus_authority(self):
        """A target reachable from >1 corpus must yield a STABLE
        ``target_corpus_id`` — the lowest corpus_id — not whatever row Postgres
        returned last from a bare ``dict(values_list(...))`` (#1996).
        """
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)
        auth = self._bootstrap_dgcl()
        auth_doc = Document.objects.get(custom_meta__canonical_key="dgcl:145")

        # Same authority document, second current path in another visible corpus.
        second = Corpus.objects.create(title="Mirror DGCL", creator=self.user)
        self._mirror_path(auth_doc, second, self.user, "/documents/dgcl-145-mirror")

        EnrichmentService().link_external_references(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED
        # Deterministic tie-break: lowest corpus_id among the target's corpora.
        assert ref.target_corpus_id == min(auth["corpus_id"], second.id)

    def test_link_target_corpus_prefers_audience_visible_corpus(self):
        """Navigability (#1996): a target reachable from several corpora links
        into one the citing corpus's audience can actually open. For a public
        citing corpus the audience floor is anonymous, so a private mirror is
        skipped in favour of the public authority corpus — even when the private
        mirror has the LOWER corpus_id (so the choice is driven by visibility,
        not merely the lowest id).
        """
        # Private mirror created FIRST -> it gets the lower corpus_id.
        private_mirror = Corpus.objects.create(
            title="Private mirror", creator=self.user
        )

        # Public citing corpus -> audience floor is anonymous.
        self.corpus.is_public = True
        self.corpus.save()

        auth = self._bootstrap_dgcl()  # auth corpus gets the HIGHER id
        auth_corpus = Corpus.objects.select_related("creator").get(pk=auth["corpus_id"])
        # Publish the authority the production way (propagates is_public to its
        # documents) so the target is visible to the anonymous floor.
        auth_corpus.is_public = True
        auth_corpus.save(update_fields=["is_public", "modified"])
        auth_doc = Document.objects.get(custom_meta__canonical_key="dgcl:145")

        self._mirror_path(
            auth_doc, private_mirror, self.user, "/documents/dgcl-145-private"
        )
        assert private_mirror.id < auth_corpus.id  # guards the test's premise

        out = EnrichmentService().apply(
            corpus_id=self.corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] >= 1
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED
        # The navigable (public) corpus wins over the lower-id private mirror.
        assert ref.target_corpus_id == auth_corpus.id
        assert ref.target_corpus_id != private_mirror.id
        # …and the rendered mention link points into the public authority corpus.
        assert ref.source_annotation.link_url == (
            f"/d/{auth_corpus.creator.slug}/{auth_corpus.slug}"
            f"/{ref.target_document.slug}"
        )
