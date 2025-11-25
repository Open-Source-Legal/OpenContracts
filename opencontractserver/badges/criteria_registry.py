"""
Registry of available badge criteria types with metadata and validation.

This module provides a declarative way to define badge criteria types, their
configuration fields, and validation rules. The registry is used for:
- Frontend discovery of available criteria types
- Multi-layer validation of criteria configurations
- Scope enforcement (global vs corpus badges)
- Type safety for criteria evaluation

Example usage:
    from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

    # Validate a criteria config
    is_valid, error = BadgeCriteriaRegistry.validate_config({
        "type": "message_count",
        "value": 10
    })

    # Get all criteria types
    all_types = BadgeCriteriaRegistry.all()

    # Get criteria types for a specific scope
    corpus_types = BadgeCriteriaRegistry.for_scope("corpus")
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CriteriaField:
    """
    Defines a configuration field for a criteria type.

    Attributes:
        name: Field identifier (used in criteria_config JSON)
        label: Human-readable label for UI
        field_type: Field data type ("number", "text", "boolean")
        required: Whether this field must be present
        description: Help text explaining the field
        min_value: Minimum allowed value (for number fields)
        max_value: Maximum allowed value (for number fields)
        allowed_values: List of allowed values (for enum-like text fields)
    """

    name: str
    label: str
    field_type: str  # "number", "text", "boolean"
    required: bool = True
    description: str = ""
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    allowed_values: Optional[list[str]] = None


@dataclass
class CriteriaTypeDefinition:
    """
    Defines a badge criteria type with its configuration schema.

    Attributes:
        type_id: Unique identifier for this criteria type
        name: Display name for UI
        description: Explanation of what this criteria checks
        scope: Where this criteria can be used ("global", "corpus", "both")
        fields: List of configuration fields required for this criteria
        implemented: Whether the evaluation logic is implemented
    """

    type_id: str
    name: str
    description: str
    scope: str  # "global", "corpus", "both"
    fields: list[CriteriaField]
    implemented: bool = True


class BadgeCriteriaRegistry:
    """
    Registry of all available badge criteria types.

    This class maintains a central registry of criteria type definitions and
    provides validation methods to ensure criteria configs are valid.
    """

    _criteria_types: dict[str, CriteriaTypeDefinition] = {}

    @classmethod
    def register(cls, criteria_def: CriteriaTypeDefinition) -> None:
        """
        Register a criteria type definition.

        Args:
            criteria_def: The criteria type definition to register
        """
        cls._criteria_types[criteria_def.type_id] = criteria_def

    @classmethod
    def get(cls, type_id: str) -> Optional[CriteriaTypeDefinition]:
        """
        Get a criteria type definition by ID.

        Args:
            type_id: The criteria type identifier

        Returns:
            The criteria type definition, or None if not found
        """
        return cls._criteria_types.get(type_id)

    @classmethod
    def all(cls) -> list[CriteriaTypeDefinition]:
        """
        Get all registered criteria types.

        Returns:
            List of all criteria type definitions
        """
        return list(cls._criteria_types.values())

    @classmethod
    def for_scope(cls, scope: str) -> list[CriteriaTypeDefinition]:
        """
        Get criteria types available for a specific scope.

        Args:
            scope: The scope to filter by ("global", "corpus", or "both")

        Returns:
            List of criteria types usable in the given scope
        """
        return [
            ct
            for ct in cls._criteria_types.values()
            if ct.scope == scope or ct.scope == "both"
        ]

    @classmethod
    def validate_config(cls, criteria_config: Any) -> tuple[bool, Optional[str]]:
        """
        Validate a criteria configuration against the registry.

        Performs comprehensive validation including:
        - Type checking (must be a dict)
        - Required 'type' field
        - Known criteria type
        - Implementation status
        - Required field presence
        - Field type validation
        - Range validation
        - No unexpected fields

        Args:
            criteria_config: The criteria configuration to validate

        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is None.

        Examples:
            >>> is_valid, error = BadgeCriteriaRegistry.validate_config({
            ...     "type": "message_count",
            ...     "value": 10
            ... })
            >>> print(is_valid)
            True

            >>> is_valid, error = BadgeCriteriaRegistry.validate_config({
            ...     "type": "unknown_type"
            ... })
            >>> print(error)
            Unknown criteria type 'unknown_type'. Valid types: ...
        """
        # Type check - must be a dict
        if not isinstance(criteria_config, dict):
            return False, "Criteria config must be a JSON object (dictionary)"

        # Check for 'type' field
        criteria_type = criteria_config.get("type")
        if not criteria_type:
            return False, "Missing required field 'type'"

        # Get the registered criteria type definition
        criteria_def = cls.get(criteria_type)
        if not criteria_def:
            valid_types = ", ".join(sorted(cls._criteria_types.keys()))
            return (
                False,
                f"Unknown criteria type '{criteria_type}'. Valid types: {valid_types}",
            )

        # Check if implemented
        if not criteria_def.implemented:
            return (
                False,
                f"Criteria type '{criteria_type}' is not yet implemented. "
                f"This criteria type is registered but the evaluation logic has not been completed.",
            )

        # Validate required fields are present and have correct types
        for field_def in criteria_def.fields:
            field_name = field_def.name
            field_value = criteria_config.get(field_name)

            # Check required fields are present
            if field_def.required and field_value is None:
                return (
                    False,
                    f"Missing required field '{field_name}' for criteria type '{criteria_type}'",
                )

            # Validate field value if present
            if field_value is not None:
                # Type validation
                if field_def.field_type == "number":
                    if not isinstance(field_value, (int, float)):
                        return (
                            False,
                            f"Field '{field_name}' must be a number, got {type(field_value).__name__}",
                        )

                    # Range validation
                    if (
                        field_def.min_value is not None
                        and field_value < field_def.min_value
                    ):
                        return (
                            False,
                            f"Field '{field_name}' must be >= {field_def.min_value}, got {field_value}",
                        )

                    if (
                        field_def.max_value is not None
                        and field_value > field_def.max_value
                    ):
                        return (
                            False,
                            f"Field '{field_name}' must be <= {field_def.max_value}, got {field_value}",
                        )

                elif field_def.field_type == "text":
                    if not isinstance(field_value, str):
                        return (
                            False,
                            f"Field '{field_name}' must be a string, got {type(field_value).__name__}",
                        )

                    # Allowed values validation
                    if (
                        field_def.allowed_values
                        and field_value not in field_def.allowed_values
                    ):
                        allowed = ", ".join(field_def.allowed_values)
                        return (
                            False,
                            f"Field '{field_name}' must be one of: {allowed}. Got '{field_value}'",
                        )

                elif field_def.field_type == "boolean":
                    if not isinstance(field_value, bool):
                        return (
                            False,
                            f"Field '{field_name}' must be a boolean, got {type(field_value).__name__}",
                        )

        # Check for unexpected fields
        expected_fields = {"type"} | {f.name for f in criteria_def.fields}
        unexpected = set(criteria_config.keys()) - expected_fields
        if unexpected:
            unexpected_list = ", ".join(sorted(unexpected))
            expected_list = ", ".join(sorted(expected_fields))
            return (
                False,
                f"Unexpected fields: {unexpected_list}. Expected fields: {expected_list}",
            )

        return True, None


# Register all available criteria types
# These definitions drive both frontend UI and backend validation

BadgeCriteriaRegistry.register(
    CriteriaTypeDefinition(
        type_id="first_post",
        name="First Post",
        description="Automatically award when user creates their first message",
        scope="both",
        fields=[],  # No configuration needed
        implemented=True,
    )
)

BadgeCriteriaRegistry.register(
    CriteriaTypeDefinition(
        type_id="message_count",
        name="Message Count",
        description="Award when user reaches a certain number of messages",
        scope="both",
        fields=[
            CriteriaField(
                name="value",
                label="Number of Messages",
                field_type="number",
                required=True,
                description="Minimum number of messages the user must create to earn this badge",
                min_value=1,
                max_value=10000,
            )
        ],
        implemented=True,
    )
)

BadgeCriteriaRegistry.register(
    CriteriaTypeDefinition(
        type_id="corpus_contribution",
        name="Corpus Contribution",
        description="Award when user contributes documents and/or annotations to a corpus",
        scope="corpus",  # Only valid for corpus-specific badges
        fields=[
            CriteriaField(
                name="value",
                label="Total Contributions",
                field_type="number",
                required=True,
                description="Minimum number of documents uploaded plus annotations created in the corpus",
                min_value=1,
                max_value=1000,
            )
        ],
        implemented=True,
    )
)

BadgeCriteriaRegistry.register(
    CriteriaTypeDefinition(
        type_id="reputation_threshold",
        name="Reputation Threshold",
        description="Award when user reaches a reputation score based on upvotes/downvotes received",
        scope="both",
        fields=[
            CriteriaField(
                name="value",
                label="Reputation Points",
                field_type="number",
                required=True,
                description="Minimum reputation score required to earn this badge",
                min_value=1,
                max_value=100000,
            )
        ],
        implemented=True,
    )
)

BadgeCriteriaRegistry.register(
    CriteriaTypeDefinition(
        type_id="message_upvotes",
        name="Message Upvotes",
        description="Award when user has a message with a certain number of upvotes",
        scope="both",
        fields=[
            CriteriaField(
                name="value",
                label="Number of Upvotes",
                field_type="number",
                required=True,
                description="Minimum number of upvotes on a single message to earn this badge",
                min_value=1,
                max_value=10000,
            )
        ],
        implemented=True,
    )
)
