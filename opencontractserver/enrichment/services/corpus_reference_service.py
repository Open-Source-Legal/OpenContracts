"""Read surface for ``CorpusReference`` rows.

Visibility derives from corpus visibility — ``CorpusReference`` carries no
per-object guardian rows in v1.
"""

from __future__ import annotations

from opencontractserver.annotations.models import CorpusReference
from opencontractserver.corpuses.models import Corpus
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
