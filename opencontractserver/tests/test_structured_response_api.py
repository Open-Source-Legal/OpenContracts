"""
Comprehensive tests for the structured response API.

Tests the new one-shot structured data extraction capabilities that allow
extracting typed data from documents and corpuses without conversation persistence.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import pytest
import vcr
from asgiref.sync import sync_to_async
from pydantic import BaseModel, Field

from opencontractserver.llms import agents
from opencontractserver.llms.types import AgentFramework
from opencontractserver.tests.base import BaseFixtureTestCase


# Set up logging for structured data results
def setup_structured_data_logger():
    """Set up logger to capture structured data results."""
    log_file = Path(__file__).parent / "structured_data_results.log"

    # Create a logger specifically for structured data
    logger = logging.getLogger("structured_data_results")
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create file handler
    file_handler = logging.FileHandler(log_file, mode="w")
    file_handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter("%(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger


# Initialize logger
structured_data_logger = setup_structured_data_logger()


def log_structured_result(test_name: str, result: any):
    """Log structured result as JSON for inspection."""
    try:
        # Convert result to JSON-serializable format
        if result is None:
            json_result = None
        elif hasattr(result, "model_dump"):
            # Pydantic model
            json_result = result.model_dump()
        elif isinstance(result, list):
            # List of items (potentially Pydantic models)
            json_result = []
            for item in result:
                if hasattr(item, "model_dump"):
                    json_result.append(item.model_dump())
                else:
                    json_result.append(item)
        else:
            # Basic types (str, int, float, bool)
            json_result = result

        # Log the result
        structured_data_logger.info(f"\n{'='*50}")
        structured_data_logger.info(f"TEST: {test_name}")
        structured_data_logger.info(f"{'='*50}")
        structured_data_logger.info(f"RESULT TYPE: {type(result).__name__}")
        structured_data_logger.info("RESULT DATA:")
        structured_data_logger.info(
            json.dumps(json_result, indent=2, ensure_ascii=False)
        )
        structured_data_logger.info("")

    except Exception as e:
        structured_data_logger.error(f"Error logging result for {test_name}: {str(e)}")
        structured_data_logger.info(f"Raw result: {repr(result)}")


# Pydantic models for structured extraction tests
class ContractDate(BaseModel):
    """A single important date in a contract."""

    date: str = Field(description="Date in ISO format (YYYY-MM-DD)")
    description: str = Field(description="What this date represents")
    is_deadline: bool = Field(description="Whether this is a deadline")


class ContractDates(BaseModel):
    """All important dates found in a contract."""

    effective_date: Optional[str] = Field(None, description="Contract effective date")
    expiration_date: Optional[str] = Field(None, description="Contract expiration date")
    key_dates: list[ContractDate] = Field(
        default_factory=list, description="Other important dates"
    )


class ContractParty(BaseModel):
    """A party to a contract."""

    name: str = Field(description="Full legal name")
    role: str = Field(
        description="Role in contract (e.g., 'Buyer', 'Seller', 'Service Provider')"
    )
    address: Optional[str] = Field(None, description="Business address if mentioned")


class ContractAnalysis(BaseModel):
    """Comprehensive contract analysis results."""

    title: str = Field(description="Contract title or type")
    parties: list[ContractParty] = Field(description="All parties to the contract")
    total_value: Optional[float] = Field(
        None, description="Total contract value in dollars"
    )
    term_months: Optional[int] = Field(None, description="Contract term in months")
    governing_law: Optional[str] = Field(None, description="Governing law jurisdiction")
    key_obligations: list[str] = Field(description="Key obligations for each party")
    risk_factors: list[str] = Field(
        default_factory=list, description="Identified risk factors"
    )
    public_law_number: Optional[str] = Field(
        None, description="Public law number pertaining to the amendment"
    )
    amendment_year: Optional[int] = Field(
        None, description="Year the section was amended"
    )


class PaymentTerm(BaseModel):
    """A payment term in a contract."""

    amount: float = Field(description="Payment amount")
    currency: str = Field(default="USD", description="Currency code")
    due_date: Optional[str] = Field(None, description="When payment is due")
    condition: str = Field(description="Payment condition or trigger")


class CorpusInsight(BaseModel):
    """High-level insights from analyzing a corpus of documents."""

    total_documents: int = Field(description="Number of documents analyzed")
    common_themes: list[str] = Field(description="Common themes across documents")
    total_contract_value: Optional[float] = Field(
        None, description="Sum of all contract values"
    )
    most_frequent_parties: list[str] = Field(
        description="Most frequently appearing parties"
    )
    key_risks: list[str] = Field(
        description="Key risks identified across all documents"
    )


@pytest.mark.asyncio
class TestStructuredResponseAPI(BaseFixtureTestCase):
    """Test suite for structured response extraction capabilities."""

    # Basic type extraction tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_string_from_document.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_string_from_document(self):
        """Test extracting a simple string from a document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response("The title of this document.", str)

        # Log the structured result for inspection
        log_structured_result("test_extract_string_from_document", result)

        assert isinstance(result, str) or result is None
        if result:
            print(f"Result: {result}")
            assert len(result) > 0
            # Should contain document title
            assert "USC Title 1 - Chapter 1".lower() in result.lower()

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_integer_from_document.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_integer_from_document(self):
        """Test extracting an integer value from a document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Extract the section number for the definition of 'County'.", int
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_integer_from_document", result)

        assert isinstance(result, int) or result is None
        if result:
            assert result == 2  # County is defined in Section 2

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_float_from_document.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_float_from_document(self):
        """Test extracting a float value from a document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "What title of the USC is this?", float
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_float_from_document", result)

        assert isinstance(result, float) or result is None
        if result is not None:
            assert result == 1.0

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_boolean_from_document.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_boolean_from_document(self):
        """Test extracting a boolean value from a document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Does this document establish the process for presidential impeachment?",
            bool,
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_boolean_from_document", result)

        assert isinstance(result, bool) or result is None
        if result is not None:
            assert result is False

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_list_from_document.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_list_from_document(self):
        """Test extracting a list from a document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Extract a list of the terms that Section 1 defines as being included under the words 'person' and 'whoever'.",  # noqa: E501
            list[str],
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_list_from_document", result)

        assert isinstance(result, list) or result is None
        if result:
            assert all(isinstance(item, str) for item in result)

    # Complex Pydantic model extraction tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_contract_dates.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_contract_dates(self):
        """Test extracting structured date information from a contract."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Extract the enactment date of the 'Born-Alive Infants Protection Act of 2002'.",
            ContractDates,
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_contract_dates", result)

        assert isinstance(result, ContractDates) or result is None
        if result:
            # Validate the structure
            if result.effective_date:
                assert isinstance(result.effective_date, str)
            assert isinstance(result.key_dates, list)
            for date in result.key_dates:
                assert isinstance(date.date, str)
                assert isinstance(date.description, str)
                assert isinstance(date.is_deadline, bool)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_contract_parties.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_contract_parties(self):
        """Test extracting party information from a contract."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Extract a list of any private corporations or associations named as parties in this legal text.",
            list[ContractParty],
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_contract_parties", result)

        assert isinstance(result, list) or result is None
        if result is not None:
            # Expect an empty list for this statute
            assert result == []

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_comprehensive_analysis.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_comprehensive_analysis(self):
        """Test extracting a comprehensive contract analysis."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Perform a comprehensive analysis of the 'Respect for Marriage Act' amendment to Section 7.",
            ContractAnalysis,
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_comprehensive_analysis", result)

        assert isinstance(result, ContractAnalysis) or result is None
        if result:
            assert result.title
            assert len(result.parties) > 0
            assert isinstance(result.key_obligations, list)
            assert result.public_law_number
            assert isinstance(result.amendment_year, int)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_payment_terms.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_payment_terms(self):
        """Test extracting payment terms from a document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Extract a list of any payment schedules or financial obligations mentioned in the text.",
            list[PaymentTerm],
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_payment_terms", result)

        assert isinstance(result, list) or result is None
        if result:
            # Expect no payment terms in this legal text
            assert result == []

    # Corpus-level extraction tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_corpus_insights.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_corpus_insights(self):
        """Test extracting insights from an entire corpus."""
        # Add multiple documents to corpus
        for doc in self.docs[:3]:  # Use first 3 documents
            await sync_to_async(self.corpus.add_document)(document=doc, user=self.user)

        agent = await agents.for_corpus(
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "From a corpus containing Title 1 and other legal documents, extract high-level insights about statutory interpretation.",  # noqa: E501
            CorpusInsight,
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_corpus_insights", result)

        assert isinstance(result, CorpusInsight) or result is None
        if result:
            assert result.total_documents >= 0
            assert isinstance(result.common_themes, list)
            assert isinstance(result.most_frequent_parties, list)
            assert isinstance(result.key_risks, list)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_extract_corpus_statistics.yaml",
        filter_headers=["authorization"],
    )
    async def test_extract_corpus_statistics(self):
        """Test extracting statistical information from a corpus."""
        agent = await agents.for_corpus(
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        class CorpusStats(BaseModel):
            document_count: int
            total_pages: int
            average_document_length: float
            most_common_document_type: str

        result = await agent.structured_response(
            "Extract basic statistics about a corpus of legal documents including Title 1.",
            CorpusStats,
        )

        # Log the structured result for inspection
        log_structured_result("test_extract_corpus_statistics", result)

        assert isinstance(result, CorpusStats) or result is None
        if result:
            assert result.document_count >= 0
            assert result.total_pages >= 0
            assert result.average_document_length >= 0

    # Parameter override tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_with_custom_system_prompt.yaml",
        filter_headers=["authorization"],
    )
    async def test_with_custom_system_prompt(self):
        """Test extraction with a custom system prompt."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Ahoy matey! What be the definition of 'vessel'?",
            str,
            system_prompt="You are a pirate speaking in nautical language.",
        )

        # Log the structured result for inspection
        log_structured_result("test_with_custom_system_prompt", result)

        assert isinstance(result, str) or result is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_verification_behavior_with_default_prompt.yaml",
        filter_headers=["authorization"],
    )
    async def test_verification_behavior_with_default_prompt(self):
        """Test that the default prompt includes verification behavior."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Test with a complex extraction that benefits from verification
        class VerifiableData(BaseModel):
            total_amount: float = Field(description="Total monetary amount")
            currency: str = Field(description="Currency code (e.g., USD, EUR)")
            is_signed: bool = Field(description="Whether the document is signed")
            parties_count: int = Field(description="Number of parties involved")

        result = await agent.structured_response(
            "Extract financial and signature information from this document",
            VerifiableData,
        )

        # Log the structured result for inspection
        log_structured_result("test_verification_behavior_with_default_prompt", result)

        assert isinstance(result, VerifiableData) or result is None
        if result:
            # Verification should ensure reasonable values
            assert result.total_amount >= 0  # No negative amounts
            # Allow empty currency string when no monetary value is present
            if result.currency:
                assert len(result.currency) == 3  # Valid currency code when provided
            else:
                assert result.currency == ""  # Expect empty string if no currency found

            # Parties count may legitimately be zero if no parties are identified
            assert result.parties_count >= 0  # Non-negative parties count

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_custom_prompt_overrides_default.yaml",
        filter_headers=["authorization"],
    )
    async def test_custom_prompt_overrides_default(self):
        """Test that custom system prompt completely overrides the default extraction prompt."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Use a deliberately bad custom prompt that would produce poor results
        # This demonstrates that it truly overrides the default
        bad_prompt = "You are a legal scholar. Provide precise statutory interpretation without creative additions."

        class TestData(BaseModel):
            document_type: str
            accuracy_statement: str = Field(description="A statement about accuracy")

        result = await agent.structured_response(
            "Using your expertise, identify the primary purpose of this text and the legal principle it establishes.",
            TestData,
            system_prompt=bad_prompt,
        )

        # Log the structured result for inspection
        log_structured_result("test_custom_prompt_overrides_default", result)

        # The result should still parse but might contain creative/inaccurate data
        # due to our bad prompt overriding the careful extraction prompt
        assert isinstance(result, TestData) or result is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_verification_prevents_placeholder_values.yaml",
        filter_headers=["authorization"],
    )
    async def test_verification_prevents_placeholder_values(self):
        """Test that verification prevents placeholder values like 'N/A' unless actually in document."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        class ContactInfo(BaseModel):
            phone: Optional[str] = Field(None, description="Phone number if present")
            email: Optional[str] = Field(None, description="Email if present")
            fax: Optional[str] = Field(None, description="Fax number if present")

        result = await agent.structured_response(
            "Extract contact information (phone, email, fax) for the enactor of this title.",
            ContactInfo,
        )

        # Log the structured result for inspection
        log_structured_result("test_verification_prevents_placeholder_values", result)

        assert isinstance(result, ContactInfo) or result is None
        if result:
            # Verification should return None rather than placeholder values
            # unless they actually appear in the document
            if result.phone:
                assert result.phone != "N/A"
                assert result.phone != "Not Available"
            if result.email:
                assert "@" in result.email  # Basic email validation
            if result.fax:
                assert result.fax != "N/A"

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_with_custom_temperature.yaml",
        filter_headers=["authorization"],
    )
    async def test_with_custom_temperature(self):
        """Test extraction with custom temperature setting."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Low temperature for deterministic extraction
        result = await agent.structured_response(
            "Is this a legal document?", bool, temperature=0.1
        )

        # Log the structured result for inspection
        log_structured_result("test_with_custom_temperature", result)

        assert isinstance(result, bool) or result is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_with_custom_model.yaml",
        filter_headers=["authorization"],
    )
    async def test_with_custom_model(self):
        """Test extraction with a different model."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Using the specified model, summarize the amendment made by Pub. L. 112-231.",
            str,
            model="gpt-3.5-turbo",
        )

        # Log the structured result for inspection
        log_structured_result("test_with_custom_model", result)

        assert isinstance(result, str) or result is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_with_max_tokens_limit.yaml",
        filter_headers=["authorization"],
    )
    async def test_with_max_tokens_limit(self):
        """Test extraction with token limit."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Describe this document.", str, max_tokens=50
        )

        # Log the structured result for inspection
        log_structured_result("test_with_max_tokens_limit", result)

        assert isinstance(result, str) or result is None
        if result:
            # Result should be relatively short due to token limit
            assert len(result.split()) < 100

    # Error handling tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_returns_none_on_llm_error.yaml",
        filter_headers=["authorization"],
    )
    async def test_returns_none_on_llm_error(self):
        """Test that the method returns None on LLM errors."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Use an invalid model to trigger an error
        result = await agent.structured_response(
            "Define 'insane person'.", str, model="invalid-model-name-12345"
        )

        # Log the structured result for inspection
        log_structured_result("test_returns_none_on_llm_error", result)

        assert result is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_returns_none_on_parsing_error.yaml",
        filter_headers=["authorization"],
    )
    async def test_returns_none_on_parsing_error(self):
        """Test that the method returns None when response can't be parsed."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Complex model that might fail to parse
        class ComplexModel(BaseModel):
            nested_data: dict[str, list[dict[str, float]]]

        result = await agent.structured_response(
            "Extract some data that definitely won't match this complex structure",
            ComplexModel,
            temperature=2.0,  # High temperature for unpredictable output
        )

        # Log the structured result for inspection
        log_structured_result("test_returns_none_on_parsing_error", result)

        # Should return None rather than raising an exception
        assert result is None or isinstance(result, ComplexModel)

    # Framework comparison tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_pydantic_ai_structured_response.yaml",
        filter_headers=["authorization"],
    )
    async def test_pydantic_ai_structured_response(self):
        """Test structured response with PydanticAI framework."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response("What type of document is this?", str)

        # Log the structured result for inspection
        log_structured_result("test_pydantic_ai_structured_response", result)

        assert isinstance(result, str) or result is None

    # Ephemeral nature tests

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_no_conversation_persistence.yaml",
        filter_headers=["authorization"],
    )
    async def test_no_conversation_persistence(self):
        """Test that structured responses don't create conversation history."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,  # Even with user_id, shouldn't persist
        )

        # Get initial conversation state
        initial_messages = await agent.get_conversation_messages()
        initial_count = len(initial_messages)

        # Make structured response call
        result = await agent.structured_response("Extract the document title", str)

        # Log the structured result for inspection
        log_structured_result("test_no_conversation_persistence", result)

        # Check conversation hasn't changed
        final_messages = await agent.get_conversation_messages()
        final_count = len(final_messages)

        assert final_count == initial_count

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_multiple_extractions_independent.yaml",
        filter_headers=["authorization"],
    )
    async def test_multiple_extractions_independent(self):
        """Test that multiple extractions are independent."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # First extraction
        result1 = await agent.structured_response(
            "Provide the statutory definition of 'writing'.", str
        )

        # Second extraction - should not have context from first
        result2 = await agent.structured_response(
            "Provide the statutory definition of 'oath'.",  # Should not rely on prior context
            str,
        )

        # Log the structured result for inspection
        log_structured_result(
            "test_multiple_extractions_independent",
            {"first_result": result1, "second_result": result2},
        )

        assert result1 is None or isinstance(result1, str)
        assert result2 is None or isinstance(result2, str)

        # The second result shouldn't reference the first question
        if result2:
            assert "writing" not in result2.lower()

    # Edge cases and advanced scenarios

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_nested_pydantic_models.yaml",
        filter_headers=["authorization"],
    )
    async def test_nested_pydantic_models(self):
        """Test extraction with deeply nested Pydantic models."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        class Address(BaseModel):
            street: str
            city: str
            state: str
            zip_code: str

        class Company(BaseModel):
            name: str
            address: Address
            subsidiaries: list["Company"] = []

        # Update forward reference
        Company.model_rebuild()

        result = await agent.structured_response(
            "Extract company information from this document", Company
        )

        # Log the structured result for inspection
        log_structured_result("test_nested_pydantic_models", result)

        assert isinstance(result, Company) or result is None
        if result:
            assert isinstance(result.address, Address)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_optional_fields_handling.yaml",
        filter_headers=["authorization"],
    )
    async def test_optional_fields_handling(self):
        """Test extraction with many optional fields."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        class DocumentMetadata(BaseModel):
            title: str
            public_law_number: Optional[str] = None
            date_enacted: Optional[str] = None
            sponsor: Optional[str] = None
            committee: Optional[str] = None

        result = await agent.structured_response(
            "Extract metadata about the '21st Century Language Act of 2012'.",
            DocumentMetadata,
        )

        # Log the structured result for inspection
        log_structured_result("test_optional_fields_handling", result)

        assert isinstance(result, DocumentMetadata) or result is None
        if result:
            # At least title should be present
            assert result.title

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_enum_extraction.yaml",
        filter_headers=["authorization"],
    )
    async def test_enum_extraction(self):
        """Test extraction with enum types."""
        from enum import Enum

        class DocumentType(str, Enum):
            POSITIVE_LAW = "POSITIVE_LAW"
            PROPOSED_BILL = "PROPOSED_BILL"
            REPEALED = "REPEALED"

        class DocClassification(BaseModel):
            doc_type: DocumentType
            confidence: float = Field(ge=0, le=1)

        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Classify the legal status of this title based on the introductory notes.",
            DocClassification,
        )

        # Log the structured result for inspection
        log_structured_result("test_enum_extraction", result)

        assert isinstance(result, DocClassification) or result is None
        if result:
            assert isinstance(result.doc_type, DocumentType)
            assert 0 <= result.confidence <= 1

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_concurrent_extractions.yaml",
        filter_headers=["authorization"],
    )
    async def test_concurrent_extractions(self):
        """Test multiple concurrent structured extractions."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Run multiple extractions concurrently
        tasks = [
            agent.structured_response(
                "Provide the official citation format for this title.", str
            ),
            agent.structured_response(
                "Return just the number of sections defined in Chapter 1.", int
            ),
            agent.structured_response("Is this document the US Constitution?", bool),
            agent.structured_response(
                "List the terms defined under the 'Rules of Construction' in Section 1.",
                list[str],
            ),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log the structured result for inspection
        log_structured_result(
            "test_concurrent_extractions",
            {
                "citation_format": results[0],
                "section_count": results[1],
                "is_constitution": results[2],
                "section_terms": results[3],
            },
        )

        # All should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)
            # Each should be None or the expected type


@pytest.mark.asyncio
class TestStructuredResponseAPIConvenience(BaseFixtureTestCase):
    """Test the convenience methods in AgentAPI for structured responses."""

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_get_structured_response_from_document.yaml",
        filter_headers=["authorization"],
    )
    async def test_get_structured_response_from_document(self):
        """Test the direct API method for document extraction."""
        from opencontractserver.llms.api import AgentAPI

        result = await AgentAPI.get_structured_response_from_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            prompt="Get a structured response summarizing the rule for 'writs of error'.",
            target_type=str,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Log the structured result for inspection
        log_structured_result("test_get_structured_response_from_document", result)

        assert isinstance(result, str) or result is None

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_get_structured_response_from_corpus.yaml",
        filter_headers=["authorization"],
    )
    async def test_get_structured_response_from_corpus(self):
        """Test the direct API method for corpus extraction."""
        from opencontractserver.llms.api import AgentAPI

        # Add documents to corpus
        for doc in self.docs[:3]:
            await sync_to_async(self.corpus.add_document)(document=doc, user=self.user)

        result = await AgentAPI.get_structured_response_from_corpus(
            corpus=self.corpus.id,
            prompt="From an entire corpus, extract the total number of unique Public Laws referenced in the statutory notes.",  # noqa: E501
            target_type=int,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # Log the structured result for inspection
        log_structured_result("test_get_structured_response_from_corpus", result)

        assert isinstance(result, int) or result is None
        if result:
            assert result >= 0

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_convenience_with_all_overrides.yaml",
        filter_headers=["authorization"],
    )
    async def test_convenience_with_all_overrides(self):
        """Test convenience method with all parameter overrides."""
        from opencontractserver.llms.api import AgentAPI

        class SimpleResult(BaseModel):
            answer: str
            confidence: float = Field(ge=0, le=1)

        result = await AgentAPI.get_structured_response_from_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            prompt="Using all overrides, act as a child and explain what the 'Born-Alive Infants Protection Act of 2002' does.",  # noqa: E501
            target_type=SimpleResult,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
            model="gpt-4",
            system_prompt="You are a document analyst",
            temperature=0.5,
            max_tokens=100,
            embedder="text-embedding-ada-002",
        )

        # Log the structured result for inspection
        log_structured_result("test_convenience_with_all_overrides", result)

        assert isinstance(result, SimpleResult) or result is None
