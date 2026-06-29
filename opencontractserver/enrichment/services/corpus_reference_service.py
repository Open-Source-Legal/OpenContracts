"""Read surface for ``CorpusReference`` rows.

Visibility derives from the readable parent corpus plus the readable source
and target objects carried by each row. ``CorpusReference`` carries no
per-object guardian rows in v1.
"""

from __future__ import annotations

from django.db.models import Q

from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.shared.services.base import BaseService


class CorpusReferenceService(BaseService):
    """Read surface for CorpusReference rows."""

    @staticmethod
    def visible_to_user_by_source(user):
        """References whose parent corpus AND source document are visible.

        Enforces corpus READ and source-annotation-document visibility, but
        does NOT filter on the resolved *target* (document / corpus /
        annotation). A citation made by a hidden document is suppressed (no
        source leak), but a citation TO a hidden target is RETAINED so the
        caller can degrade that target to a ghost rather than dropping the
        reference outright.

        Use this for aggregate surfaces that perform their own per-target
        ghosting (the governance graph re-checks both endpoints and degrades
        an invisible target to an external key node). For surfaces that expose
        the target foreign keys directly (e.g. the ``corpusReferences``
        GraphQL query), use :meth:`visible_to_user`, which additionally hides
        references whose target is invisible.
        """
        visible_corpora = Corpus.objects.visible_to_user(user)
        visible_documents = Document.objects.visible_to_user(user)

        return CorpusReference.objects.filter(
            corpus__in=visible_corpora,
            source_annotation__document__in=visible_documents,
        )

    @staticmethod
    def visible_to_user(user):
        """Return only references whose exposed graph is visible to ``user``.

        Corpus references are reachable from a readable corpus, but each row
        also carries document- and corpus-scoped foreign keys.  Apply the same
        MIN(document_permission, corpus_permission) rule used by user-facing
        corpus document surfaces so a readable corpus cannot disclose private
        source annotations or private resolved targets.

        Builds on :meth:`visible_to_user_by_source` (corpus + source) and adds
        the target-visibility filter, so a reference is hidden when its
        resolved target document / corpus / annotation is not visible. Callers
        that ghost invisible targets themselves should use
        :meth:`visible_to_user_by_source` instead so those references are not
        dropped before they can be degraded.
        """
        visible_corpora = Corpus.objects.visible_to_user(user)
        visible_documents = Document.objects.visible_to_user(user)

        return CorpusReferenceService.visible_to_user_by_source(user).filter(
            (Q(target_document__isnull=True) | Q(target_document__in=visible_documents))
            & (Q(target_corpus__isnull=True) | Q(target_corpus__in=visible_corpora))
            & (
                Q(target_annotation__isnull=True)
                | Q(target_annotation__document__in=visible_documents)
            )
        )

    @classmethod
    def for_corpus(cls, user, corpus_id: int):
        return cls.visible_to_user(user).filter(corpus_id=corpus_id)

    @classmethod
    def for_corpus_by_source(cls, user, corpus_id: int):
        """Corpus-scoped variant of :meth:`visible_to_user_by_source`.

        For callers (the governance graph) that ghost invisible targets
        themselves and so must not have target-hidden references pre-filtered.
        """
        return cls.visible_to_user_by_source(user).filter(corpus_id=corpus_id)

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

        qs = (
            cls.visible_to_user(user)
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
