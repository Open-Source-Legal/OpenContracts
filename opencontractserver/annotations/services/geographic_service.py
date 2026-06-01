"""Geographic annotation aggregation — issue #1819.

Surfaces aggregated pin data for the map UI (#1820 / #1821) without leaking
the underlying annotation rows. Two visibility modes:

* ``aggregate_for_corpus`` — corpus-scoped. Routes through
  :class:`CorpusDocumentService.get_corpus_documents_visible_to_user` so a
  private document inside a public/shared corpus does NOT contribute pins
  to a user who lacks document-level READ. This matches the user-facing
  ``MIN(document, corpus)`` semantic documented in
  ``docs/permissioning/consolidated_permissioning_guide.md``.
* ``aggregate_global`` — global Discover surface. Uses
  ``Annotation.objects.visible_to_user(user)`` so per-row visibility rules
  apply uniformly across every corpus the viewer can read.

Both return the same ``GeographicPin`` shape so the frontend reuses one
component (``AnnotationMap``, #1820) for either source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

from django.db.models import Q, QuerySet

from opencontractserver.constants.annotations import (
    GEOGRAPHIC_PIN_SAMPLE_DOC_LIMIT,
    OC_CITY_LABEL,
    OC_COUNTRY_LABEL,
    OC_STATE_LABEL,
)
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


# The closed set of ``resolve_place`` label-type literals. Naming it once lets
# the inverse map (and any downstream caller) advertise the exact three values
# instead of a bare ``str``, so call sites get exhaustiveness checking.
GeocodeLabelType = Literal["country", "state", "city"]

# Map a frontend ``labelType`` filter value to the backend label text used
# to mark the annotation. Single source of truth so callers don't sprinkle
# label-text constants through resolvers.
GEOCODE_LABEL_TYPE_TO_LABEL_TEXT: dict[str, str] = {
    "country": OC_COUNTRY_LABEL,
    "state": OC_STATE_LABEL,
    "city": OC_CITY_LABEL,
}

_ALL_GEO_LABELS = frozenset(GEOCODE_LABEL_TYPE_TO_LABEL_TEXT.values())

# Inverse of ``GEOCODE_LABEL_TYPE_TO_LABEL_TEXT`` — maps an OC_* label text
# back to the ``resolve_place`` label-type literal. Lets annotation-creation
# callers that work in terms of label *text* (e.g. the
# ``add_annotations_from_exact_strings`` agent tool) reuse the same geocoding
# path the GraphQL mutations use without re-deriving the mapping. The ``cast``
# narrows each value from ``str`` (the forward map's value type) to the
# ``GeocodeLabelType`` literal — exhaustively true here, but not provable to the
# type checker through the comprehension.
LABEL_TEXT_TO_GEOCODE_LABEL_TYPE: dict[str, GeocodeLabelType] = {
    text: cast(GeocodeLabelType, label_type)
    for label_type, text in GEOCODE_LABEL_TYPE_TO_LABEL_TEXT.items()
}


def build_geocoded_annotation_data(
    geocode_label_type: str,
    text: str,
    *,
    country_hint: str | None = None,
    state_hint: str | None = None,
) -> dict[str, Any]:
    """Resolve ``text`` and return the ``Annotation.data`` payload.

    Single source of truth for the geocoded sidecar shape written onto
    ``OC_COUNTRY`` / ``OC_STATE`` / ``OC_CITY`` annotations. Both the GraphQL
    geographic mutations (``config/graphql/annotation_mutations.py``) and the
    ``add_annotations_from_exact_strings`` agent tool call this so the map
    aggregation service (which keys off ``data['geocoded']`` /
    ``canonical_name`` / ``lat`` / ``lng``) sees an identical shape regardless
    of which surface created the row.

    On a resolver hit the dict carries ``geocoded=True`` plus the canonical
    name, coordinates, and admin codes. On a miss the annotation is still
    worth creating (the caller keeps the user's labelling work) so a
    ``geocoded=False`` sentinel is returned instead — the aggregation service
    filters those out of map pins.

    Args:
        geocode_label_type: ``"country"`` / ``"state"`` / ``"city"`` — the
            ``resolve_place`` label type, NOT the OC_* label text. Callers
            holding a label text should map it via
            :data:`LABEL_TEXT_TO_GEOCODE_LABEL_TYPE` first.
        text: The span text to geocode.
        country_hint: Optional disambiguation hint forwarded to ``resolve_place``
            — narrows ``state`` / ``city`` candidates to the given country.
        state_hint: Optional disambiguation hint forwarded to ``resolve_place``
            — narrows ``city`` candidates to the given (US) state.
    """
    from opencontractserver.utils.geocoding import resolve_place

    # Make the caller contract explicit rather than relying on the
    # ``type: ignore`` alone — a bad label type is a programming error here
    # (the OC_* reverse-map / GraphQL enum should never produce anything
    # else), so fail loudly instead of letting it reach ``resolve_place``.
    # A bare ``assert`` would be stripped under ``python -O`` (common in
    # production containers), so raise explicitly.
    if geocode_label_type not in ("country", "state", "city"):
        raise ValueError(
            f"geocode_label_type must be country/state/city, "
            f"got {geocode_label_type!r}"
        )

    resolved = resolve_place(
        text,
        geocode_label_type,  # type: ignore[arg-type]  # narrowed by the guard above
        country_hint=country_hint,
        state_hint=state_hint,
    )
    if resolved is not None:
        return {
            "canonical_name": resolved.canonical_name,
            "lat": resolved.lat,
            "lng": resolved.lng,
            "admin_codes": resolved.admin_codes,
            "geocoded": True,
        }
    return {
        "canonical_name": None,
        "lat": None,
        "lng": None,
        "admin_codes": {},
        "geocoded": False,
        "raw_text": text,
    }


def _validate_label_types(label_types: list[str] | None) -> None:
    """Validate caller-supplied ``label_types`` against the known set.

    Called by both ``aggregate_for_corpus`` and ``aggregate_global`` BEFORE
    any visibility short-circuit so a typo (``"city "``, ``"municipality"``)
    fails fast with a clear error rather than silently returning ``[]``
    when the corpus happens to be empty or inaccessible.
    """
    if label_types is None:
        return
    for lt in label_types:
        if lt not in GEOCODE_LABEL_TYPE_TO_LABEL_TEXT:
            raise ValueError(
                f"Unknown label_type '{lt}'; expected one of "
                f"{sorted(GEOCODE_LABEL_TYPE_TO_LABEL_TEXT)}"
            )


@dataclass(frozen=True)
class BBox:
    """Map bounding box used as an optional spatial filter.

    Fields use map conventions: south/west = lower-left corner, north/east
    = upper-right corner. ``south <= north`` always; ``west`` may exceed
    ``east`` when the box crosses the antimeridian (180°/-180° longitude
    seam), which the filter handles explicitly.
    """

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        # Reject degenerate latitude band — a south>north box would silently
        # match nothing (``_bbox_contains`` requires ``south <= lat <= north``)
        # and quietly return an empty list, making debugging painful.
        # Longitude is intentionally unvalidated: ``west > east`` is the
        # antimeridian-crossing case, which is legal.
        if self.south > self.north:
            raise ValueError(
                f"BBox south ({self.south}) must be <= north ({self.north})"
            )


@dataclass(frozen=True)
class GeographicPin:
    """A single aggregated pin returned to the map UI.

    The shape mirrors the GraphQL type one-to-one (the resolver builds
    the type directly from this dataclass) so the contract between the
    service and the API surface is auditable in one place.
    """

    canonical_name: str
    label_type: str
    lat: float
    lng: float
    document_count: int
    sample_document_ids: list[int]


def _label_type_label_filter(label_types: list[str] | None) -> Q:
    """Build a ``Q`` filter constraining annotations to the geographic labels.

    Pre-condition: ``label_types`` has already been validated by
    :func:`_validate_label_types` (the public service methods call it).
    Building the queryset is the only responsibility here.
    """
    target_texts: list[str] = []
    if label_types is None:
        target_texts.extend(_ALL_GEO_LABELS)
    else:
        for lt in label_types:
            target_texts.append(GEOCODE_LABEL_TYPE_TO_LABEL_TEXT[lt])
    return Q(annotation_label__text__in=target_texts)


def _row_to_pin(row: dict) -> GeographicPin:
    """Project a grouped row from ``aggregate_pins`` into a ``GeographicPin``."""
    sample_ids = row["sample_ids"][:GEOGRAPHIC_PIN_SAMPLE_DOC_LIMIT]
    return GeographicPin(
        canonical_name=row["canonical_name"],
        label_type=row["label_type"],
        lat=row["lat"],
        lng=row["lng"],
        document_count=row["document_count"],
        sample_document_ids=sample_ids,
    )


def _bbox_contains(bbox: BBox, lat: float, lng: float) -> bool:
    """Return True when ``(lat, lng)`` falls inside ``bbox``.

    Handles antimeridian-crossing boxes (``west > east``) by treating the
    longitude band as a union of two ranges: [west, 180] ∪ [-180, east].
    Latitude is a single interval — there's no analogous wrap-around in
    Mercator-style web maps.
    """
    if not (bbox.south <= lat <= bbox.north):
        return False
    if bbox.west <= bbox.east:
        return bbox.west <= lng <= bbox.east
    return lng >= bbox.west or lng <= bbox.east


def _aggregate_pins(
    qs: QuerySet,
    label_types: list[str] | None,
    bbox: BBox | None,
) -> list[GeographicPin]:
    """Group an annotation queryset into deduplicated map pins.

    Filters to:
      * Only annotations carrying one of the geographic OC_* labels (or
        the explicit ``label_types`` subset)
      * Only annotations with ``data['geocoded'] is True`` — the mutations
        write annotations even when the resolver returned ``None`` so the
        user's annotation work survives, but those rows must not pollute
        map aggregation.

    Then groups by ``(label_text, canonical_name, lat, lng)`` so identical
    places coming from different documents collapse into one pin with a
    ``document_count`` and a bounded ``sample_document_ids`` preview.

    The grouping is done in Python after a small projected ``.values()``
    fetch rather than via PostgreSQL ``json_agg``. The aggregation set is
    bounded by the geographic label set (typically < 1000 distinct
    canonical names per corpus / < 10000 globally), so the Python pass is
    cheap and keeps the query portable across SQLite/PG/etc.

    **Memory note (issue #1819 review):** each bucket carries a
    ``document_count_set`` of full document PKs for accurate
    deduplication. For ``aggregate_for_corpus`` the set is bounded by
    corpus size and stays small. For ``aggregate_global`` on a popular
    canonical name (e.g. "United States" across a large multi-corpus
    deployment) this set could grow to hundreds of thousands of entries
    per pin. If profiling ever shows this as a hotspot, switch to a
    DB-side ``COUNT(DISTINCT document_id)`` aggregate keyed by
    ``(label_text, data->>canonical_name, data->>lat, data->>lng)`` —
    ``sample_document_ids`` would still need the bounded Python pass.
    """
    qs = qs.filter(_label_type_label_filter(label_types))
    qs = qs.exclude(data__isnull=True)
    # ``data__geocoded=True`` — JSONField key lookup; matches rows where
    # the resolver succeeded.
    qs = qs.filter(data__geocoded=True)

    grouped: dict[tuple[str, str, float, float], dict] = {}

    for row in qs.values(
        "annotation_label__text",
        "data",
        "document_id",
    ):
        data = row.get("data") or {}
        canonical = data.get("canonical_name")
        lat = data.get("lat")
        lng = data.get("lng")
        if not canonical or lat is None or lng is None:
            continue
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError):
            continue

        if bbox is not None and not _bbox_contains(bbox, lat_f, lng_f):
            continue

        label_text = row["annotation_label__text"]
        # Reverse-map the label text → label_type literal exposed to clients.
        # The dict is tiny so a linear scan is fine.
        label_type = next(
            (
                lt
                for lt, txt in GEOCODE_LABEL_TYPE_TO_LABEL_TEXT.items()
                if txt == label_text
            ),
            None,
        )
        if label_type is None:  # pragma: no cover
            # Defensive: shouldn't happen given the ``_label_type_label_filter``
            # upstream, but skip rather than crash on dataset drift.
            continue

        key = (label_text, canonical, lat_f, lng_f)
        bucket = grouped.get(key)
        doc_id = row.get("document_id")
        if bucket is None:
            grouped[key] = {
                "canonical_name": canonical,
                "label_type": label_type,
                "lat": lat_f,
                "lng": lng_f,
                "document_count_set": {doc_id} if doc_id else set(),
                "sample_ids": [doc_id] if doc_id else [],
            }
            continue
        if doc_id and doc_id not in bucket["document_count_set"]:
            bucket["document_count_set"].add(doc_id)
            if len(bucket["sample_ids"]) < GEOGRAPHIC_PIN_SAMPLE_DOC_LIMIT:
                bucket["sample_ids"].append(doc_id)

    pins: list[GeographicPin] = []
    for bucket in grouped.values():
        bucket["document_count"] = len(bucket["document_count_set"])
        pins.append(_row_to_pin(bucket))
    # Sort by document count desc for a deterministic, useful order.
    pins.sort(key=lambda p: (-p.document_count, p.canonical_name))
    return pins


class GeographicAnnotationService(BaseService):
    """Aggregate geographic annotations into map-ready pins.

    Two callers, two visibility modes — see module docstring. Both modes
    return ``list[GeographicPin]``; the resolver translates each pin into
    its GraphQL type.

    The service is the single permission gate for the map surface. Inline
    composition of ``Annotation.objects.visible_to_user`` + corpus filters
    in resolvers would risk leaking private docs in a public corpus
    (CLAUDE.md rule 7 — always route through ``services/``).
    """

    @classmethod
    def aggregate_for_corpus(
        cls,
        user: Any,
        corpus: Any,
        *,
        bbox: BBox | None = None,
        label_types: list[str] | None = None,
        request: Any = None,
    ) -> list[GeographicPin]:
        """Return pins for ``corpus``, filtered to documents visible to ``user``.

        Visibility: routes through
        :meth:`CorpusDocumentService.get_corpus_documents_visible_to_user`
        (issue #1682, ``_visible_to_user`` variant) so a private document
        inside a public/shared corpus does NOT contribute pins to a user
        who lacks document-level READ.

        Returns an empty list (NOT raise) when the user cannot read the
        corpus — keeps the surface IDOR-safe (same response as an empty
        corpus / unrecognised id).
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.corpuses.services import CorpusDocumentService

        # Validate up front — must happen before any short-circuit so a
        # typo in ``label_types`` doesn't get masked by an empty corpus
        # returning [].
        _validate_label_types(label_types)

        visible_docs = CorpusDocumentService.get_corpus_documents_visible_to_user(
            user=user, corpus=corpus, request=request
        )

        # Always-empty short-circuit: if the user can't see any documents in
        # this corpus, no annotations are visible either. Saves a needless
        # ``annotations`` table scan when the corpus is empty / inaccessible.
        if not visible_docs.exists():
            return []

        # Corpus-scoped — annotations tied to documents the viewer can see.
        # ``corpus_id=corpus.pk`` already constrains the row set; the
        # ``document_id__in=visible_docs`` clause is the MIN-permission
        # gate (document-level READ). ``.values("pk")`` keeps the
        # queryset unevaluated so Django compiles a SQL subquery — no
        # Python-side materialisation of every visible document PK.
        qs = Annotation.objects.filter(
            corpus_id=corpus.pk,
            document_id__in=visible_docs.values("pk"),
        )

        return _aggregate_pins(qs, label_types=label_types, bbox=bbox)

    @classmethod
    def aggregate_global(
        cls,
        user: Any,
        *,
        bbox: BBox | None = None,
        label_types: list[str] | None = None,
        request: Any = None,
    ) -> list[GeographicPin]:
        """Return pins across every annotation visible to ``user``.

        Visibility: ``Annotation.objects.visible_to_user(user)`` — the
        manager method that encodes the cross-corpus, MIN-permission
        rules for the global Discover surface.

        ``request`` is accepted for API symmetry with the corpus variant
        and reserved for future Tier-2 permission caching; the underlying
        ``visible_to_user`` manager does not currently consume it.
        """
        from opencontractserver.annotations.models import Annotation

        # Validate up front — symmetric with ``aggregate_for_corpus`` so a
        # typo in ``label_types`` fails fast even when ``visible_to_user``
        # would otherwise return an empty queryset.
        _validate_label_types(label_types)

        qs = Annotation.objects.visible_to_user(user)
        return _aggregate_pins(qs, label_types=label_types, bbox=bbox)


__all__ = [
    "BBox",
    "GeographicAnnotationService",
    "GeographicPin",
    "LABEL_TEXT_TO_GEOCODE_LABEL_TYPE",
    "build_geocoded_annotation_data",
]
