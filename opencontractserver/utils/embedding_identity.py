"""Identify the settings snapshot that actually produced a vector."""

import dataclasses
import hashlib
import json

from django.conf import settings


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
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def valid_embeddings(path, dimension, configuration):
    """pgvector enforces finite values/dimension; cosine search also needs nonzero vectors."""
    from django.db.models import F, FloatField, Func

    from opencontractserver.annotations.models import Embedding
    from opencontractserver.constants.search import DIM_TO_FIELD_MAP

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
