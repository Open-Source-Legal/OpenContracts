"""Tests for the authority corpus bootstrapper (statute reference targets)."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment.authorities import (
    AuthorityCorpusBootstrapper,
    AuthoritySection,
    authority_alias_registry,
    candidate_keys,
    find_authority_target,
)
from opencontractserver.utils.files import read_field_file_text

User = get_user_model()

DGCL_145_TEXT = (
    "(a) A corporation shall have power to indemnify any person who was or is "
    "a party to any action by reason of the fact that the person is or was a "
    "director, officer, employee or agent of the corporation."
)
DGCL_122_TEXT = (
    "Every corporation created under this chapter shall have power to ... "
    "(17) renounce, in its certificate of incorporation or by action of its "
    "board of directors, any interest in specified business opportunities."
)


def _bootstrap(user, sections):
    return AuthorityCorpusBootstrapper().bootstrap(
        creator_id=user.id,
        corpus_title="Delaware General Corporation Law",
        sections=sections,
    )


class AuthorityBootstrapTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        self.sections = [
            AuthoritySection(
                key="dgcl:145",
                heading="DGCL § 145 — Indemnification of officers and directors",
                text=DGCL_145_TEXT,
                source_url="https://delcode.delaware.gov/title8/c001/sc04/#145",
            ),
            AuthoritySection(
                key="dgcl:122",
                heading="DGCL § 122 — Specific powers",
                text=DGCL_122_TEXT,
            ),
        ]

    def test_bootstrap_creates_corpus_and_keyed_documents(self):
        out = _bootstrap(self.user, self.sections)
        assert out["corpus_created"] is True
        assert out["documents_created"] == 2

        doc = Document.objects.get(custom_meta__canonical_key="dgcl:145")
        assert doc.custom_meta["authority"] == "dgcl"
        assert doc.custom_meta["source_url"].endswith("#145")
        assert read_field_file_text(doc.txt_extract_file) == DGCL_145_TEXT
        corpus = Corpus.objects.get(pk=out["corpus_id"])
        assert corpus.title == "Delaware General Corporation Law"

    def test_bootstrap_is_idempotent(self):
        _bootstrap(self.user, self.sections)
        doc_count = Document.objects.count()

        out = _bootstrap(self.user, self.sections)
        assert out["corpus_created"] is False
        assert out["documents_created"] == 0
        assert out["documents_updated"] == 0
        assert out["documents_skipped"] == 2
        assert Document.objects.count() == doc_count

    def test_bootstrap_restamps_clobbered_custom_meta(self):
        """A concurrent pipeline save can wipe custom_meta; re-run must heal it.

        The document is still recognised by title, restamped in place — no new
        document or version is created.
        """
        _bootstrap(self.user, self.sections)
        doc = Document.objects.get(custom_meta__canonical_key="dgcl:145")
        doc.custom_meta = {}
        doc.save(update_fields=["custom_meta"])
        doc_count = Document.objects.count()

        out = _bootstrap(self.user, self.sections)
        assert out["documents_restamped"] == 1
        assert out["documents_created"] == 0
        assert out["documents_updated"] == 0
        assert Document.objects.count() == doc_count
        doc.refresh_from_db()
        assert doc.custom_meta["canonical_key"] == "dgcl:145"

    def test_bootstrap_versions_up_changed_text(self):
        _bootstrap(self.user, self.sections)
        amended = DGCL_145_TEXT + " [As amended.]"
        out = _bootstrap(
            self.user,
            [
                AuthoritySection(
                    key="dgcl:145",
                    heading="DGCL § 145 — Indemnification of officers and directors",
                    text=amended,
                )
            ],
        )
        assert out["documents_updated"] == 1
        assert out["documents_created"] == 0

        user_target = find_authority_target("dgcl:145", self.user)
        assert user_target is not None
        assert read_field_file_text(user_target.txt_extract_file) == amended


class AuthorityAliasRegistryTests(TestCase):
    """Adding a body of law = bootstrapping a corpus with aliases — no code."""

    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        AuthorityCorpusBootstrapper().bootstrap(
            creator_id=self.user.id,
            corpus_title="New York Business Corporation Law",
            aliases=["New York Business Corporation Law", "NYBCL"],
            sections=[
                AuthoritySection(
                    key="nybcl:912",
                    heading="NYBCL § 912 — Requirements relating to certain business combinations",
                    text="(a) Definitions... business combination with an interested shareholder.",
                )
            ],
        )

    def test_registry_merges_db_aliases_with_static_defaults(self):
        registry = authority_alias_registry(self.user)
        assert registry["nybcl"] == "nybcl"
        assert registry["new york business corporation law"] == "nybcl"
        # Static defaults still present.
        assert registry["dgcl"] == "dgcl"

    def test_registry_respects_visibility(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        registry = authority_alias_registry(stranger)
        assert "nybcl" not in registry

    def test_new_authority_extracted_and_linked_end_to_end(self):
        """A filing citing the DB-declared authority resolves with zero code."""
        from opencontractserver.annotations.models import CorpusReference
        from opencontractserver.enrichment.services import EnrichmentService

        filing_corpus = Corpus.objects.create(title="NY Filings", creator=self.user)
        doc = Document.objects.create(title="Acme merger proxy", creator=self.user)
        doc.txt_extract_file.save(
            "proxy.txt",
            ContentFile(
                b"We are subject to Section 912 of the New York Business "
                b"Corporation Law as an interested shareholder."
            ),
        )
        filing_corpus.add_document(document=doc, user=self.user)

        out = EnrichmentService().apply(
            corpus_id=filing_corpus.id, creator_id=self.user.id
        )
        assert out["law_references_linked"] == 1

        ref = CorpusReference.objects.get(
            corpus=filing_corpus, canonical_key="nybcl:912"
        )
        assert ref.target_document is not None
        assert (ref.target_document.custom_meta or {})["canonical_key"] == "nybcl:912"


class FindAuthorityTargetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="owner", password="p")
        _bootstrap(
            self.user,
            [
                AuthoritySection(
                    key="dgcl:122", heading="DGCL § 122", text=DGCL_122_TEXT
                )
            ],
        )

    def test_candidate_keys_fall_back_to_section_root(self):
        assert candidate_keys("dgcl:122(17)") == ["dgcl:122(17)", "dgcl:122"]
        assert candidate_keys("securities-act:7(a)(2)(b)") == [
            "securities-act:7(a)(2)(b)",
            "securities-act:7",
        ]
        assert candidate_keys("dgcl:145") == ["dgcl:145"]

    def test_candidate_keys_preserve_dotted_and_hyphenated_sections(self):
        # Dotted/hyphenated SECTION numbers are whole sections, NOT subsections:
        # only parenthetical groups roll up. (Regression: the old root regex
        # truncated cfr-40:261.4 -> cfr-40:261 and usc-15:80a-1 -> usc-15:80a.)
        assert candidate_keys("cfr-40:261.4") == ["cfr-40:261.4"]
        assert candidate_keys("cfr-17:240.10b-5") == ["cfr-17:240.10b-5"]
        assert candidate_keys("usc-15:80a-1") == ["usc-15:80a-1"]
        assert candidate_keys("sec-rule:10b-5") == ["sec-rule:10b-5"]
        # A subsection of a dotted section rolls up to the dotted section root.
        assert candidate_keys("cfr-40:261.4(a)") == [
            "cfr-40:261.4(a)",
            "cfr-40:261.4",
        ]

    def test_candidate_keys_normalizes_underscore_to_hyphen(self):
        # Real canonical keys use hyphens exclusively in their namespace
        # prefix ("exchange-act:16", never "exchange_act:16"), but an LLM
        # occasionally emits the underscore-separated variant anyway
        # (pattern-matching Python-identifier conventions). candidate_keys
        # must try the normalized hyphenated form as a fallback.
        assert "exchange-act:16" in candidate_keys("exchange_act:16")

    def test_exact_and_subsection_keys_resolve(self):
        exact = find_authority_target("dgcl:122", self.user)
        sub = find_authority_target("dgcl:122(17)", self.user)
        assert exact is not None
        assert sub is not None
        assert exact.id == sub.id

    def test_unknown_key_returns_none(self):
        assert find_authority_target("dgcl:999", self.user) is None

    def test_visibility_respected(self):
        stranger = User.objects.create_user(username="stranger", password="p")
        assert find_authority_target("dgcl:122", stranger) is None

    def test_whole_act_key_resolves_to_representative_document(self):
        # A bare authority key (no section) — e.g. "dgcl" from "the Delaware
        # General Corporation Law", or "exchange-act" from the popular-name
        # grammar's "the Exchange Act" — references the WHOLE body of law. With
        # no section-less "whole act" document, it resolves to a representative
        # section so the citation links into the existing corpus instead of
        # stranding as a wanted/unsupported frontier entry.
        target = find_authority_target("dgcl", self.user)
        assert target is not None
        assert (target.custom_meta or {}).get("authority") == "dgcl"

    def test_whole_act_key_for_absent_authority_returns_none(self):
        # No corpus carries this authority — stays unresolved (genuinely wanted).
        assert find_authority_target("nonexistent-act", self.user) is None

    def test_sectioned_key_does_not_use_whole_act_fallback(self):
        # A section-precise citation we don't have must NOT silently resolve to
        # some other section of the same body — it stays unresolved.
        assert find_authority_target("dgcl:999", self.user) is None

    def test_whole_act_fallback_respects_visibility(self):
        stranger = User.objects.create_user(username="wa-stranger", password="p")
        assert find_authority_target("dgcl", stranger) is None


class AuthorityAliasRegistryNamespaceTests(TestCase):
    """authority_alias_registry merges global AuthorityNamespace aliases."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="ns", password="p")

    def test_global_namespace_alias_is_included(self):
        from opencontractserver.annotations.models import AuthorityNamespace
        from opencontractserver.enrichment.authorities import authority_alias_registry

        AuthorityNamespace.objects.create(
            prefix="tx-boc",
            display_name="Texas Business Organizations Code",
            jurisdiction="us-tx",
            authority_type="statute",
            aliases=["texas business organizations code"],
            is_global=True,
        )
        mapping = authority_alias_registry(self.user)
        assert mapping["texas business organizations code"] == "tx-boc"
        # Static defaults still present (back-compat).
        assert mapping["dgcl"] == "dgcl"
