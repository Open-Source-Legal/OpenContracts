"""Tests for the CAML intelligence-block default + backfill.

Covers the "structural default, narrative override" behaviour added so every
corpus's ``Readme.CAML`` composes the live corpus-intelligence overview:

  * ``opencontractserver/corpuses/caml_intelligence.py`` — the pure string
    helpers (``ensure_intelligence_block`` idempotency / append, the default
    builder).
  * ``CorpusService.ensure_readme_caml_default`` — the deterministic default
    service path (creates a structural Readme.CAML, or appends the block to an
    existing one).
  * The branding post-process — given an agent CAML without the block, the
    saved result gains it.
  * The ``backfill_intelligence_block`` management command — idempotent, and
    creates a structural README where none exists.

The LLM agent and the OpenAI Images API are never exercised here — the
deterministic default path is tested directly, and the branding post-process is
tested via its public service entry point with the agent bypassed.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from opencontractserver.corpuses.caml_intelligence import (
    CAML_INTELLIGENCE_BLOCK,
    CAML_INTELLIGENCE_MARKERS,
    build_default_readme_caml,
    ensure_intelligence_block,
    has_intelligence_block,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.corpuses.services.description_cache import read_caml_body
from opencontractserver.users.models import User


def _readme_body(user: User, corpus: Corpus) -> str:
    """Return the corpus's current Readme.CAML body, or ``""`` if it has none.

    Shared across the DB-backed test classes below so the read-back logic isn't
    re-declared per class.
    """
    from opencontractserver.corpuses.services.corpus_documents import (
        CorpusDocumentService,
    )

    doc = CorpusDocumentService.get_corpus_caml_articles(user, corpus).first()
    return read_caml_body(doc) if doc is not None else ""


# =============================================================================
# Pure string helpers (no DB)
# =============================================================================


class IntelligenceBlockHelperTests(TestCase):
    def test_block_contains_all_three_markers(self):
        for marker in CAML_INTELLIGENCE_MARKERS:
            self.assertIn(marker, CAML_INTELLIGENCE_BLOCK)
        # The three the task contract names, explicitly.
        self.assertIn("[component:insight-panel]", CAML_INTELLIGENCE_BLOCK)
        self.assertIn("[component:document-graph]", CAML_INTELLIGENCE_BLOCK)
        self.assertIn("[component:ask-across-docs]", CAML_INTELLIGENCE_BLOCK)

    def test_has_intelligence_block(self):
        self.assertFalse(has_intelligence_block(""))
        self.assertFalse(has_intelligence_block(None))
        self.assertFalse(has_intelligence_block("# Plain article\n\nNo embeds."))
        self.assertTrue(has_intelligence_block(CAML_INTELLIGENCE_BLOCK))
        # A single marker counts (lenient detection).
        self.assertTrue(
            has_intelligence_block("::: oc-component\n[component:document-graph]\n:::")
        )

    def test_ensure_appends_when_absent(self):
        src = "# My Collection\n\nSome narrative prose."
        out = ensure_intelligence_block(src)
        self.assertIn("# My Collection", out)
        self.assertIn("Some narrative prose.", out)
        self.assertTrue(has_intelligence_block(out))
        # Appended below the existing content, one blank-line seam.
        self.assertTrue(out.startswith("# My Collection\n\nSome narrative prose.\n\n"))

    def test_ensure_is_idempotent(self):
        src = "# Doc\n\nProse."
        once = ensure_intelligence_block(src)
        twice = ensure_intelligence_block(once)
        self.assertEqual(once, twice)
        # The block appears exactly once (each marker present once).
        for marker in CAML_INTELLIGENCE_MARKERS:
            self.assertEqual(twice.count(marker), 1)

    def test_ensure_leaves_content_with_block_untouched(self):
        src = "# Doc\n\nProse.\n\n" + CAML_INTELLIGENCE_BLOCK
        self.assertEqual(ensure_intelligence_block(src), src)

    def test_ensure_empty_yields_bare_block(self):
        self.assertEqual(ensure_intelligence_block(""), CAML_INTELLIGENCE_BLOCK)
        self.assertEqual(ensure_intelligence_block("   \n  "), CAML_INTELLIGENCE_BLOCK)
        self.assertEqual(ensure_intelligence_block(None), CAML_INTELLIGENCE_BLOCK)

    def test_build_default_readme_caml(self):
        out = build_default_readme_caml(
            "Tax Filings 2024", "Annual corporate tax docs."
        )
        self.assertTrue(out.startswith("# Tax Filings 2024"))
        self.assertIn("Annual corporate tax docs.", out)
        for marker in CAML_INTELLIGENCE_MARKERS:
            self.assertIn(marker, out)

    def test_build_default_readme_caml_without_description(self):
        out = build_default_readme_caml("Just A Title", None)
        self.assertTrue(out.startswith("# Just A Title"))
        self.assertTrue(has_intelligence_block(out))

    def test_build_default_readme_caml_blank_title_falls_back(self):
        out = build_default_readme_caml("   ", "")
        self.assertTrue(out.startswith("# Untitled collection"))

    def test_build_default_strips_caml_injection_from_metadata(self):
        """Crafted title/description cannot smuggle directives into the article.

        Corpus metadata is user-controlled and the backfill command feeds every
        historical corpus through this builder, so ``[component:...]`` markers
        and ``:::`` fence lines must be stripped — otherwise a title like
        ``"X\\n\\n::: oc-component\\n[component:evil]\\n:::"`` would mount an
        arbitrary registered embed (or break the document's fence structure).
        """
        out = build_default_readme_caml(
            "Quarterly\n\n::: oc-component\n[component:evil-embed]\n:::\nFilings",
            "Docs\n::: oc-component\n[component:another]\n:::\nlegit prose",
        )
        self.assertNotIn("[component:evil-embed]", out)
        self.assertNotIn("[component:another]", out)
        # The only fences/markers left are the canonical block's own.
        self.assertEqual(out.count(":::"), CAML_INTELLIGENCE_BLOCK.count(":::"))
        for marker in CAML_INTELLIGENCE_MARKERS:
            self.assertEqual(out.count(marker), 1)
        # A multi-line title collapses onto the single heading line.
        first_line = out.splitlines()[0]
        self.assertEqual(first_line, "# Quarterly Filings")
        self.assertIn("legit prose", out)

    def test_build_default_metadata_reduced_to_directives_falls_back(self):
        """Metadata that is *only* directive syntax degrades to the fallbacks."""
        out = build_default_readme_caml(
            "::: oc-component\n[component:evil]\n:::",
            ":::",
        )
        self.assertTrue(out.startswith("# Untitled collection"))
        self.assertEqual(out.count(":::"), CAML_INTELLIGENCE_BLOCK.count(":::"))


# =============================================================================
# Service: ensure_readme_caml_default (deterministic default path)
# =============================================================================


class EnsureReadmeCamlDefaultTests(TestCase):
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="caml-intel-user", password="x")

    def test_creates_structural_default_when_no_article(self):
        # ``_skip_signals`` keeps the branding post_save signal from queuing a
        # Celery task during the fixture create; we drive the default directly.
        corpus = Corpus(
            title="Newco", description="A fresh collection.", creator=self.user
        )
        corpus._skip_signals = True
        corpus.save()

        with self.captureOnCommitCallbacks(execute=True):
            result = CorpusService.ensure_readme_caml_default(self.user, corpus)
        self.assertTrue(result.ok)

        body = _readme_body(self.user, corpus)
        self.assertTrue(body.startswith("# Newco"))
        self.assertIn("A fresh collection.", body)
        self.assertTrue(has_intelligence_block(body))

    def test_appends_block_to_existing_article_without_block(self):
        corpus = Corpus(title="Existing", creator=self.user)
        corpus._skip_signals = True
        corpus.save()

        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(
                self.user, corpus, "# Existing\n\nAuthor prose, no embeds."
            )
        self.assertFalse(has_intelligence_block(_readme_body(self.user, corpus)))

        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.ensure_readme_caml_default(self.user, corpus)

        body = _readme_body(self.user, corpus)
        self.assertIn("Author prose, no embeds.", body)
        self.assertTrue(has_intelligence_block(body))

    def test_idempotent_no_duplicate_block(self):
        corpus = Corpus(title="Idem", creator=self.user)
        corpus._skip_signals = True
        corpus.save()

        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.ensure_readme_caml_default(self.user, corpus)
        with self.captureOnCommitCallbacks(execute=True):
            second = CorpusService.ensure_readme_caml_default(self.user, corpus)
        # Content-identical second call is a no-op (returns None value).
        self.assertTrue(second.ok)
        self.assertIsNone(second.value)

        body = _readme_body(self.user, corpus)
        for marker in CAML_INTELLIGENCE_MARKERS:
            self.assertEqual(body.count(marker), 1)


# =============================================================================
# Branding post-process: agent CAML gains the block
# =============================================================================


class BrandingPostProcessTests(TestCase):
    """The branding flow must end with the block present even if the agent omitted it.

    We bypass the LLM by writing the "agent's" article directly (as the agent's
    ``update_corpus_description`` tool would), then assert the post-process step
    (``ensure_readme_caml_default``, called from ``_generate_readme`` after the
    agent turn) appends the block.
    """

    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="branding-pp-user", password="x")

    def test_agent_caml_without_block_gains_it(self):
        corpus = Corpus(title="Branded", creator=self.user)
        corpus._skip_signals = True
        corpus.save()

        # Simulate the agent's save: a CAML article with no intelligence embeds.
        agent_caml = '---\nversion: "1.0"\n---\n\n# Branded\n\nResearched narrative.'
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(self.user, corpus, agent_caml)
        self.assertFalse(has_intelligence_block(_readme_body(self.user, corpus)))

        # The post-process step the branding flow runs after the agent turn.
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.ensure_readme_caml_default(self.user, corpus)

        body = _readme_body(self.user, corpus)
        self.assertIn("Researched narrative.", body)
        self.assertTrue(has_intelligence_block(body))


# =============================================================================
# Backfill management command
# =============================================================================


class BackfillIntelligenceBlockCommandTests(TestCase):
    user: User

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="backfill-user", password="x")

    def _make_corpus(self, title: str) -> Corpus:
        corpus = Corpus(title=title, creator=self.user)
        corpus._skip_signals = True
        corpus.save()
        return corpus

    def test_creates_structural_readme_where_none_exists(self):
        corpus = self._make_corpus("NoReadme")
        self.assertEqual(_readme_body(self.user, corpus), "")

        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("backfill_intelligence_block", stdout=out)

        body = _readme_body(self.user, corpus)
        self.assertTrue(body.startswith("# NoReadme"))
        self.assertTrue(has_intelligence_block(body))
        self.assertIn("created", out.getvalue())

    def test_idempotent_block_appears_once(self):
        corpus = self._make_corpus("RunTwice")

        with self.captureOnCommitCallbacks(execute=True):
            call_command("backfill_intelligence_block", stdout=StringIO())
        with self.captureOnCommitCallbacks(execute=True):
            call_command("backfill_intelligence_block", stdout=StringIO())

        body = _readme_body(self.user, corpus)
        for marker in CAML_INTELLIGENCE_MARKERS:
            self.assertEqual(body.count(marker), 1)

    def test_appends_block_to_existing_readme(self):
        corpus = self._make_corpus("HasProse")
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(
                self.user, corpus, "# HasProse\n\nKeep this prose."
            )

        with self.captureOnCommitCallbacks(execute=True):
            call_command("backfill_intelligence_block", stdout=StringIO())

        body = _readme_body(self.user, corpus)
        self.assertIn("Keep this prose.", body)
        self.assertTrue(has_intelligence_block(body))

    def test_dry_run_writes_nothing(self):
        corpus = self._make_corpus("DryRun")

        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("backfill_intelligence_block", "--dry-run", stdout=out)

        # No README written under dry-run.
        self.assertEqual(_readme_body(self.user, corpus), "")
        self.assertIn("would create", out.getvalue())
