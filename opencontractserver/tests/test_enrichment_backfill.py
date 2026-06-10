"""Tests for the authority-backfill workflow.

Covers the three production gaps around authority corpora:

* the wanted-authorities queue (``CorpusReferenceService.wanted_authorities``
  + the ``wantedAuthorities`` GraphQL query),
* the reactive re-link (``EnrichmentService.relink_corpora_for_keys``), and
* the bootstrap entry points (``bootstrap_authority_corpus`` composite +
  the ``bootstrap_authority`` management command).
"""

import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthoritySection,
    bootstrap_authority_corpus,
)
from opencontractserver.enrichment.services import (
    CorpusReferenceService,
    EnrichmentService,
)

User = get_user_model()

FILING_TEXT = (
    "We are governed by Section 203 of the Delaware General Corporation Law. "
    "Indemnification is provided per Section 145 of the Delaware General "
    "Corporation Law. The offering relies on Section 4(a)(2) of the "
    "Securities Act."
)

DGCL_SECTIONS = [
    AuthoritySection(key="dgcl:145", heading="DGCL § 145", text="..145.."),
    AuthoritySection(key="dgcl:203", heading="DGCL § 203", text="..203.."),
]


def _make_filing_corpus(user, title="S-1 Corpus"):
    corpus = Corpus.objects.create(title=title, creator=user)
    doc = Document.objects.create(title=f"{title} primary", creator=user)
    doc.txt_extract_file.save("s1.txt", ContentFile(FILING_TEXT.encode("utf-8")))
    corpus.add_document(document=doc, user=user)
    return corpus


class _GQLContext:
    def __init__(self, user):
        self.user = user


class WantedAuthoritiesServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = _make_filing_corpus(self.user)
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

    def test_aggregates_external_law_refs_by_authority(self):
        wanted = CorpusReferenceService.wanted_authorities(self.user)
        by_auth = {w["authority"]: w for w in wanted}
        assert set(by_auth) == {"dgcl", "securities-act"}
        dgcl = by_auth["dgcl"]
        assert dgcl["mention_count"] == 2
        assert dgcl["key_count"] == 2  # dgcl:145, dgcl:203
        assert dgcl["corpus_count"] == 1
        top = {k["canonical_key"] for k in dgcl["top_keys"]}
        assert top == {"dgcl:145", "dgcl:203"}
        # Sorted by mention volume — dgcl (2) outranks securities-act (1).
        assert wanted[0]["authority"] == "dgcl"

    def test_subsection_keys_roll_up_to_section_root(self):
        # "securities-act:4(a)(2)" rolls up to "securities-act:4" — the unit
        # the bootstrapper materialises (one document per SECTION).
        wanted = CorpusReferenceService.wanted_authorities(self.user)
        sa = next(w for w in wanted if w["authority"] == "securities-act")
        assert [k["canonical_key"] for k in sa["top_keys"]] == ["securities-act:4"]

    def test_corpus_scope_filter(self):
        other = _make_filing_corpus(self.user, title="Other S-1")
        EnrichmentService().apply(corpus_id=other.id, creator_id=self.user.id)

        global_wanted = CorpusReferenceService.wanted_authorities(self.user)
        dgcl_global = next(w for w in global_wanted if w["authority"] == "dgcl")
        assert dgcl_global["mention_count"] == 4
        assert dgcl_global["corpus_count"] == 2

        scoped = CorpusReferenceService.wanted_authorities(
            self.user, corpus_id=self.corpus.id
        )
        dgcl_scoped = next(w for w in scoped if w["authority"] == "dgcl")
        assert dgcl_scoped["mention_count"] == 2
        assert dgcl_scoped["corpus_count"] == 1

    def test_visibility_scoped(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        assert CorpusReferenceService.wanted_authorities(stranger) == []

    def test_resolved_refs_drop_off_the_queue(self):
        bootstrap_authority_corpus(
            creator_id=self.user.id,
            corpus_title="Delaware General Corporation Law",
            sections=DGCL_SECTIONS,
        )
        wanted = CorpusReferenceService.wanted_authorities(self.user)
        assert {w["authority"] for w in wanted} == {"securities-act"}


class RelinkForKeysTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="p")
        self.corpus = _make_filing_corpus(self.owner)
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.owner.id)

    def _bootstrap_dgcl(self, user, public=False):
        out = bootstrap_authority_corpus(
            creator_id=user.id,
            corpus_title="Delaware General Corporation Law",
            sections=DGCL_SECTIONS,
            make_public=public,
            relink=False,  # exercise relink_corpora_for_keys directly
        )
        return out

    def test_relink_upgrades_matching_corpora(self):
        librarian = User.objects.create_user(username="librarian", password="p")
        self._bootstrap_dgcl(librarian, public=True)

        out = EnrichmentService().relink_corpora_for_keys(["dgcl:145", "dgcl:203"])
        assert out["corpora_relinked"] == 1
        assert out["law_references_linked"] == 2

        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED

    def test_relink_runs_as_each_corpus_creator_no_private_leak(self):
        """A PRIVATE authority must not resolve other users' corpora: the
        relink runs under each filing corpus creator's visibility."""
        librarian = User.objects.create_user(username="librarian", password="p")
        self._bootstrap_dgcl(librarian, public=False)

        out = EnrichmentService().relink_corpora_for_keys(["dgcl:145", "dgcl:203"])
        assert out["law_references_linked"] == 0
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_EXTERNAL

    def test_relink_ignores_unrelated_keys(self):
        out = EnrichmentService().relink_corpora_for_keys(["irc:501"])
        assert out["corpora_checked"] == 0
        assert out["law_references_linked"] == 0

    def test_subsection_refs_match_their_root_key(self):
        # Filing cites securities-act:4(a)(2); the authority lands the root
        # section securities-act:4 — the relink must still pick the corpus up.
        librarian = User.objects.create_user(username="librarian2", password="p")
        bootstrap_authority_corpus(
            creator_id=librarian.id,
            corpus_title="Securities Act",
            sections=[
                AuthoritySection(
                    key="securities-act:4", heading="Securities Act § 4", text=".."
                )
            ],
            make_public=True,
            relink=False,
        )
        out = EnrichmentService().relink_corpora_for_keys(["securities-act:4"])
        assert out["law_references_linked"] == 1
        ref = CorpusReference.objects.get(
            corpus=self.corpus, canonical_key="securities-act:4(a)(2)"
        )
        assert ref.resolution_status == C.STATUS_RESOLVED


class BootstrapCompositeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="p")
        self.corpus = _make_filing_corpus(self.owner)
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.owner.id)

    def test_bootstrap_relinks_filings_by_default(self):
        out = bootstrap_authority_corpus(
            creator_id=self.owner.id,
            corpus_title="Delaware General Corporation Law",
            sections=DGCL_SECTIONS,
        )
        assert out["documents_created"] == 2
        assert out["relink"]["law_references_linked"] == 2
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED

    def test_bootstrap_no_relink_leaves_refs_external(self):
        out = bootstrap_authority_corpus(
            creator_id=self.owner.id,
            corpus_title="Delaware General Corporation Law",
            sections=DGCL_SECTIONS,
            relink=False,
        )
        assert "relink" not in out
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_EXTERNAL

    def test_bootstrap_make_public_publishes_corpus(self):
        out = bootstrap_authority_corpus(
            creator_id=self.owner.id,
            corpus_title="Delaware General Corporation Law",
            sections=DGCL_SECTIONS,
            make_public=True,
            relink=False,
        )
        corpus = Corpus.objects.get(pk=out["corpus_id"])
        assert corpus.is_public is True


class BootstrapCommandTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="p")
        self.corpus = _make_filing_corpus(self.owner)
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.owner.id)

    def _spec_file(self, spec: dict) -> str:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(spec, f)
        f.close()
        return f.name

    def test_command_bootstraps_publishes_and_relinks(self):
        path = self._spec_file(
            {
                "aliases": ["Delaware General Corporation Law"],
                "sections": [
                    {"key": "dgcl:145", "heading": "DGCL § 145", "text": "..145.."},
                    {"key": "dgcl:203", "heading": "DGCL § 203", "text": "..203.."},
                ],
            }
        )
        call_command(
            "bootstrap_authority",
            "--creator",
            "owner",
            "--title",
            "Delaware General Corporation Law",
            "--file",
            path,
            "--public",
        )
        auth = Corpus.objects.get(title="Delaware General Corporation Law")
        assert auth.is_public is True
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        assert ref.resolution_status == C.STATUS_RESOLVED

    def test_command_rejects_malformed_sections(self):
        from django.core.management.base import CommandError

        path = self._spec_file({"sections": [{"heading": "no key", "text": "x"}]})
        with self.assertRaises(CommandError):
            call_command(
                "bootstrap_authority",
                "--creator",
                "owner",
                "--title",
                "Broken",
                "--file",
                path,
            )


class WantedAuthoritiesGraphQLTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.corpus = _make_filing_corpus(self.user)
        EnrichmentService().apply(corpus_id=self.corpus.id, creator_id=self.user.id)

    def _execute(self, user, variables=None):
        client = Client(schema)
        return client.execute(
            self.QUERY, variable_values=variables, context_value=_GQLContext(user)
        )

    QUERY = """
        query Wanted($corpusId: ID) {
          wantedAuthorities(corpusId: $corpusId) {
            authority
            mentionCount
            keyCount
            corpusCount
            topKeys { canonicalKey mentionCount corpusCount }
          }
        }
    """

    def test_returns_wanted_authorities(self):
        result = self._execute(self.user)
        assert "errors" not in result
        rows = result["data"]["wantedAuthorities"]
        assert rows[0]["authority"] == "dgcl"
        assert rows[0]["mentionCount"] == 2
        assert {k["canonicalKey"] for k in rows[0]["topKeys"]} == {
            "dgcl:145",
            "dgcl:203",
        }

    def test_malformed_corpus_id_returns_empty_no_error(self):
        result = self._execute(self.user, {"corpusId": "not-a-relay-id"})
        assert "errors" not in result
        assert result["data"]["wantedAuthorities"] == []

    def test_visibility_scoped(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        result = self._execute(stranger)
        assert "errors" not in result
        assert result["data"]["wantedAuthorities"] == []
