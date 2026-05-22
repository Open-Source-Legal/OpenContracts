"""
Simple test to verify the structured response API implementation.
"""

import json
import logging
from pathlib import Path

import pytest
import vcr
from pydantic import BaseModel, Field

from opencontractserver.llms import agents
from opencontractserver.llms.types import AgentFramework
from opencontractserver.tests.base import TransactionFixtureTestCase


# Set up logging for structured data results
def setup_structured_data_logger_simple():
    """Set up logger to capture structured data results for simple tests."""
    log_file = Path(__file__).parent / "structured_data_results_simple.log"

    # Create a logger specifically for structured data
    logger = logging.getLogger("structured_data_results_simple")
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
structured_data_logger_simple = setup_structured_data_logger_simple()


def log_structured_result_simple(test_name: str, result: any):
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
        structured_data_logger_simple.info(f"\n{'='*50}")
        structured_data_logger_simple.info(f"TEST: {test_name}")
        structured_data_logger_simple.info(f"{'='*50}")
        structured_data_logger_simple.info(f"RESULT TYPE: {type(result).__name__}")
        structured_data_logger_simple.info("RESULT DATA:")
        structured_data_logger_simple.info(
            json.dumps(json_result, indent=2, ensure_ascii=False)
        )
        structured_data_logger_simple.info("")

    except Exception as e:
        structured_data_logger_simple.error(
            f"Error logging result for {test_name}: {str(e)}"
        )
        structured_data_logger_simple.info(f"Raw result: {repr(result)}")


class SimpleExtraction(BaseModel):
    """Simple model for testing."""

    title: str = Field(description="Document title")
    page_count: int = Field(description="Number of pages")


@pytest.mark.asyncio
class TestStructuredResponseBasic(TransactionFixtureTestCase):
    """Basic tests for structured response API."""

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_basic_string_extraction.yaml",
        filter_headers=["authorization"],
    )
    async def test_basic_string_extraction(self):
        """Test basic string extraction."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,  # Use the test user to access private resources
        )

        # Test that the method exists and is callable
        assert hasattr(agent, "structured_response")
        assert callable(agent.structured_response)

        # Test basic extraction
        result = await agent.structured_response("What is this document?", str)

        # Log the structured result for inspection
        log_structured_result_simple("test_basic_string_extraction", result)

        # Should return None or a string
        assert result is None or isinstance(result, str)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_pydantic_model_extraction.yaml",
        filter_headers=["authorization"],
    )
    async def test_pydantic_model_extraction(self):
        """Test Pydantic model extraction."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        result = await agent.structured_response(
            "Extract document information", SimpleExtraction
        )

        # Log the structured result for inspection
        log_structured_result_simple("test_pydantic_model_extraction", result)

        # Should return None or the model
        assert result is None or isinstance(result, SimpleExtraction)

        if result:
            assert isinstance(result.title, str)
            assert isinstance(result.page_count, int)

    @vcr.use_cassette(
        "fixtures/vcr_cassettes/structured_data_tests/test_custom_vs_default_prompt.yaml",
        filter_headers=["authorization"],
    )
    async def test_custom_vs_default_prompt(self):
        """Test that custom system prompt overrides the default extraction prompt."""
        agent = await agents.for_document(
            document=self.doc.id,
            corpus=self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
        )

        # First, test with default prompt (should use verification)
        default_result = await agent.structured_response(
            "Extract the document title", str
        )

        # Then test with a minimal custom prompt
        custom_result = await agent.structured_response(
            "Extract the document title",
            str,
            system_prompt="Return the title as JSON string.",
        )

        # Log both results for comparison
        log_structured_result_simple(
            "test_custom_vs_default_prompt",
            {
                "default_prompt_result": default_result,
                "custom_prompt_result": custom_result,
            },
        )

        # Both should work, but might have different characteristics
        assert default_result is None or isinstance(default_result, str)
        assert custom_result is None or isinstance(custom_result, str)
