"""Read surface for ``CorpusReference`` rows.

Visibility derives from the readable parent corpus plus the readable source
and target objects carried by each row. ``CorpusReference`` carries no
per-object guardian rows in v1.
"""

from __future__ import annotations

from django.db.models import Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment import constants as C
from opencontractserver.shared.services.base import BaseService


class CorpusReferenceService(BaseService):
    """Read surface for CorpusReference rows."""

    @staticmethod
    def _build_visibility_querysets(user):
        """The ``(visible_corpora, visible_documents)`` pair both visibility
        filters need — built in one place so the source-side and target-side
        filters cannot drift apart.

        Materialised to plain pk lists (rather than left as lazy QuerySets):
        each list is reused across up to four ``__in=`` positions in the
        combined filter, and Django renders one SQL subquery per ``__in=``
        use site of a QuerySet. Fetching the pks once here trades a single
        list round-trip for avoiding that repeated-subquery fan-out.
        """
        return (
            list(Corpus.objects.visible_to_user(user).values_list("pk", flat=True)),
            list(Document.objects.visible_to_user(user).values_list("pk", flat=True)),
        )

    @staticmethod
    def _source_visible_q(visible_corpora, visible_documents):
        """``Q`` gating the reference row's parent corpus and its SOURCE
        annotation under MIN(document_permission, corpus_permission).

        Corpus READ gates the row itself. ``source_annotation`` is a
        non-nullable FK, so every row has one; what needs the NULL-passthrough
        guard is the source annotation's own ``document`` and ``corpus``
        fields. A structural annotation has ``document=None``, and
        ``Annotation.corpus`` is nullable — NULL is never a member of an
        ``__in`` list, so without these isnull guards every
        structural-annotation-sourced reference (including the corpus owner's
        own) would be silently dropped.
        """
        return Q(corpus__in=visible_corpora) & (
            (
                Q(source_annotation__document__isnull=True)
                | Q(source_annotation__document__in=visible_documents)
            )
            & (
                Q(source_annotation__corpus__isnull=True)
                | Q(source_annotation__corpus__in=visible_corpora)
            )
        )

    @staticmethod
    def _target_visible_q(visible_corpora, visible_documents):
        """``Q`` gating a reference's resolved TARGET (document / corpus /
        annotation) under MIN(document_permission, corpus_permission).

        A target whose document is public but whose corpus is private must not
        leak its annotation FK, so the target annotation's document AND corpus
        are both gated (NULLs passed through, as on the source side).
        """
        return (
            (Q(target_document__isnull=True) | Q(target_document__in=visible_documents))
            & (Q(target_corpus__isnull=True) | Q(target_corpus__in=visible_corpora))
            & (
                Q(target_annotation__isnull=True)
                | (
                    (
                        Q(target_annotation__document__isnull=True)
                        | Q(target_annotation__document__in=visible_documents)
                    )
                    & (
                        Q(target_annotation__corpus__isnull=True)
                        | Q(target_annotation__corpus__in=visible_corpora)
                    )
                )
            )
        )

    # ------------------------------------------------------------------ #
    # Superseded sources                                                   #
    # ------------------------------------------------------------------ #
    # A citing document's version-up leaves the previous version's mentions
    # and references in place — that is the history. Current views must not
    # show them (the same citation would appear once per version, and
    # citations from documents soft-deleted from the corpus would linger), so
    # every read surface defaults to sources with an ACTIVE path in the
    # reference's corpus and exposes ``include_historical`` to opt back in.

    SOURCE_ACTIVE_ATTR = "source_is_active"
    SOURCE_HAS_PATH_ATTR = "source_has_path"

    @classmethod
    def _only_active_sources(cls, qs):
        """Drop references whose source annotation's document is a superseded
        or soft-deleted version in the reference's corpus.

        "Superseded or soft-deleted" means the document HAS ``DocumentPath``
        rows in that corpus but none that is current and not deleted. A
        document with no path rows there at all (never placed through the
        versioning primitive) passes through unchanged, as do
        structural-annotation sources (``document=None``), mirroring
        :meth:`_source_visible_q`. Expressed as ``Exists`` so the multi-valued
        path join never duplicates rows.
        """
        paths = DocumentPath.objects.filter(
            document_id=OuterRef("source_annotation__document_id"),
            corpus_id=OuterRef("corpus_id"),
        )
        return qs.annotate(
            **{
                cls.SOURCE_HAS_PATH_ATTR: Exists(paths),
                cls.SOURCE_ACTIVE_ATTR: Exists(
                    paths.filter(is_current=True, is_deleted=False)
                ),
            }
        ).filter(
            Q(source_annotation__document__isnull=True)
            | Q(**{cls.SOURCE_HAS_PATH_ATTR: False})
            | Q(**{cls.SOURCE_ACTIVE_ATTR: True})
        )

    @classmethod
    def visible_to_user_by_source(cls, user, *, include_historical: bool = False):
        """References whose parent corpus AND source annotation are visible.

        Enforces corpus READ and source-annotation visibility, but does NOT
        filter on the resolved *target* (document / corpus / annotation). A
        citation made by a hidden source is suppressed (no source leak), but a
        citation TO a hidden target is RETAINED so the caller can degrade that
        target to a ghost rather than dropping the reference outright.

        Use this for aggregate surfaces that perform their own per-target
        ghosting (the governance graph re-checks both endpoints and degrades
        an invisible target to an external key node). For surfaces that expose
        the target foreign keys directly (e.g. the ``corpusReferences``
        GraphQL query), use :meth:`visible_to_user`, which additionally hides
        references whose target is invisible.
        """
        visible_corpora, visible_documents = cls._build_visibility_querysets(user)
        qs = CorpusReference.objects.filter(
            cls._source_visible_q(visible_corpora, visible_documents)
        )
        return qs if include_historical else cls._only_active_sources(qs)

    @classmethod
    def visible_to_user(cls, user, *, include_historical: bool = False):
        """Return only references whose exposed graph is visible to ``user``.

        Corpus references are reachable from a readable corpus, but each row
        also carries document- and corpus-scoped foreign keys.  Apply the same
        MIN(document_permission, corpus_permission) rule used by user-facing
        corpus document surfaces so a readable corpus cannot disclose private
        source annotations or private resolved targets.

        Composes the source filter (corpus + source) of
        :meth:`visible_to_user_by_source` with the target-visibility filter, so
        a reference is hidden when its resolved target document / corpus /
        annotation is not visible. Callers that ghost invisible targets
        themselves should use :meth:`visible_to_user_by_source` instead so those
        references are not dropped before they can be degraded.
        """
        visible_corpora, visible_documents = cls._build_visibility_querysets(user)
        qs = CorpusReference.objects.filter(
            cls._source_visible_q(visible_corpora, visible_documents)
            & cls._target_visible_q(visible_corpora, visible_documents)
        )
        return qs if include_historical else cls._only_active_sources(qs)

    @classmethod
    def for_corpus(cls, user, corpus_id: int, *, include_historical: bool = False):
        return cls.visible_to_user(user, include_historical=include_historical).filter(
            corpus_id=corpus_id
        )

    @classmethod
    def inbound_to_document(
        cls, user, document_id: int, *, include_historical: bool = False
    ):
        """References resolved onto ``document_id`` (the pinned target), for
        ``DocumentType.inboundReferences``."""
        return cls.visible_to_user(user, include_historical=include_historical).filter(
            target_document_id=document_id
        )

    @classmethod
    def inbound_to_corpus(
        cls, user, corpus_id: int, *, include_historical: bool = False
    ):
        """References from other corpora resolved into ``corpus_id``, for
        ``CorpusType.inboundReferences``."""
        return cls.visible_to_user(user, include_historical=include_historical).filter(
            target_corpus_id=corpus_id
        )

    # ------------------------------------------------------------------ #
    # Version-pinned targets: "as cited" vs. "current"                     #
    # ------------------------------------------------------------------ #
    # ``target_document`` is write-once (the version current when the citation
    # was linked — see ``EnrichmentService._link_external``). The current text
    # is derived, never stored: the ``is_current`` row in the pinned version's
    # tree that still has an active path in the corpus the link points into.
    # Two attributes carry it on a row: ``current_target_document_id`` and
    # ``target_is_current``. Querysets get them in bulk from
    # :meth:`annotate_current_target`; single rows fall back to one query in
    # :meth:`current_target_document_id`.

    CURRENT_TARGET_ATTR = "current_target_document_id"
    TARGET_IS_CURRENT_ATTR = "target_is_current"

    @classmethod
    def annotate_current_target(cls, qs):
        """Annotate ``current_target_document_id`` and ``target_is_current``.

        One correlated subquery, no per-row work. LAW refs link into
        ``target_corpus``; DOCUMENT refs target a sibling in the row's own
        corpus (``target_corpus`` is null), hence the ``Coalesce``.
        """
        current = Document.objects.filter(
            version_tree_id=OuterRef("target_document__version_tree_id"),
            is_current=True,
            path_records__corpus_id=Coalesce(
                OuterRef("target_corpus_id"), OuterRef("corpus_id")
            ),
            path_records__is_current=True,
            path_records__is_deleted=False,
        ).values("id")[:1]
        return qs.annotate(
            **{
                cls.CURRENT_TARGET_ATTR: Subquery(current),
                cls.TARGET_IS_CURRENT_ATTR: F("target_document__is_current"),
            }
        )

    @classmethod
    def current_target_document_id(cls, ref: CorpusReference) -> int | None:
        """The current version's id for ``ref``'s pinned target, or ``None``.

        Reads the bulk annotation when present; otherwise computes it once and
        caches it on the instance so GraphQL field resolvers stay cheap.
        """
        if cls.CURRENT_TARGET_ATTR in ref.__dict__:
            return ref.__dict__[cls.CURRENT_TARGET_ATTR]
        current_id: int | None = None
        target_is_current: bool | None = None
        if ref.target_document_id is not None:
            row = (
                cls.annotate_current_target(CorpusReference.objects.filter(pk=ref.pk))
                .values_list(cls.CURRENT_TARGET_ATTR, cls.TARGET_IS_CURRENT_ATTR)
                .first()
            )
            if row is not None:
                current_id, target_is_current = row
        ref.__dict__[cls.CURRENT_TARGET_ATTR] = current_id
        ref.__dict__[cls.TARGET_IS_CURRENT_ATTR] = target_is_current
        return current_id

    @classmethod
    def target_is_superseded(cls, ref: CorpusReference) -> bool:
        """``True`` when the pinned target is no longer its tree's current
        version. ``False`` for unresolved refs."""
        if ref.target_document_id is None:
            return False
        if cls.TARGET_IS_CURRENT_ATTR not in ref.__dict__:
            cls.current_target_document_id(ref)
        return ref.__dict__[cls.TARGET_IS_CURRENT_ATTR] is False

    @classmethod
    def for_corpus_by_source(
        cls, user, corpus_id: int, *, include_historical: bool = False
    ):
        """Corpus-scoped variant of :meth:`visible_to_user_by_source`.

        For callers that ghost invisible targets themselves (the governance
        graph) or read only the canonical key without exposing target FKs (the
        authority crawl frontier seed), so target-hidden references must not be
        pre-filtered out.
        """
        return cls.visible_to_user_by_source(
            user, include_historical=include_historical
        ).filter(corpus_id=corpus_id)

    @classmethod
    def wanted_authorities(
        cls,
        user,
        corpus_id: int | None = None,
        top_keys_n: int = C.WANTED_AUTHORITIES_TOP_KEYS,
        finalized_only: bool = False,
    ) -> list[dict]:
        """The missing-authority backlog: what to bootstrap next, ranked.

        Aggregates EXTERNAL law references (visible to ``user``) by authority
        prefix, rolling subsection keys up to their section root — the unit
        the bootstrapper materialises (one document per section, mirroring
        the governance graph's ghost nodes). Returns entries sorted by
        mention volume::

            {"authority": "dgcl", "mention_count": 412, "key_count": 37,
             "corpus_count": 3,
             "top_keys": [{"canonical_key": "dgcl:145",
                           "mention_count": 80, "corpus_count": 3}, ...]}

        Aggregation is Python-side over (key, corpus) value rows: roots come
        from ``candidate_keys`` (regex on the key), which SQL can't express;
        row count equals the EXTERNAL-mention count, which stays modest.

        ``finalized_only`` excludes in-flight (``is_provisional``) references.
        The crawl seed passes ``True`` — irreversible ingestion must act only on
        finalized detections, never on the partial output of a still-running
        enrichment pass. The display/inventory callers leave it ``False`` so the
        References panel and ``list_wanted_authorities`` surface in-flight rows
        as they are found.
        """
        from opencontractserver.enrichment.authorities import candidate_keys

        # This aggregate never exposes a target FK (only canonical_key /
        # corpus_id), so it belongs on the source-only variant per the
        # documented split above — not the strict ``visible_to_user``, which
        # also gates on the (here-irrelevant) resolved target.
        qs = (
            cls.visible_to_user_by_source(user)
            .filter(
                reference_type=C.REF_LAW,
                resolution_status=C.STATUS_EXTERNAL,
            )
            .exclude(canonical_key=None)
        )
        if finalized_only:
            qs = qs.filter(is_provisional=False)
        if corpus_id is not None:
            qs = qs.filter(corpus_id=corpus_id)

        per_key: dict[str, dict] = {}  # root key -> {mentions, corpora}
        for key, ref_corpus_id in qs.values_list("canonical_key", "corpus_id"):
            root = candidate_keys(key)[-1]
            entry = per_key.setdefault(root, {"mentions": 0, "corpora": set()})
            entry["mentions"] += 1
            entry["corpora"].add(ref_corpus_id)

        per_authority: dict[str, dict] = {}
        for root, entry in per_key.items():
            authority = root.split(":", 1)[0]
            agg = per_authority.setdefault(
                authority, {"mentions": 0, "corpora": set(), "keys": {}}
            )
            agg["mentions"] += entry["mentions"]
            agg["corpora"] |= entry["corpora"]
            agg["keys"][root] = entry

        wanted = []
        for authority, agg in per_authority.items():
            top = sorted(
                agg["keys"].items(), key=lambda kv: (-kv[1]["mentions"], kv[0])
            )[:top_keys_n]
            wanted.append(
                {
                    "authority": authority,
                    "mention_count": agg["mentions"],
                    "key_count": len(agg["keys"]),
                    "corpus_count": len(agg["corpora"]),
                    "top_keys": [
                        {
                            "canonical_key": root,
                            "mention_count": entry["mentions"],
                            "corpus_count": len(entry["corpora"]),
                        }
                        for root, entry in top
                    ],
                }
            )
        wanted.sort(key=lambda w: (-w["mention_count"], w["authority"]))
        return wanted
