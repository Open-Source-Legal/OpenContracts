"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import strawberry

from config.graphql.core.relay import (
    register_type,
)


@strawberry.type(
    name="OGCorpusMetadataType",
    description="Minimal corpus metadata for Open Graph previews - public entities only.",
)
class OGCorpusMetadataType:
    title: str | None = strawberry.field(
        name="title", description="Corpus title", default=None
    )
    description: str | None = strawberry.field(
        name="description", description="Corpus description (truncated)", default=None
    )
    icon_url: str | None = strawberry.field(
        name="iconUrl", description="URL to corpus icon/thumbnail", default=None
    )
    document_count: int | None = strawberry.field(
        name="documentCount", description="Number of documents in corpus", default=None
    )
    creator_name: str | None = strawberry.field(
        name="creatorName", description="Public slug of corpus creator", default=None
    )
    is_public: bool | None = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGCorpusMetadataType", OGCorpusMetadataType, model=None)


@strawberry.type(
    name="OGDocumentMetadataType",
    description="Minimal document metadata for Open Graph previews - public entities only.",
)
class OGDocumentMetadataType:
    title: str | None = strawberry.field(
        name="title", description="Document title", default=None
    )
    description: str | None = strawberry.field(
        name="description", description="Document description (truncated)", default=None
    )
    icon_url: str | None = strawberry.field(
        name="iconUrl", description="URL to document thumbnail", default=None
    )
    corpus_title: str | None = strawberry.field(
        name="corpusTitle",
        description="Title of parent corpus (if document is in a corpus)",
        default=None,
    )
    corpus_description: str | None = strawberry.field(
        name="corpusDescription",
        description="Description of parent corpus (if document is in a corpus)",
        default=None,
    )
    creator_name: str | None = strawberry.field(
        name="creatorName", description="Public slug of document creator", default=None
    )
    is_public: bool | None = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGDocumentMetadataType", OGDocumentMetadataType, model=None)


@strawberry.type(
    name="OGThreadMetadataType",
    description="Minimal discussion thread metadata for Open Graph previews.",
)
class OGThreadMetadataType:
    title: str | None = strawberry.field(
        name="title", description="Thread title or default 'Discussion'", default=None
    )
    corpus_title: str | None = strawberry.field(
        name="corpusTitle", description="Title of parent corpus", default=None
    )
    message_count: int | None = strawberry.field(
        name="messageCount", description="Number of messages in thread", default=None
    )
    creator_name: str | None = strawberry.field(
        name="creatorName", description="Public slug of thread creator", default=None
    )
    is_public: bool | None = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGThreadMetadataType", OGThreadMetadataType, model=None)


@strawberry.type(
    name="OGExtractMetadataType",
    description="Minimal extract metadata for Open Graph previews.",
)
class OGExtractMetadataType:
    name: str | None = strawberry.field(
        name="name", description="Extract name", default=None
    )
    corpus_title: str | None = strawberry.field(
        name="corpusTitle", description="Title of source corpus", default=None
    )
    fieldset_name: str | None = strawberry.field(
        name="fieldsetName",
        description="Name of fieldset used for extraction",
        default=None,
    )
    creator_name: str | None = strawberry.field(
        name="creatorName", description="Public slug of extract creator", default=None
    )
    is_public: bool | None = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGExtractMetadataType", OGExtractMetadataType, model=None)
