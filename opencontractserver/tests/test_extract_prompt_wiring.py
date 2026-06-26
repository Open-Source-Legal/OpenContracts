"""Regression tests for extraction-prompt construction.

These pin behavior that the marvin -> doc-agent rewrite (commit 184903f62)
silently dropped and that the diligence eval restored:

* ``Column.instructions`` / ``must_contain_text`` / ``limit_to_label`` are folded
  into the prompt the extraction agent actually runs (previously ignored).
* The full text of a short document is injected (fenced) so the agent can
  confirm clause *absence* in one read instead of search-looping.

The agent call is patched so no LLM is hit; we assert on the ``prompt`` that the
task hands to ``get_structured_response_and_sources_from_document``.
"""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task

User = get_user_model()

_DOC_TEXT = (
    "This Agreement is governed by the laws of the State of Texas. "
    "Vendor shall indemnify and hold harmless the City."
)


class ExtractPromptWiringTestCase(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pwuser", password="pw")
        self.corpus = Corpus.objects.create(title="PW Corpus", creator=self.user)
        self.document = Document.objects.create(
            title="PW Doc",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=ContentFile(_DOC_TEXT.encode(), name="pw.txt"),
        )
        self.corpus.add_document(document=self.document, user=self.user)
        self.fieldset = Fieldset.objects.create(
            name="PW FS", description="d", creator=self.user
        )

    def _capture_prompt(self, column) -> str:
        """Run the task with the agent patched; return the prompt it was given."""
        extract = Extract.objects.create(
            name="PW Ex", fieldset=self.fieldset, creator=self.user
        )
        extract.documents.add(self.document)
        cell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition=column.output_type,
            creator=self.user,
        )

        captured: dict[str, str] = {}

        async def fake_agent(*args, **kwargs):
            captured["prompt"] = kwargs.get("prompt", "")
            return ("ok", [])

        # The task does ``from opencontractserver.llms import agents`` then calls
        # ``agents.get_structured_response_and_sources_from_document`` — patch the
        # attribute on that module so the lookup at call time resolves to ours.
        from unittest.mock import patch

        import opencontractserver.llms.agents as agents_mod

        with patch.object(
            agents_mod,
            "get_structured_response_and_sources_from_document",
            fake_agent,
        ):
            doc_extract_query_task.si(cell.id).apply()
        return captured.get("prompt", "")

    def test_instructions_reach_prompt(self):
        col = Column.objects.create(
            name="c_instr",
            fieldset=self.fieldset,
            query="What is the governing law?",
            output_type="str",
            instructions="SENTINEL_INSTRUCTION_RETURN_ISO",
            creator=self.user,
        )
        prompt = self._capture_prompt(col)
        self.assertIn("SENTINEL_INSTRUCTION_RETURN_ISO", prompt)

    def test_must_contain_and_limit_to_label_reach_prompt(self):
        col = Column.objects.create(
            name="c_constraints",
            fieldset=self.fieldset,
            query="What is the value?",
            output_type="str",
            must_contain_text="SENTINEL_PAYMENT_SECTION",
            limit_to_label="SENTINEL_LABEL",
            creator=self.user,
        )
        prompt = self._capture_prompt(col)
        self.assertIn("SENTINEL_PAYMENT_SECTION", prompt)
        self.assertIn("SENTINEL_LABEL", prompt)

    def test_full_text_injected_for_short_doc(self):
        col = Column.objects.create(
            name="c_fulltext",
            fieldset=self.fieldset,
            query="Is there an indemnification clause?",
            output_type="bool",
            creator=self.user,
        )
        prompt = self._capture_prompt(col)
        # The short document's full text is injected so the agent can answer
        # (and confirm absence) without search-looping.
        self.assertIn("indemnify and hold harmless", prompt)
