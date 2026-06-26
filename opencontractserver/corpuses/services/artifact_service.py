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

from opencontractserver.corpuses.models import Artifact, Corpus
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes


@dataclass
class TemplateInfo:
    id: str
    label: str
    description: str
    eligible: bool
    reason: str


# The artifact template registry. ``id`` matches the frontend poster registry;
# ``needs`` names the data signal the eligibility check looks for. Adding a
# template here (and its frontend poster) never needs a migration — the model
# stores ``template`` as a free string.
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
    {
        "id": "reference-web",
        "label": "Reference web",
        "description": (
            "How the collection is wired together through shared legal "
            "authority — the hidden citation network."
        ),
        "needs": "references",
    },
]

# Minimum data for a template to be worth offering.
_MIN_DATED = 3
_MIN_REFERENCES = 2


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
        artifact = Artifact.objects.filter(slug=slug).select_related("corpus").first()
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
        return list(Artifact.objects.filter(corpus_id=corpus_id).order_by("-created"))

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
        references = cls._reference_count(corpus_id)

        out: list[TemplateInfo] = []
        for t in ARTIFACT_TEMPLATES:
            if t["needs"] == "dated":
                eligible = dated >= _MIN_DATED
                reason = (
                    f"{dated} dated documents"
                    if eligible
                    else "needs dated documents (run the profile extract)"
                )
            elif t["needs"] == "references":
                eligible = references >= _MIN_REFERENCES
                reason = (
                    f"{references} law references"
                    if eligible
                    else "needs a mapped reference web"
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

    @staticmethod
    def _reference_count(corpus_id: int) -> int:
        try:
            from opencontractserver.annotations.models import CorpusReference

            return CorpusReference.objects.filter(corpus_id=corpus_id).count()
        except Exception:
            return 0

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
        return artifact

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
        if not cls.user_has(
            artifact, user, PermissionTypes.UPDATE, request=request
        ) and artifact.creator_id != getattr(user, "id", None):
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
        return artifact
