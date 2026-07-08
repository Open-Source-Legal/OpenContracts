"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

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

from typing import Optional

import strawberry

from config.graphql.core.relay import (
    register_type,
)


@strawberry.type(
    name="OGCorpusMetadataType",
    description="Minimal corpus metadata for Open Graph previews - public entities only.",
)
class OGCorpusMetadataType:
    title: Optional[str] = strawberry.field(
        name="title", description="Corpus title", default=None
    )
    description: Optional[str] = strawberry.field(
        name="description", description="Corpus description (truncated)", default=None
    )
    icon_url: Optional[str] = strawberry.field(
        name="iconUrl", description="URL to corpus icon/thumbnail", default=None
    )
    document_count: Optional[int] = strawberry.field(
        name="documentCount", description="Number of documents in corpus", default=None
    )
    creator_name: Optional[str] = strawberry.field(
        name="creatorName", description="Public slug of corpus creator", default=None
    )
    is_public: Optional[bool] = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGCorpusMetadataType", OGCorpusMetadataType, model=None)


@strawberry.type(
    name="OGDocumentMetadataType",
    description="Minimal document metadata for Open Graph previews - public entities only.",
)
class OGDocumentMetadataType:
    title: Optional[str] = strawberry.field(
        name="title", description="Document title", default=None
    )
    description: Optional[str] = strawberry.field(
        name="description", description="Document description (truncated)", default=None
    )
    icon_url: Optional[str] = strawberry.field(
        name="iconUrl", description="URL to document thumbnail", default=None
    )
    corpus_title: Optional[str] = strawberry.field(
        name="corpusTitle",
        description="Title of parent corpus (if document is in a corpus)",
        default=None,
    )
    corpus_description: Optional[str] = strawberry.field(
        name="corpusDescription",
        description="Description of parent corpus (if document is in a corpus)",
        default=None,
    )
    creator_name: Optional[str] = strawberry.field(
        name="creatorName", description="Public slug of document creator", default=None
    )
    is_public: Optional[bool] = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGDocumentMetadataType", OGDocumentMetadataType, model=None)


@strawberry.type(
    name="OGThreadMetadataType",
    description="Minimal discussion thread metadata for Open Graph previews.",
)
class OGThreadMetadataType:
    title: Optional[str] = strawberry.field(
        name="title", description="Thread title or default 'Discussion'", default=None
    )
    corpus_title: Optional[str] = strawberry.field(
        name="corpusTitle", description="Title of parent corpus", default=None
    )
    message_count: Optional[int] = strawberry.field(
        name="messageCount", description="Number of messages in thread", default=None
    )
    creator_name: Optional[str] = strawberry.field(
        name="creatorName", description="Public slug of thread creator", default=None
    )
    is_public: Optional[bool] = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGThreadMetadataType", OGThreadMetadataType, model=None)


@strawberry.type(
    name="OGExtractMetadataType",
    description="Minimal extract metadata for Open Graph previews.",
)
class OGExtractMetadataType:
    name: Optional[str] = strawberry.field(
        name="name", description="Extract name", default=None
    )
    corpus_title: Optional[str] = strawberry.field(
        name="corpusTitle", description="Title of source corpus", default=None
    )
    fieldset_name: Optional[str] = strawberry.field(
        name="fieldsetName",
        description="Name of fieldset used for extraction",
        default=None,
    )
    creator_name: Optional[str] = strawberry.field(
        name="creatorName", description="Public slug of extract creator", default=None
    )
    is_public: Optional[bool] = strawberry.field(
        name="isPublic", description="Always True for returned entities", default=None
    )


register_type("OGExtractMetadataType", OGExtractMetadataType, model=None)
