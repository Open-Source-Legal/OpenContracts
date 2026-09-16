"""Versioned, secret-free policy for the supported bounded processing adapter.

First-party OpenAI and explicitly declared self-hosted sentence embeddings expose
bounded input and accounted provider fees. Unpriced/custom providers, parsing,
multimodal fallbacks and automatic corpus actions are unavailable to bound runs.
External worker preparation and infrastructure costs are explicitly excluded.
"""

import hashlib
import json
import re
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.conf import settings

from opencontractserver.annotations.models import EMBEDDING_DIMENSIONS
from opencontractserver.constants.document_processing import (
    OPENAI_EMBEDDER_MAX_INPUT_CHARS,
)
from opencontractserver.constants.embeddings import (
    MICROSERVICE_EMBEDDER_PATH,
    MICROSERVICE_MODEL_REVISION_PATTERN,
    OPENAI_API_BASE_URL,
    OPENAI_EMBEDDER_PATH,
    OPENAI_MODEL_DIMENSIONS,
)
from opencontractserver.constants.ingestion_runs import (
    MAX_ALLOWANCE_USD,
    MAX_PREPARATIONS,
    TOKENS_PER_PRICING_UNIT,
    USD_QUANTUM,
)
from opencontractserver.documents.models import PipelineSettings
from opencontractserver.pipeline.embedders.openai_embedder import OpenAIEmbedder
from opencontractserver.pipeline.embedders.sent_transformer_microservice import (
    MicroserviceEmbedder,
)
from opencontractserver.pipeline.utils import get_component_by_name
from opencontractserver.utils.embedding_identity import embedding_configuration
from opencontractserver.utils.public_errors import PublicError

SUPPORTED_DIMENSIONS = {dimension for dimension, _ in EMBEDDING_DIMENSIONS}


class RunPolicyError(PublicError):
    """Only fixed, credential-free error codes may cross this boundary."""

    default_code = "run_policy_error"
    public_codes = frozenset(
        {
            "ceiling_cannot_decrease",
            "embedding_policy_mismatch",
            "invalid_embedding_result",
            "invalid_money",
            "invalid_preparation_policy",
            "invalid_run_action",
            "invalid_usage_receipt",
            "operation_input_changed",
            "operation_not_retryable",
            "policy_integrity_violation",
            "preparation_policy_mismatch",
            "pricing_changed",
            "prohibited_fallback",
            "prohibited_multimodal_fallback",
            "prohibited_parse",
            "provider_configuration_changed",
            "provider_configuration_unavailable",
            "provider_model_revision_required",
            "retry_exhausted",
            "run_cancelled",
            "run_identity_conflict",
            "run_not_active",
            "run_not_found",
            "run_requires_idempotency_key",
            "unbounded_provider",
            "unknown_pricing",
            "unsupported_embedding_dimension",
            "usage_exceeds_reservation",
        }
    )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > MAX_ALLOWANCE_USD:
            raise ValueError
        if amount != amount.quantize(USD_QUANTUM):
            raise ValueError
        return amount
    except (InvalidOperation, ValueError):
        raise RunPolicyError("invalid_money") from None


def resolve_provider(corpus):
    """Resolve fresh DB settings, then instantiate from that fixed snapshot.

    No process cache or mutable configuration is consulted by the resulting
    instance. Secrets live only in memory and never enter the descriptor.
    """
    pipeline = PipelineSettings.get_instance(use_cache=False)
    corpus.refresh_from_db(fields=["preferred_embedder"])
    path = corpus.preferred_embedder or pipeline.get_default_embedder()
    supported: dict[str, type[OpenAIEmbedder] | type[MicroserviceEmbedder]] = {
        OPENAI_EMBEDDER_PATH: OpenAIEmbedder,
        MICROSERVICE_EMBEDDER_PATH: MicroserviceEmbedder,
    }
    if path not in supported or not pipeline.is_component_enabled(path):
        raise RunPolicyError("unbounded_provider")
    try:
        cls = get_component_by_name(path)
        if cls is not supported[path]:
            raise RunPolicyError("unbounded_provider")
        provider = supported[path](
            component_settings=pipeline.get_full_component_settings(path)
        )
        if provider.vector_size not in SUPPORTED_DIMENSIONS:
            raise RunPolicyError("unsupported_embedding_dimension")
        if isinstance(provider, OpenAIEmbedder):
            config = provider._effective_settings
            model = config.openai_embedding_model
            if (
                model not in OPENAI_MODEL_DIMENSIONS
                or config.openai_api_base_url
                not in (
                    "",
                    OPENAI_API_BASE_URL,
                )
            ):
                raise RunPolicyError("unbounded_provider")
            if provider.vector_size > OPENAI_MODEL_DIMENSIONS[model]:
                raise RunPolicyError("unsupported_embedding_dimension")
            endpoint = OPENAI_API_BASE_URL
        else:
            service_config = provider.settings
            if not isinstance(service_config, MicroserviceEmbedder.Settings):
                raise RunPolicyError("provider_configuration_unavailable")
            if service_config.no_external_provider_fees is not True:
                raise RunPolicyError("unknown_pricing")
            # Configure through the pipeline settings GUI/API. The existing
            # deployment revision setting remains a backwards-compatible fallback.
            model = service_config.embedding_model_revision or getattr(
                settings, "EMBEDDING_MODEL_REVISIONS", {}
            ).get(path, "")
            if not isinstance(model, str) or not re.fullmatch(
                MICROSERVICE_MODEL_REVISION_PATTERN, model
            ):
                raise RunPolicyError("provider_model_revision_required")
            url = service_config.embeddings_microservice_url
            parsed = urlsplit(url)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise RunPolicyError("unbounded_provider")
            endpoint = digest(url)
        configuration = embedding_configuration(provider)
        if not configuration:
            raise RunPolicyError("provider_configuration_unavailable")
        descriptor = {
            "path": path,
            "model": model,
            "dimension": provider.vector_size,
            "configuration": configuration,
            "endpoint": endpoint,
            "implementation": provider.accounting_version,
        }
        return descriptor, provider
    except RunPolicyError:
        raise
    except Exception:
        raise RunPolicyError("provider_configuration_unavailable") from None


def pricing_for(model, *, provider_path=OPENAI_EMBEDDER_PATH):
    if provider_path == MICROSERVICE_EMBEDDER_PATH:
        # resolve_provider requires the operator's explicit fee declaration.
        return {
            "version": "self-hosted-no-provider-fees-v1",
            "currency": "USD",
            "usd_per_million_tokens": "0",
            "reservation_basis": "no-external-provider-fees-v1",
            "accounting_basis": "no-external-provider-fees-v1",
            "sdk_retries": 0,
        }
    table = getattr(settings, "INGESTION_RUN_PRICING", {})
    try:
        version = table["version"]
        if not isinstance(version, str) or not re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,100}", version
        ):
            raise ValueError
        if provider_path != OPENAI_EMBEDDER_PATH:
            raise ValueError
        rate = money(table["openai_usd_per_million_tokens"][model])
        if rate <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise RunPolicyError("unknown_pricing") from None
    return {
        "version": version,
        "currency": "USD",
        "usd_per_million_tokens": format(rate.normalize(), "f"),
        "reservation_basis": "utf8-byte-token-upper-bound-v1",
        "accounting_basis": "provider-prompt-tokens-v1",
        "sdk_retries": 0,
    }


def build_policy(corpus, *, preparations, embedding_mode="prepared", fallback="forbid"):
    if embedding_mode not in ("prepared", "server") or fallback != "forbid":
        raise RunPolicyError("prohibited_fallback")
    if (
        not isinstance(preparations, list)
        or not 1 <= len(preparations) <= MAX_PREPARATIONS
    ):
        raise RunPolicyError("invalid_preparation_policy")
    fields = {
        "fingerprint",
        "parser_name",
        "parser_version",
        "embedder_path",
        "embedding_dimension",
        "embedding_model_fingerprint",
    }
    for preparation in preparations:
        if not isinstance(preparation, dict) or set(preparation) != fields:
            raise RunPolicyError("invalid_preparation_policy")
        for key in ("fingerprint", "embedding_model_fingerprint"):
            if not isinstance(preparation[key], str) or not re.fullmatch(
                r"[a-f0-9]{64}", preparation[key]
            ):
                raise RunPolicyError("invalid_preparation_policy")
        for key in ("parser_name", "parser_version", "embedder_path"):
            if not isinstance(preparation[key], str) or not re.fullmatch(
                r"[A-Za-z0-9_. :/-]{0,200}", preparation[key]
            ):
                raise RunPolicyError("invalid_preparation_policy")
        if type(preparation["embedding_dimension"]) is not int or preparation[
            "embedding_dimension"
        ] not in SUPPORTED_DIMENSIONS | {0}:
            raise RunPolicyError("invalid_preparation_policy")
    policy = {
        "version": 1,
        "preparations": preparations,
        "embedding_mode": embedding_mode,
        "permitted_stages": ["store"]
        + (["embed_text"] if embedding_mode == "server" else []),
        "fallback": "forbid",
        "excluded_costs": [
            "external_worker_preparation",
            "infrastructure",
            "interactive_user_work",
        ],
        "suppressed_stages": [
            "parse",
            "convert",
            "thumbnail",
            "corpus_action",
            "multimodal_embedding",
        ],
        "pricing": {"version": "no-server-provider-v1", "currency": "USD"},
    }
    if embedding_mode == "server":
        descriptor, _ = resolve_provider(corpus)
        policy["provider"] = descriptor
        policy["pricing"] = pricing_for(
            descriptor["model"], provider_path=descriptor["path"]
        )
    return policy


def validate_execution(run):
    if digest(run.policy) != run.policy_digest:
        raise RunPolicyError("policy_integrity_violation")
    if run.policy["embedding_mode"] == "server":
        descriptor, provider = resolve_provider(run.corpus)
        if descriptor != run.policy["provider"]:
            raise RunPolicyError("provider_configuration_changed")
        if (
            pricing_for(descriptor["model"], provider_path=descriptor["path"])
            != run.policy["pricing"]
        ):
            raise RunPolicyError("pricing_changed")
        return provider
    return None


def validate_preparation(run, metadata):
    matched = next(
        (
            p
            for p in run.policy["preparations"]
            if p["fingerprint"] == metadata.get("preparation_identity")
        ),
        None,
    )
    if matched is None or any(
        metadata.get(k) != matched[k] for k in ("parser_name", "parser_version")
    ):
        raise RunPolicyError("preparation_policy_mismatch")
    embeddings = metadata.get("embeddings")
    if embeddings:
        vectors = [
            embeddings.get("document_embedding"),
            *embeddings.get("annotation_embeddings", {}).values(),
        ]
        if embeddings.get("embedder_path") != matched["embedder_path"] or any(
            v is not None and len(v) != matched["embedding_dimension"] for v in vectors
        ):
            raise RunPolicyError("embedding_policy_mismatch")
    validate_execution(run)


def bounded_text(text):
    return text[:OPENAI_EMBEDDER_MAX_INPUT_CHARS]


def token_cost(policy, tokens):
    return (
        Decimal(tokens)
        * Decimal(policy["pricing"]["usd_per_million_tokens"])
        / TOKENS_PER_PRICING_UNIT
    ).quantize(USD_QUANTUM, rounding=ROUND_CEILING)
