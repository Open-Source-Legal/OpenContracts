"""Versioned, secret-free policy for the supported bounded processing adapter.

Only first-party OpenAI text embeddings currently expose bounded input and
accounted usage. Unpriced/custom providers, parsing, multimodal fallbacks and
automatic corpus actions are deliberately unavailable to policy-bound runs.
External worker preparation and infrastructure costs are explicitly excluded.
"""

import hashlib
import inspect
import json
import re
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings

from opencontractserver.annotations.models import EMBEDDING_DIMENSIONS
from opencontractserver.constants.document_processing import (
    OPENAI_EMBEDDER_MAX_INPUT_CHARS,
)
from opencontractserver.constants.embeddings import (
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
from opencontractserver.pipeline.utils import get_component_by_name
from opencontractserver.utils.embedding_identity import embedding_configuration

SUPPORTED_DIMENSIONS = {dimension for dimension, _ in EMBEDDING_DIMENSIONS}


class RunPolicyError(ValueError):
    """Only fixed, credential-free error codes may cross this boundary."""


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
    if path != OPENAI_EMBEDDER_PATH or not pipeline.is_component_enabled(path):
        raise RunPolicyError("unbounded_provider")
    try:
        cls = get_component_by_name(path)
        if cls is not OpenAIEmbedder:
            raise RunPolicyError("unbounded_provider")
        provider = OpenAIEmbedder(
            component_settings=pipeline.get_full_component_settings(path)
        )
        config = provider._effective_settings
        model = config.openai_embedding_model
        base_url = config.openai_api_base_url
        if model not in OPENAI_MODEL_DIMENSIONS or base_url not in (
            "",
            OPENAI_API_BASE_URL,
        ):
            raise RunPolicyError("unbounded_provider")
        if (
            provider.vector_size not in SUPPORTED_DIMENSIONS
            or provider.vector_size > OPENAI_MODEL_DIMENSIONS[model]
        ):
            raise RunPolicyError("unsupported_embedding_dimension")
        configuration = embedding_configuration(provider)
        if not configuration:
            raise RunPolicyError("provider_configuration_unavailable")
        descriptor = {
            "path": path,
            "model": model,
            "dimension": provider.vector_size,
            "configuration": configuration,
            "endpoint": OPENAI_API_BASE_URL,
            "implementation": hashlib.sha256(
                Path(inspect.getfile(cls)).read_bytes()
            ).hexdigest(),
        }
        return descriptor, provider
    except RunPolicyError:
        raise
    except Exception:
        raise RunPolicyError("provider_configuration_unavailable") from None


def pricing_for(model):
    table = getattr(settings, "INGESTION_RUN_PRICING", {})
    try:
        version = table["version"]
        rate = money(table["openai_usd_per_million_tokens"][model])
        if (
            not isinstance(version, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", version)
            or rate <= 0
        ):
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
        policy["pricing"] = pricing_for(descriptor["model"])
    return policy


def validate_execution(run):
    if digest(run.policy) != run.policy_digest:
        raise RunPolicyError("policy_integrity_violation")
    if run.policy["embedding_mode"] == "server":
        descriptor, provider = resolve_provider(run.corpus)
        if descriptor != run.policy["provider"]:
            raise RunPolicyError("provider_configuration_changed")
        if pricing_for(descriptor["model"]) != run.policy["pricing"]:
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
