"""Identify the settings snapshot that actually produced a vector."""

import dataclasses
import hashlib
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def embedding_configuration(embedder) -> str:
    """Hash model, dimension and non-secret settings; never expose credentials.

    Operators must bump EMBEDDING_MODEL_REVISIONS when a service changes its
    model in place without changing its URL or component settings.
    """
    path = f"{type(embedder).__module__}.{type(embedder).__name__}"
    config = embedder.get_component_settings()
    if dataclasses.is_dataclass(embedder.settings) and not isinstance(
        embedder.settings, type
    ):
        config = {**dataclasses.asdict(embedder.settings), **config}
    schema = embedder.get_settings_schema()
    config = {
        key: value
        for key, value in config.items()
        if schema.get(key, {}).get("setting_type") != "secret"
        and not any(
            word in key.lower() for word in ("key", "token", "secret", "password")
        )
    }
    payload = [
        path,
        embedder.vector_size,
        config,
        getattr(settings, "EMBEDDING_MODEL_REVISIONS", {}).get(path, ""),
    ]
    try:
        encoded = json.dumps(payload, sort_keys=True).encode()
    except (TypeError, ValueError):
        logger.warning("Cannot fingerprint settings for embedder %s", path)
        return ""
    return hashlib.sha256(encoded).hexdigest()


def valid_embeddings(path, dimension, configuration):
    """pgvector enforces finite values/dimension; cosine search also needs nonzero vectors."""
    from django.db.models import F, FloatField, Func

    from opencontractserver.annotations.models import Embedding
    from opencontractserver.constants.search import DIM_TO_FIELD_MAP

    if not configuration:
        # Empty fingerprints represent unverified vectors, never readiness.
        raise ValueError("valid_embeddings requires a configuration fingerprint")
    field = DIM_TO_FIELD_MAP[dimension]
    return (
        Embedding.objects.filter(
            embedder_path=path,
            configuration=configuration,
            **{f"{field}__isnull": False},
        )
        .annotate(
            _norm=Func(F(field), function="vector_norm", output_field=FloatField())
        )
        .filter(_norm__gt=0)
    )


def embeddable_annotations(annotations):
    """Exclude empty text, including tabs and form feeds that SQL TRIM leaves."""
    from django.db.models import Q

    return annotations.exclude(Q(raw_text__isnull=True) | Q(raw_text__regex=r"^\s*$"))
