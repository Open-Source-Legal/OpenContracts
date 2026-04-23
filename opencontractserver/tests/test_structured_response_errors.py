"""Tests for structured-response error classification and propagation.

Covers issue #1351: stop masking infrastructure errors (rate limit, billing,
auth, 5xx) behind the generic "information not present in document" message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TransactionTestCase

from opencontractserver.llms.exceptions import (
    AuthenticationError,
    BillingError,
    ModelError,
    RateLimitError,
    ServerError,
    StructuredResponseInfraError,
    classify_model_exception,
)

User = get_user_model()


class _FakeResponse:
    """Imitates a minimal ``httpx.Response``-like object."""

    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeAPIError(Exception):
    """Imitates an openai/anthropic APIStatusError shape."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None,
        body=None,
        response=None,
    ):
        super().__init__(message)
        self.status_code: int | None = status_code
        self.body = body
        self.response = response


class ClassifyModelExceptionTests(SimpleTestCase):
    """Unit tests for :func:`classify_model_exception`."""

    def test_openai_insufficient_quota_is_billing(self) -> None:
        """OpenAI returns ``insufficient_quota`` with a 429 status; it must
        classify as a billing error, not a rate-limit error."""
        body = {
            "error": {
                "message": "You exceeded your current quota",
                "type": "insufficient_quota",
                "code": "insufficient_quota",
            }
        }
        exc = _FakeAPIError("insufficient_quota", status_code=429, body=body)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, BillingError)
        self.assertEqual(classified.error_code, "billing_error")
        self.assertEqual(classified.status_code, 429)
        self.assertIs(classified.original, exc)

    def test_anthropic_credit_balance_too_low_is_billing(self) -> None:
        body = {
            "error": {
                "type": "credit_balance_too_low",
                "message": "Your credit balance is too low",
            }
        }
        exc = _FakeAPIError("credit_balance_too_low", status_code=429, body=body)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, BillingError)

    def test_anthropic_rate_limit_error_is_rate_limit(self) -> None:
        body = {"error": {"type": "rate_limit_error", "message": "slow down"}}
        exc = _FakeAPIError("rate_limit_error", status_code=429, body=body)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, RateLimitError)
        self.assertEqual(classified.error_code, "rate_limit_error")

    def test_status_429_without_body_is_rate_limit(self) -> None:
        exc = _FakeAPIError("Too Many Requests", status_code=429)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, RateLimitError)

    def test_status_401_is_authentication(self) -> None:
        body = {"error": {"type": "authentication_error", "message": "bad key"}}
        exc = _FakeAPIError("unauthorized", status_code=401, body=body)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, AuthenticationError)

    def test_status_403_is_authentication(self) -> None:
        exc = _FakeAPIError("forbidden", status_code=403)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, AuthenticationError)

    def test_status_500_is_server_error(self) -> None:
        exc = _FakeAPIError("internal error", status_code=500)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, ServerError)

    def test_status_503_is_server_error(self) -> None:
        exc = _FakeAPIError("service unavailable", status_code=503)

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, ServerError)

    def test_unclassified_exception_is_model_error(self) -> None:
        exc = ValueError("something odd happened")

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, ModelError)
        # ModelError is NOT an infra error; callers can distinguish.
        self.assertNotIsInstance(classified, StructuredResponseInfraError)
        self.assertEqual(classified.error_code, "model_error")

    def test_already_classified_exception_is_returned_unchanged(self) -> None:
        original = RateLimitError("already classified", status_code=429)

        classified = classify_model_exception(original)

        self.assertIs(classified, original)

    def test_response_status_code_fallback(self) -> None:
        """If the exception doesn't expose ``status_code`` directly but its
        ``response`` does, we still pick it up."""
        exc = _FakeAPIError(
            "server down",
            status_code=None,
            response=_FakeResponse(502, "bad gateway"),
        )
        # Override the direct attribute so only response carries the code.
        exc.status_code = None

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, ServerError)
        self.assertEqual(classified.status_code, 502)

    def test_rate_limit_from_message_without_status(self) -> None:
        exc = RuntimeError("too many requests, please slow down")

        classified = classify_model_exception(exc)

        self.assertIsInstance(classified, RateLimitError)

    def test_describe_contains_error_code_and_status(self) -> None:
        body = {"error": {"type": "insufficient_quota"}}
        classified = classify_model_exception(
            _FakeAPIError("out of credits", status_code=429, body=body)
        )

        description = classified.describe()

        self.assertIn("billing_error", description)
        self.assertIn("status_code=429", description)
        self.assertIn("insufficient_quota", description)


class StructuredResponsePropagationTests(TransactionTestCase):
    """Integration tests that verify infra errors propagate through
    :meth:`CoreAgentBase.structured_response` without being swallowed.
    """

    def setUp(self) -> None:
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        self.user = User.objects.create_user(username="infra-err-test", password="pw")
        self.corpus = Corpus.objects.create(
            title="Infra Error Test Corpus",
            creator=self.user,
            is_public=True,
        )
        self.doc = Document.objects.create(
            title="Infra Error Test Doc",
            creator=self.user,
            is_public=True,
            file_type="text/plain",
        )
        self.doc.txt_extract_file.save(
            "doc.txt",
            ContentFile(b"A short test document body."),
            save=True,
        )
        self.corpus.add_document(document=self.doc, user=self.user)

    async def _make_agent(self):
        from opencontractserver.llms import agents

        return await agents.for_document(
            document=self.doc,
            corpus=self.corpus,
            user_id=self.user.id,
            streaming=False,
        )

    async def test_rate_limit_error_propagates_as_classified(self) -> None:
        """When the underlying pydantic_ai agent raises a provider 429, the
        classified :class:`RateLimitError` must bubble up through
        :meth:`structured_response` instead of being swallowed as ``None``."""
        from pydantic import BaseModel

        class Answer(BaseModel):
            value: str

        agent = await self._make_agent()

        fake = _FakeAPIError(
            "rate_limit_error",
            status_code=429,
            body={"error": {"type": "rate_limit_error"}},
        )

        # Patch the PydanticAIAgent constructed inside _structured_response_raw
        # so its .run() raises the simulated provider error.
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=fake)

        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent",
            return_value=mock_instance,
        ):
            with self.assertRaises(RateLimitError) as ctx:
                await agent.structured_response(
                    prompt="anything",
                    target_type=Answer,
                )

        self.assertEqual(ctx.exception.error_code, "rate_limit_error")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIs(ctx.exception.original, fake)

    async def test_billing_error_propagates_as_classified(self) -> None:
        from pydantic import BaseModel

        class Answer(BaseModel):
            value: str

        agent = await self._make_agent()

        fake = _FakeAPIError(
            "insufficient_quota",
            status_code=429,
            body={"error": {"type": "insufficient_quota"}},
        )
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=fake)

        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent",
            return_value=mock_instance,
        ):
            with self.assertRaises(BillingError):
                await agent.structured_response(
                    prompt="anything",
                    target_type=Answer,
                )

    async def test_model_error_still_propagates(self) -> None:
        """Non-infra model errors should also propagate as
        :class:`ModelError` rather than being silently mapped to ``None`` —
        otherwise the caller cannot distinguish them from a legitimate None
        extraction.  (They're still distinguishable from infra errors via
        ``isinstance(err, StructuredResponseInfraError)``.)"""
        from pydantic import BaseModel

        class Answer(BaseModel):
            value: str

        agent = await self._make_agent()

        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(side_effect=ValueError("weird model output"))

        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent",
            return_value=mock_instance,
        ):
            with self.assertRaises(ModelError) as ctx:
                await agent.structured_response(
                    prompt="anything",
                    target_type=Answer,
                )

        self.assertFalse(isinstance(ctx.exception, StructuredResponseInfraError))

    async def test_legitimate_none_still_returns_none(self) -> None:
        """When the model legitimately produces ``None`` structured output,
        :meth:`structured_response` still returns ``None`` — the exception
        path is reserved for failures."""
        from pydantic import BaseModel

        class Answer(BaseModel):
            value: str

        agent = await self._make_agent()

        mock_result = MagicMock()
        mock_result.output = None
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_result)

        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent",
            return_value=mock_instance,
        ):
            result = await agent.structured_response(
                prompt="anything",
                target_type=Answer,
            )

        self.assertIsNone(result)


class DocExtractQueryTaskInfraErrorTests(TransactionTestCase):
    """End-to-end test that an infra failure no longer silently claims
    "information not present in document" but instead records the classified
    error code on the Datacell.
    """

    def setUp(self) -> None:
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import Column, Extract, Fieldset

        self.user = User.objects.create_user(
            username="doc-extract-infra", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Doc Extract Infra Corpus",
            creator=self.user,
            is_public=True,
        )
        self.doc = Document.objects.create(
            title="Doc Extract Infra Doc",
            creator=self.user,
            is_public=True,
            file_type="text/plain",
        )
        self.doc.txt_extract_file.save(
            "doc.txt",
            ContentFile(b"A short test document body."),
            save=True,
        )
        self.corpus.add_document(document=self.doc, user=self.user)

        self.fieldset = Fieldset.objects.create(
            name="Infra Fieldset",
            description="",
            creator=self.user,
        )
        self.column = Column.objects.create(
            name="Infra Column",
            fieldset=self.fieldset,
            output_type="str",
            query="What is the title?",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            corpus=self.corpus,
            name="Infra Extract",
            fieldset=self.fieldset,
            creator=self.user,
        )

    def _invoke_task(self, mocked_side_effect):
        """Drive :func:`doc_extract_query_task` with ``get_structured_response
        _from_document`` patched to raise ``mocked_side_effect``."""
        from opencontractserver.extracts.models import Datacell
        from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task

        datacell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.doc,
            data_definition="infra-test",
            creator=self.user,
        )

        with patch(
            "opencontractserver.llms.api.AgentAPI.get_structured_response_from_document",
            new=AsyncMock(side_effect=mocked_side_effect),
        ):
            doc_extract_query_task.si(cell_id=datacell.id).apply()

        datacell.refresh_from_db()
        return datacell

    def test_rate_limit_failure_records_error_code(self) -> None:
        """The acceptance test for issue #1351: a rate-limit is not silent."""
        datacell = self._invoke_task(
            RateLimitError(
                "Anthropic 429",
                status_code=429,
                body={"error": {"type": "rate_limit_error"}},
            )
        )

        self.assertIsNotNone(datacell.failed, "cell must be marked failed")
        self.assertIsNone(datacell.completed, "cell must NOT be marked completed")
        self.assertIn("rate_limit_error", datacell.stacktrace or "")
        # And it must NOT claim the info was merely "not present in document".
        self.assertNotIn(
            "may not be present in the document", datacell.stacktrace or ""
        )

    def test_billing_failure_records_error_code(self) -> None:
        datacell = self._invoke_task(
            BillingError(
                "OpenAI insufficient_quota",
                status_code=429,
                body={"error": {"type": "insufficient_quota"}},
            )
        )

        self.assertIsNotNone(datacell.failed)
        self.assertIn("billing_error", datacell.stacktrace or "")

    def test_auth_failure_records_error_code(self) -> None:
        datacell = self._invoke_task(
            AuthenticationError("invalid api key", status_code=401)
        )

        self.assertIsNotNone(datacell.failed)
        self.assertIn("authentication_error", datacell.stacktrace or "")

    def test_server_failure_records_error_code(self) -> None:
        datacell = self._invoke_task(ServerError("bad gateway", status_code=502))

        self.assertIsNotNone(datacell.failed)
        self.assertIn("server_error", datacell.stacktrace or "")

    def test_none_result_still_produces_answer_was_none(self) -> None:
        """When the model genuinely returns ``None`` we still mark failed,
        but with a distinct ``answer_was_none`` code — not an infra code."""
        from opencontractserver.extracts.models import Datacell
        from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task

        datacell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.doc,
            data_definition="infra-test-none",
            creator=self.user,
        )

        with patch(
            "opencontractserver.llms.api.AgentAPI.get_structured_response_from_document",
            new=AsyncMock(return_value=None),
        ):
            doc_extract_query_task.si(cell_id=datacell.id).apply()

        datacell.refresh_from_db()
        self.assertIsNotNone(datacell.failed)
        self.assertIn("answer_was_none", datacell.stacktrace or "")
        for infra_code in (
            "rate_limit_error",
            "billing_error",
            "authentication_error",
            "server_error",
        ):
            self.assertNotIn(
                infra_code,
                datacell.stacktrace or "",
                f"answer_was_none path must not mention infra code {infra_code}",
            )
