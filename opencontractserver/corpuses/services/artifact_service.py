"""Artifact service — create / read / list shareable corpus posters.

An :class:`~opencontractserver.corpuses.models.Artifact` pairs a corpus with a
reusable, corpus-agnostic visual *template* and a few configurable captions.
This service is the single entry point for the GraphQL layer (per the service
rule): it enforces **corpus-as-gate** visibility (the source corpus must be
READ-visible to the caller; a public corpus's artifact is therefore anonymous-
visible, like the data story and governance graph) and owns the registry of
templates plus their **data-gated eligibility** — a corpus only offers the
templates its data can actually fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencontractserver.constants.artifacts import _MIN_DATED
from opencontractserver.corpuses.models import Artifact, Corpus
from opencontractserver.shared.services.base import BaseService


@dataclass
class TemplateInfo:
    id: str
    label: str
    description: str
    eligible: bool
    reason: str


# The artifact template registry. ``id`` matches the frontend poster registry
# (``POSTER_TEMPLATES`` in ``ArtifactPosterRoute.tsx``); ``needs`` names the data
# signal the eligibility check looks for. A template is only listed here once its
# frontend renderer exists — otherwise users could mint an artifact that
# ``/a/<slug>`` cannot render. Adding a template (and its frontend poster) never
# needs a migration — the model stores ``template`` as a free string.
#
# ``reference-web`` (the citation-network poster) is intentionally NOT listed yet:
# its frontend renderer is not built, so offering it would create unviewable
# artifacts. Re-add it here (and its ``_MIN_REFERENCES`` eligibility branch) when
# the poster ships.
ARTIFACT_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "spending-beeswarm",
        "label": "Spending beeswarm",
        "description": (
            "Every document a dot on a time axis, sized by dollar value — the "
            "collection's spending over time."
        ),
        "needs": "dated",
    },
]

# Eligibility threshold (``_MIN_DATED``) and the upload size guard
# (``MAX_ARTIFACT_IMAGE_BASE64_BYTES``) live in
# ``opencontractserver.constants.artifacts``. The size guard is enforced by the
# ``SetArtifactImage`` mutation before the decode, so it is imported there.


class ArtifactService(BaseService):
    """Create, read and enumerate corpus artifacts (corpus-as-gate)."""

    _NOT_FOUND = "Artifact not found or you don't have permission."

    # ------------------------------------------------------------------
    # Visibility helper (corpus-as-gate)
    # ------------------------------------------------------------------
    @classmethod
    def _corpus_readable(
        cls, user: Any, corpus_id: int, *, request: Any = None
    ) -> bool:
        return (
            BaseService.filter_visible(Corpus, user, request=request)
            .filter(id=corpus_id)
            .exists()
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    @classmethod
    def get_by_slug(
        cls, user: Any, slug: str, *, request: Any = None
    ) -> Artifact | None:
        """Return the artifact for ``slug`` iff its corpus is READ-visible.

        Corpus-as-gate: a public corpus's artifact is visible to anonymous
        users; a private corpus's artifact stays hidden. Returns ``None`` (the
        resolver maps that to a null field) rather than leaking existence.
        """
        artifact = (
            Artifact.objects.filter(slug=slug)
            .select_related("corpus", "creator")
            .first()
        )
        if artifact is None:
            return None
        if not cls._corpus_readable(user, artifact.corpus_id, request=request):
            return None
        return artifact

    @classmethod
    def list_for_corpus(
        cls, user: Any, corpus_id: int, *, request: Any = None
    ) -> list[Artifact]:
        """All artifacts of a corpus the caller can read (corpus-as-gate)."""
        if not cls._corpus_readable(user, corpus_id, request=request):
            return []
        # ``_artifact_to_type`` dereferences ``corpus`` and ``creator`` on every
        # row, so prefetch both to avoid 2N follow-up queries.
        return list(
            Artifact.objects.filter(corpus_id=corpus_id)
            .select_related("corpus", "creator")
            .order_by("-created")
        )

    # ------------------------------------------------------------------
    # Template eligibility (data-gated picker)
    # ------------------------------------------------------------------
    @classmethod
    def templates_for_corpus(
        cls, user: Any, corpus_id: int, *, request: Any = None
    ) -> list[TemplateInfo]:
        """Which templates this corpus's data can actually fill."""
        if not cls._corpus_readable(user, corpus_id, request=request):
            return []

        from opencontractserver.corpuses.services.data_story import (
            CorpusDataStoryService,
        )

        story = CorpusDataStoryService.build(user, corpus_id, request=request)
        dated = (
            sum(1 for p in story.profiles if p.effective_date)
            if story is not None
            else 0
        )

        out: list[TemplateInfo] = []
        for t in ARTIFACT_TEMPLATES:
            if t["needs"] == "dated":
                eligible = dated >= _MIN_DATED
                reason = (
                    f"{dated} dated documents"
                    if eligible
                    else "needs dated documents (run the profile extract)"
                )
            else:  # pragma: no cover - future templates
                eligible, reason = False, "unknown requirement"
            out.append(
                TemplateInfo(
                    id=t["id"],
                    label=t["label"],
                    description=t["description"],
                    eligible=eligible,
                    reason=reason,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Create / update
    # ------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        user: Any,
        corpus_id: int,
        template: str,
        *,
        title: str = "",
        subtitle: str = "",
        byline: str = "",
        config: dict | None = None,
        is_public: bool = True,
        request: Any = None,
    ) -> Artifact | None:
        """Create an artifact for a corpus the caller can read.

        Requires an **authenticated** creator — anonymous users may *view* a
        public corpus's posters but may not mint new ones (no anonymous DB
        writes). Gated at READ on top of that (you can make a poster of any
        collection you can see); the artifact is public by default so its
        ``/a/<slug>`` link is shareable, but its data still only renders to
        viewers who can read the corpus.
        """
        if not getattr(user, "is_authenticated", False):
            return None
        known = {t["id"] for t in ARTIFACT_TEMPLATES}
        if template not in known:
            return None
        if not cls._corpus_readable(user, corpus_id, request=request):
            return None
        artifact = Artifact.objects.create(
            corpus_id=corpus_id,
            template=template,
            title=title or "",
            subtitle=subtitle or "",
            byline=byline or "",
            config=config or {},
            is_public=is_public,
            creator=user,
        )
        # Refetch with corpus/creator prefetched: the CreateArtifact mutation
        # immediately serializes the result via ``_artifact_to_type``, which
        # reads ``a.corpus.slug``; returning the bare ``create()`` object would
        # force an extra SELECT on every create (N+1).
        return Artifact.objects.select_related("corpus", "creator").get(pk=artifact.pk)

    @classmethod
    def update_captions(
        cls,
        user: Any,
        slug: str,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        byline: str | None = None,
        config: dict | None = None,
        request: Any = None,
    ) -> Artifact | None:
        """Edit an artifact's captions — creator only."""
        artifact = Artifact.objects.filter(slug=slug).first()
        if artifact is None:
            return None
        # Corpus-as-gate (mirrors get_by_slug): a known/guessed slug must not let
        # a user mutate an artifact in a corpus they cannot read (IDOR). Checked
        # before the creator/UPDATE gate so a private-corpus artifact is
        # indistinguishable from a nonexistent one.
        if not cls._corpus_readable(user, artifact.corpus_id, request=request):
            return None
        if not cls._can_edit(artifact, user):
            return None
        if title is not None:
            artifact.title = title
        if subtitle is not None:
            artifact.subtitle = subtitle
        if byline is not None:
            artifact.byline = byline
        if config is not None:
            artifact.config = config
        artifact.save()
        # Refetch with corpus/creator prefetched (as ``create`` does): the
        # UpdateArtifact mutation serializes the result via ``_artifact_to_type``,
        # which reads ``a.corpus.slug`` / ``a.creator.slug`` — returning the bare
        # saved instance forces an extra SELECT per call (and raises
        # ``SynchronousOnlyOperation`` in an async context).
        return Artifact.objects.select_related("corpus", "creator").get(pk=artifact.pk)

    @classmethod
    def set_image(
        cls,
        user: Any,
        slug: str,
        image_bytes: bytes,
        *,
        request: Any = None,
    ) -> Artifact | None:
        """Persist the rendered poster PNG for ``slug`` — creator/UPDATE only.

        The GraphQL layer routes here rather than touching ``Artifact.objects``
        directly (service-layer invariant), so any future image handling
        (validation, audit, storage abstraction) has a single home. Caller is
        responsible for size-capping and decoding the base64 upload before this
        point; this method owns validating the decoded bytes are actually a PNG.

        Raises ``ValueError`` if ``image_bytes`` isn't PNG data (distinct from
        the ``None`` return used for not-found/no-permission, which must stay
        indistinguishable to avoid an existence oracle).
        """
        from django.core.files.base import ContentFile

        artifact = Artifact.objects.filter(slug=slug).first()
        if artifact is None:
            return None
        # Corpus-as-gate (mirrors get_by_slug / update_captions): the slug alone
        # must not let a user overwrite the poster image of an artifact in a
        # corpus they cannot read (IDOR).
        if not cls._corpus_readable(user, artifact.corpus_id, request=request):
            return None
        if not cls._can_edit(artifact, user):
            return None
        # The bytes are persisted as ``<slug>.png`` at a public media URL, so
        # reject anything that isn't actually a PNG (an SVG with embedded
        # script, an executable, a polyglot) before it reaches storage. Checked
        # after the permission gate so an unauthorized caller learns nothing
        # about whether their upload would otherwise have been accepted.
        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Image must be a PNG.")
        artifact.image.save(f"{artifact.slug}.png", ContentFile(image_bytes), save=True)
        # Refetch with corpus/creator prefetched (as ``create``/``update_captions``
        # do): the SetArtifactImage mutation's caller may serialize the result
        # via ``_artifact_to_type``, which reads ``a.corpus.slug`` — returning
        # the bare saved instance would force an extra SELECT (and raises
        # ``SynchronousOnlyOperation`` in an async context).
        return Artifact.objects.select_related("corpus", "creator").get(pk=artifact.pk)

    @staticmethod
    def _can_edit(artifact: Artifact, user: Any) -> bool:
        """Whether ``user`` may mutate ``artifact`` (captions / image).

        ``Artifact`` has no guardian permission tables, so object-level
        ``user_has(... UPDATE ...)`` can only ever return ``True`` for the
        creator — the same condition checked directly here — making it dead
        weight that also implied future guardian grants are possible (they
        aren't). Edit rights are the creator, plus superusers for admin
        override.
        """
        return artifact.creator_id == getattr(user, "id", None) or bool(
            getattr(user, "is_superuser", False)
        )
