"""GraphQL type definitions for the LLM configuration system.

Mirrors the shape of ``pipeline_types.py``:

* :class:`LLMSettingSchemaType` — one provider config field (analogue of
  ``ComponentSettingSchemaType``).
* :class:`LLMProviderType` — code-side provider class metadata + schema
  + has-secrets flag (analogue of ``PipelineComponentType``).
* :class:`RegisteredLLMType` — admin-curated DB row with resolvability
  metadata (no analogue in pipeline land — pipelines are pure code).
* :class:`LLMSettingsType` — the singleton (analogue of
  ``PipelineSettingsType``).

Per the design doc, secrets are NEVER exposed via GraphQL; only
``has_value`` / ``providers_with_secrets`` lists indicate presence.
"""

from __future__ import annotations

import graphene
from graphene.types.generic import GenericScalar

from config.graphql.user_types import UserType


class LLMSettingSchemaType(graphene.ObjectType):
    """Schema for one provider config field (api_key, base_url, …).

    Identical shape to :class:`ComponentSettingSchemaType` so admin UIs
    can reuse the same form-rendering code for both pipeline components
    and LLM providers.
    """

    name = graphene.String(
        required=True, description="Setting name (api_key, base_url, …)."
    )
    setting_type = graphene.String(
        required=True, description="Type: 'required', 'optional', or 'secret'."
    )
    python_type = graphene.String(
        description="Python type hint (e.g., 'str', 'int', 'bool')."
    )
    required = graphene.Boolean(
        required=True,
        description="Whether this setting must have a value to use the provider.",
    )
    description = graphene.String(
        description="Human-readable description of the setting."
    )
    default = GenericScalar(description="Default value if not configured.")
    env_var = graphene.String(
        description="Environment variable consulted at seed time."
    )
    has_value = graphene.Boolean(description="Whether a value is currently configured.")
    current_value = GenericScalar(
        description="Current value (always null for secrets to avoid exposure)."
    )


class LLMProviderType(graphene.ObjectType):
    """Code-side LLM provider class.

    Discovered from :mod:`opencontractserver.llms.providers` at runtime
    via the registry. The ``settings_schema`` field powers the per-
    provider config form in the admin UI.
    """

    name = graphene.String(
        required=True, description="Class name (e.g. OpenAIProvider)."
    )
    class_path = graphene.String(
        required=True,
        description="Full Python class path used as the registry key + the "
        "RegisteredLLM.provider_class_path foreign reference.",
    )
    title = graphene.String(description="Human-readable label.")
    description = graphene.String(description="Provider description.")
    pydantic_ai_prefix = graphene.String(
        required=True,
        description="pydantic-ai model-string prefix (e.g. 'openai', 'anthropic').",
    )
    default_models = graphene.List(
        graphene.String,
        description="Canonical model identifiers commonly registered under "
        "this provider. NOT a closed allow-list — operators can register "
        "any model_id they want.",
    )
    supports_structured_output = graphene.Boolean(required=True)
    supports_tools = graphene.Boolean(required=True)
    settings_schema = graphene.List(
        LLMSettingSchemaType,
        description="Schema of the provider's Settings dataclass (api_key, "
        "base_url, …) for rendering admin config forms.",
    )
    has_secrets = graphene.Boolean(
        required=True,
        description="True iff at least one secret is currently stored under "
        "this provider's class path in LLMSettings.encrypted_secrets.",
    )
    has_valid_secrets = graphene.Boolean(
        required=True,
        description="True iff a non-empty api_key is configured (the resolver's "
        "definition of 'has valid secrets'). Distinct from has_secrets, which "
        "just reports presence of any key in the bucket.",
    )


class RegisteredLLMType(graphene.ObjectType):
    """Admin-curated row representing one (provider, model) combination.

    Immutable: the row's fields never change after creation. "Edits"
    create a new row with ``previous_version`` pointing at the prior
    one. ``Column.preferred_llm`` and ``Datacell.executed_llm`` (Phase 4)
    use ``on_delete=PROTECT`` so historical references can never dangle.
    """

    id = graphene.ID(required=True)
    provider_class_path = graphene.String(required=True)
    provider = graphene.Field(
        LLMProviderType,
        description="The resolved provider class metadata (null if "
        "the provider has been de-registered since this row was created).",
    )
    model_id = graphene.String(required=True)
    display_name = graphene.String(required=True)
    pydantic_ai_model_string = graphene.String(
        description="Combined '<prefix>:<model_id>' string passed to pydantic-ai. "
        "Null if the provider is no longer registered."
    )

    is_enabled = graphene.Boolean(required=True)
    is_archived = graphene.Boolean(required=True)
    is_head = graphene.Boolean(
        required=True,
        description="True iff no newer version supersedes this row "
        "(i.e. this is the current version of its lineage).",
    )
    is_resolvable = graphene.Boolean(
        required=True,
        description="True iff lifecycle flags + provider registry + valid "
        "secrets all check out — the row can run an LLM call right now.",
    )
    unavailable_reason = graphene.String(
        description="Operator-actionable explanation of why this row is not "
        "resolvable (null if it is resolvable). Use verbatim in column-picker "
        "tooltips."
    )
    is_default_for_extracts = graphene.Boolean(
        required=True,
        description="True iff this row is currently set as "
        "LLMSettings.default_extract_llm.",
    )

    # Capability overrides.
    context_window = graphene.Int()
    supports_structured_output = graphene.Boolean(required=True)
    supports_tools = graphene.Boolean(required=True)
    max_output_tokens = graphene.Int()
    temperature_default = graphene.Float()
    notes = graphene.String()

    # Lineage (recursive CTE walks via opencontractserver.llm_configs).
    previous_version_id = graphene.ID(
        description="ID of the immediately prior version, if any."
    )

    # Audit.
    created = graphene.DateTime()
    modified = graphene.DateTime()
    creator = graphene.Field(UserType)


class LLMSettingsType(graphene.ObjectType):
    """The singleton — global LLM configuration.

    Mirrors :class:`PipelineSettingsType` in shape: a singleton with
    audit fields and a public list of which provider class paths have
    encrypted secrets stored (without ever leaking the secret values).
    """

    provider_settings = GenericScalar(
        description="Mapping of provider class paths to non-secret kwargs "
        "(base_url, organization_id, …). Secrets live in encrypted_secrets "
        "and are never exposed via this resolver."
    )
    default_extract_llm = graphene.Field(
        RegisteredLLMType,
        description="LLM used by extract tasks when a Column has no "
        "preferred_llm set. Null falls back to "
        "constants.extraction.DEFAULT_EXTRACT_MODEL.",
    )
    providers_with_secrets = graphene.List(
        graphene.String,
        required=True,
        description="Provider class paths that have at least one secret "
        "stored. Actual secret values are never exposed.",
    )

    modified = graphene.DateTime()
    modified_by = graphene.Field(UserType)
