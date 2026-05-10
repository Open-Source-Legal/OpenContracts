"""
Open Graph Metadata Types for Social Media Previews

These types return minimal public metadata for generating OG/Twitter meta tags.
All queries are unauthenticated and only return data for public entities.

Used by the Cloudflare Worker at cloudflare-og-worker/ to serve rich link
previews to social media crawlers (Twitter, Facebook, Slack, etc.)

See: docs/architecture/social-media-previews.md
"""

import graphene


class OGCorpusMetadataType(graphene.ObjectType):
    """Minimal corpus metadata for Open Graph previews - public entities only."""

    title = graphene.String(description="Corpus title")
    description = graphene.String(description="Corpus description (truncated)")
    icon_url = graphene.String(description="URL to corpus icon/thumbnail")
    document_count = graphene.Int(description="Number of documents in corpus")
    creator_name = graphene.String(description="Public slug of corpus creator")
    is_public = graphene.Boolean(description="Always True for returned entities")


class OGDocumentMetadataType(graphene.ObjectType):
    """Minimal document metadata for Open Graph previews - public entities only."""

    title = graphene.String(description="Document title")
    description = graphene.String(description="Document description (truncated)")
    icon_url = graphene.String(description="URL to document thumbnail")
    corpus_title = graphene.String(
        description="Title of parent corpus (if document is in a corpus)"
    )
    corpus_description = graphene.String(
        description="Description of parent corpus (if document is in a corpus)"
    )
    creator_name = graphene.String(description="Public slug of document creator")
    is_public = graphene.Boolean(description="Always True for returned entities")


class OGThreadMetadataType(graphene.ObjectType):
    """Minimal discussion thread metadata for Open Graph previews."""

    title = graphene.String(description="Thread title or default 'Discussion'")
    corpus_title = graphene.String(description="Title of parent corpus")
    message_count = graphene.Int(description="Number of messages in thread")
    creator_name = graphene.String(description="Public slug of thread creator")
    is_public = graphene.Boolean(description="Always True for returned entities")


class OGExtractMetadataType(graphene.ObjectType):
    """Minimal extract metadata for Open Graph previews."""

    name = graphene.String(description="Extract name")
    corpus_title = graphene.String(description="Title of source corpus")
    fieldset_name = graphene.String(description="Name of fieldset used for extraction")
    creator_name = graphene.String(description="Public slug of extract creator")
    is_public = graphene.Boolean(description="Always True for returned entities")
