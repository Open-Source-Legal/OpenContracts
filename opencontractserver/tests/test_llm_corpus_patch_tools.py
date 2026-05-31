import difflib

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_documents import (
    CorpusDocumentService,
)
from opencontractserver.corpuses.services.description_cache import (
    read_caml_body,
)
from opencontractserver.llms.tools.core_tools import update_corpus_description

User = get_user_model()


def _read_corpus_caml_body(corpus, user) -> str:
    """Read the corpus's canonical Readme.CAML body via the service layer."""
    caml = CorpusDocumentService.get_corpus_caml_articles(user, corpus).first()
    return read_caml_body(caml) if caml else ""


class CorpusPatchToolTests(TestCase):
    """Verify that an ndiff patch round-trips through the canonical CAML
    write path.

    The bodies below intentionally end in ``\\n`` so ``ndiff`` produces a
    well-formed (line-terminated) diff. Without the trailing newline the
    final removed/added lines emerge as ``'- Initial+ Changed'`` after
    join — a known ndiff edge case ``difflib.restore`` cannot recover
    from — which would mask the canonical-write contract this test is
    actually verifying.
    """

    INITIAL_BODY = "# H1\n\nInitial\n"
    UPDATED_BODY = "# H1\n\nChanged\n"

    def setUp(self):
        self.user = User.objects.create_user("cuser", password="pw")
        self.corpus = Corpus.objects.create(title="Patch C", creator=self.user)
        # Seed the initial CAML body. ``import_document`` (called by
        # ``CorpusService.update_description`` under the hood) schedules
        # cache-refresh signal work on commit; wrap so it executes
        # before the test body reads the CAML back.
        with self.captureOnCommitCallbacks(execute=True):
            update_corpus_description(
                corpus_id=self.corpus.id,
                new_content=self.INITIAL_BODY,
                author_id=self.user.id,
            )

    def test_patch(self):
        current = _read_corpus_caml_body(self.corpus, self.user)
        self.assertEqual(
            current,
            self.INITIAL_BODY,
            "Sanity: setUp should have seeded the canonical CAML body.",
        )

        diff_text = "".join(
            difflib.ndiff(
                current.splitlines(keepends=True),
                self.UPDATED_BODY.splitlines(keepends=True),
            )
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = update_corpus_description(
                corpus_id=self.corpus.id,
                diff_text=diff_text,
                author_id=self.user.id,
            )

        # ``CorpusService.update_description`` (Task 8) returns the new
        # head Document; ``update_corpus_description`` unwraps the
        # ServiceResult so this is non-None whenever content changed.
        self.assertIsNotNone(result)

        self.corpus.refresh_from_db()
        updated = _read_corpus_caml_body(self.corpus, self.user)
        self.assertEqual(updated, self.UPDATED_BODY)
