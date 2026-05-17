"""Canonical Extract-setup helpers.

Mirrors :mod:`opencontractserver.utils.analysis`. Any user-facing flow that
creates an :class:`~opencontractserver.extracts.models.Extract` should go
through :func:`create_and_setup_extract` so the creator always receives
guardian CRUD and the row always surfaces correctly in GraphQL
``my_permissions`` / ``object_shared_with`` fields. Implementers do not
need to remember the grant — the framework guarantees it.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.extracts.models import Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


def create_and_setup_extract(
    user_id: int | str,
    *,
    corpus: Corpus,
    fieldset: Fieldset,
    name: str | None = None,
    document_ids: list[int] | None = None,
    corpus_action: CorpusAction | None = None,
    mark_started: bool = False,
) -> Extract:
    """Create an Extract, grant the creator CRUD, optionally link docs.

    Canonical chokepoint for Extract creation. Always grants the
    creator guardian CRUD on the new row via
    :func:`set_permissions_for_obj_to_user` (``is_new=True``) so the
    row surfaces correctly in GraphQL ``my_permissions`` /
    ``object_shared_with`` fields and in the user's "my extracts"
    filters. Mirrors :func:`opencontractserver.utils.analysis.create_and_setup_analysis`
    so the Extract and Analysis frameworks share one creation pattern.

    Args:
        user_id: PK of the user that owns the run. Becomes ``creator``
            and receives guardian CRUD.
        corpus: Corpus the extract is scoped to.
        fieldset: Fieldset whose columns drive extraction.
        name: Optional display name. Defaults to ``"Extract {fieldset}
            on {corpus}"``.
        document_ids: Optional list of Document PKs to link via
            ``extract.documents.add``. The caller is responsible for
            ensuring these are visible to the user and scoped to the
            corpus — this helper does not re-validate scope.
        corpus_action: Optional CorpusAction to attach for lineage
            tracking when this extract was queued by an automated
            corpus-action run.
        mark_started: When True, sets ``started=timezone.now()`` and
            ``finished=None`` inside the transaction (matches the
            timestamp posture used by ``process_corpus_action``). The
            Celery pipeline (``run_extract``) sets ``started`` itself,
            so agent / GraphQL paths that dispatch via the pipeline
            should leave this False.

    Returns:
        The persisted ``Extract`` instance.
    """

    extract_name = name or (f"Extract {fieldset.name} on {corpus.title or 'corpus'}")

    with transaction.atomic():
        extract = Extract.objects.create(
            corpus=corpus,
            name=extract_name,
            fieldset=fieldset,
            creator_id=user_id,
            corpus_action=corpus_action,
        )
        if mark_started:
            extract.started = timezone.now()
            extract.finished = None
            extract.save()
        set_permissions_for_obj_to_user(
            user_id, extract, [PermissionTypes.CRUD], is_new=True
        )
        if document_ids:
            extract.documents.add(*document_ids)

    logger.info(
        "create_and_setup_extract: extract=%s creator=%s docs=%s action=%s",
        extract.id,
        user_id,
        len(document_ids) if document_ids else 0,
        corpus_action.id if corpus_action else None,
    )
    return extract
