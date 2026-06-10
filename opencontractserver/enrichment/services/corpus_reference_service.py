"""Read surface for ``CorpusReference`` rows.

Visibility derives from corpus visibility — ``CorpusReference`` carries no
per-object guardian rows in v1.
"""

from __future__ import annotations

from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment import constants as C
from opencontractserver.shared.services.base import BaseService


class CorpusReferenceService(BaseService):
    """Read surface for CorpusReference rows."""

    @staticmethod
    def visible_to_user(user):
        return CorpusReference.objects.filter(
            corpus__in=Corpus.objects.visible_to_user(user)
        )

    @classmethod
    def for_corpus(cls, user, corpus_id: int):
        return cls.visible_to_user(user).filter(corpus_id=corpus_id)

    @classmethod
    def wanted_authorities(
        cls,
        user,
        corpus_id: int | None = None,
        top_keys_n: int = C.WANTED_AUTHORITIES_TOP_KEYS,
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
