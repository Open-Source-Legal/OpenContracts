"""
Example usage of the structured response API for one-shot data extraction.

This demonstrates how to extract structured data from documents and corpuses
without maintaining conversation history.
"""

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from opencontractserver.llms import agents
from opencontractserver.llms.api import AgentAPI
from opencontractserver.llms.types import AgentFramework


# Define your data models
class ContractParty(BaseModel):
    """A party in a legal contract."""

    name: str = Field(description="Full legal name of the party")
    role: str = Field(description="Role (e.g., 'Buyer', 'Seller', 'Licensor')")
    address: Optional[str] = Field(None, description="Address if mentioned")


class ContractSummary(BaseModel):
    """Structured summary of a contract."""

    title: str = Field(description="Contract title or type")
    parties: list[ContractParty] = Field(description="All parties involved")
    effective_date: Optional[str] = Field(
        None, description="When contract becomes effective"
    )
    value: Optional[float] = Field(None, description="Total contract value in USD")
    key_terms: list[str] = Field(description="Key terms and conditions")


class RiskAssessment(BaseModel):
    """Risk assessment for a document."""

    risk_level: str = Field(
        description="Overall risk level: 'Low', 'Medium', or 'High'"
    )
    risk_factors: list[str] = Field(description="Specific risk factors identified")
    recommendations: list[str] = Field(description="Recommendations to mitigate risks")
    confidence: float = Field(ge=0, le=1, description="Confidence in assessment (0-1)")


async def example_document_extraction():
    """Example: Extract structured data from a single document."""

    # Method 1: Using agent directly
    agent = await agents.for_document(
        document=123,  # Your document ID
        corpus=1,  # Your corpus ID
        framework=AgentFramework.PYDANTIC_AI,
    )

    # Extract basic data types
    title = await agent.structured_response("What is the title of this document?", str)
    print(f"Document title: {title}")

    # Extract integers
    page_count = await agent.structured_response(
        "How many pages does this document have?", int
    )
    print(f"Page count: {page_count}")

    # Extract complex structured data
    contract_summary = await agent.structured_response(
        "Analyze this contract and extract key information", ContractSummary
    )

    if contract_summary:
        print("\nContract Summary:")
        print(f"Title: {contract_summary.title}")
        print(f"Parties: {len(contract_summary.parties)}")
        for party in contract_summary.parties:
            print(f"  - {party.name} ({party.role})")
        print(
            f"Value: ${contract_summary.value:,.2f}"
            if contract_summary.value
            else "Value: Not specified"
        )
        print(f"Key terms: {', '.join(contract_summary.key_terms[:3])}...")

    # Extract with custom parameters
    risk_assessment = await agent.structured_response(
        "Perform a risk assessment of this document",
        RiskAssessment,
        temperature=0.2,  # Lower temperature for more consistent analysis
        system_prompt="You are a legal risk assessment expert. Be thorough and conservative in your analysis.",
    )

    if risk_assessment:
        print("\nRisk Assessment:")
        print(f"Risk Level: {risk_assessment.risk_level}")
        print(f"Confidence: {risk_assessment.confidence:.2%}")
        print(f"Top risks: {', '.join(risk_assessment.risk_factors[:3])}")


async def example_corpus_extraction():
    """Example: Extract insights from an entire corpus."""

    class CorpusStatistics(BaseModel):
        """Statistics about a document corpus."""

        total_documents: int
        total_pages: int
        document_types: list[str]
        date_range: str
        total_value: Optional[float] = None

    class ComplianceCheck(BaseModel):
        """Compliance check results."""

        compliant_documents: int
        non_compliant_documents: int
        compliance_rate: float
        common_issues: list[str]
        recommendations: list[str]

    # Using corpus agent
    agent = await agents.for_corpus(
        corpus=456, framework=AgentFramework.PYDANTIC_AI  # Your corpus ID
    )

    # Extract corpus-wide statistics
    stats = await agent.structured_response(
        "Analyze this corpus and provide statistics", CorpusStatistics
    )

    if stats:
        print("\nCorpus Statistics:")
        print(f"Documents: {stats.total_documents}")
        print(f"Total pages: {stats.total_pages}")
        print(f"Document types: {', '.join(stats.document_types)}")
        print(f"Date range: {stats.date_range}")

    # Perform compliance check across corpus
    compliance = await agent.structured_response(
        "Check all documents in this corpus for standard compliance requirements",
        ComplianceCheck,
        model="gpt-4",  # Use more capable model for complex analysis
        temperature=0.1,  # Low temperature for consistency
    )

    if compliance:
        print("\nCompliance Check:")
        print(f"Compliance rate: {compliance.compliance_rate:.1%}")
        print(f"Common issues: {', '.join(compliance.common_issues[:3])}")


async def example_convenience_api():
    """Example: Using the convenience API methods."""

    # Direct extraction from document without creating agent
    result = await AgentAPI.get_structured_response_from_document(
        document=789,
        corpus=1,
        prompt="Extract the main parties and their roles",
        target_type=list[ContractParty],
        framework=AgentFramework.PYDANTIC_AI,
        temperature=0.3,
    )

    if result:
        print(f"\nParties found: {len(result)}")
        for party in result:
            print(f"  - {party.name}: {party.role}")

    # Direct extraction from corpus
    class CorpusThemes(BaseModel):
        """Themes identified across a corpus."""

        primary_theme: str
        secondary_themes: list[str]
        recurring_topics: list[str]
        anomalies: list[str]

    themes = await AgentAPI.get_structured_response_from_corpus(
        corpus=456,
        prompt="Identify the main themes and topics across all documents",
        target_type=CorpusThemes,
        framework=AgentFramework.PYDANTIC_AI,
    )

    if themes:
        print("\nCorpus Themes:")
        print(f"Primary: {themes.primary_theme}")
        print(f"Secondary: {', '.join(themes.secondary_themes[:3])}")
        print(f"Anomalies: {', '.join(themes.anomalies)}")


async def example_error_handling():
    """Example: Handling extraction failures gracefully."""

    agent = await agents.for_document(
        document=123, corpus=1, framework=AgentFramework.PYDANTIC_AI
    )

    # This might fail due to model issues or parsing errors
    result = await agent.structured_response(
        "Extract something very specific that might not exist",
        ComplexModel,  # Assuming ComplexModel is defined
        model="gpt-3.5-turbo",
    )

    # The API returns None on failure instead of raising exceptions
    if result is None:
        print("Extraction failed - using fallback logic")
        # Implement your fallback logic here
    else:
        print(f"Successfully extracted: {result}")


async def example_batch_extraction():
    """Example: Extract data from multiple documents efficiently."""

    document_ids = [123, 124, 125]  # Your document IDs
    corpus_id = 1

    # Run extractions concurrently
    tasks = []
    for doc_id in document_ids:
        agent = await agents.for_document(
            document=doc_id, corpus=corpus_id, framework=AgentFramework.PYDANTIC_AI
        )

        task = agent.structured_response("Extract contract summary", ContractSummary)
        tasks.append(task)

    # Wait for all extractions to complete
    results = await asyncio.gather(*tasks)

    # Process results
    valid_summaries = [r for r in results if r is not None]
    print(f"\nProcessed {len(document_ids)} documents")
    print(f"Successful extractions: {len(valid_summaries)}")

    # Aggregate data
    total_value = sum(s.value for s in valid_summaries if s.value)
    all_parties: set[str] = set()
    for summary in valid_summaries:
        all_parties.update(party.name for party in summary.parties)

    print(f"Total contract value: ${total_value:,.2f}")
    print(f"Unique parties: {len(all_parties)}")


# Complex model definition for demonstration
class ComplexModel(BaseModel):
    """Example of a complex nested model."""

    class NestedData(BaseModel):
        field1: str
        field2: int
        field3: list[float]

    main_data: str
    nested: NestedData
    optional_nested: Optional[NestedData] = None
    metadata: dict[str, str]


if __name__ == "__main__":
    # Run examples
    asyncio.run(example_document_extraction())
    # asyncio.run(example_corpus_extraction())
    # asyncio.run(example_convenience_api())
    # asyncio.run(example_batch_extraction())
