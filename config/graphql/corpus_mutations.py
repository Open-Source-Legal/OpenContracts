"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
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

import logging
from typing import Annotated, Any

import strawberry
from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from graphql_relay import from_global_id, to_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from config.graphql.serializers import CorpusSerializer
from config.telemetry import record_event
from opencontractserver.analyzer.models import Analyzer
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionTemplate,
)
from opencontractserver.corpuses.services import (
    CorpusActionService,
    CorpusService,
)
from opencontractserver.corpuses.services.branding import (
    corpus_readme_will_be_auto_branded,
)
from opencontractserver.documents.models import Document
from opencontractserver.documents.versioning import calculate_content_version
from opencontractserver.extracts.models import Fieldset
from opencontractserver.shared.services.base import BaseService
from opencontractserver.tasks import fork_corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_collector import collect_corpus_objects
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


@strawberry.type(name="StartCorpusFork")
class StartCorpusFork:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    new_corpus: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="newCorpus", default=None)


register_type("StartCorpusFork", StartCorpusFork, model=None)


@strawberry.type(
    name="ReEmbedCorpus",
    description="Re-embed all annotations in a corpus with a different embedder (Issue #437).\n\nThis is the controlled migration path for changing a corpus's embedder\nafter documents have been added. It:\n1. Validates the new embedder exists in the registry\n2. Locks the corpus (backend_lock=True)\n3. Queues a background task that updates preferred_embedder and\n   generates new embeddings for all annotations\n4. The corpus unlocks automatically when re-embedding completes\n\nOnly the corpus creator can trigger re-embedding.",
)
class ReEmbedCorpus:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("ReEmbedCorpus", ReEmbedCorpus, model=None)


@strawberry.type(
    name="SetCorpusVisibility",
    description="Set corpus visibility (public/private).\n\nRequires one of:\n- User is the corpus creator (owner), OR\n- User has PERMISSION permission on the corpus, OR\n- User is superuser\n\nSecurity notes:\n- Permission check prevents users from escalating access\n- Uses existing make_corpus_public_task for cascading public visibility\n- Making private only affects the corpus flag (child objects remain public)",
)
class SetCorpusVisibility:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("SetCorpusVisibility", SetCorpusVisibility, model=None)


@strawberry.type(name="CreateCorpusMutation")
class CreateCorpusMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("CreateCorpusMutation", CreateCorpusMutation, model=None)


@strawberry.type(name="UpdateCorpusMutation")
class UpdateCorpusMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("UpdateCorpusMutation", UpdateCorpusMutation, model=None)


@strawberry.type(
    name="UpdateCorpusDescription",
    description="Mutation to update a corpus's markdown description, creating a new version in the process.\nOnly the corpus creator can update the description.",
)
class UpdateCorpusDescription:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="obj", default=None)
    version: int | None = strawberry.field(
        name="version", description="The new version number after update", default=None
    )


register_type("UpdateCorpusDescription", UpdateCorpusDescription, model=None)


@strawberry.type(name="DeleteCorpusMutation")
class DeleteCorpusMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteCorpusMutation", DeleteCorpusMutation, model=None)


@strawberry.type(
    name="AddDocumentsToCorpus",
    description="Add existing documents to a corpus.\n\nDelegates to CorpusDocumentService.add_documents_to_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Document validation (user owns or public)\n- Dual-system update (DocumentPath + corpus.add_document)",
)
class AddDocumentsToCorpus:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("AddDocumentsToCorpus", AddDocumentsToCorpus, model=None)


@strawberry.type(
    name="RemoveDocumentsFromCorpus",
    description="Remove documents from a corpus (soft-delete).\n\nDelegates to CorpusDocumentService.remove_documents_from_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Soft-delete via DocumentPath (creates is_deleted=True record)\n- Audit trail",
)
class RemoveDocumentsFromCorpus:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RemoveDocumentsFromCorpus", RemoveDocumentsFromCorpus, model=None)


@strawberry.type(
    name="CreateCorpusAction",
    description="Create a new CorpusAction that will be triggered when events occur in a corpus.\n\nAction types:\n- **Fieldset**: Run data extraction (fieldset_id)\n- **Analyzer**: Run classification/annotation (analyzer_id)\n- **Agent**: Execute an AI agent task. Provide task_instructions describing what the\n  agent should do. Optionally link an agent_config_id for custom persona/tool defaults,\n  or use create_agent_inline=True for thread/message moderation.\n- **Lightweight agent**: Just provide task_instructions (no agent_config needed).\n  The system auto-selects tools based on the trigger type.\n\nRequires UPDATE permission on the corpus.",
)
class CreateCorpusAction:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusActionType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateCorpusAction", CreateCorpusAction, model=None)


@strawberry.type(
    name="UpdateCorpusAction",
    description="Update an existing CorpusAction.\nAllows updating name, trigger, action type (fieldset/analyzer/agent), disabled state,\nand agent-specific settings.\nRequires the user to be the creator of the action.",
)
class UpdateCorpusAction:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusActionType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateCorpusAction", UpdateCorpusAction, model=None)


@strawberry.type(
    name="DeleteCorpusAction",
    description="Mutation to delete a CorpusAction.\nRequires the user to be the creator of the action or have appropriate permissions.",
)
class DeleteCorpusAction:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteCorpusAction", DeleteCorpusAction, model=None)


@strawberry.type(
    name="RunCorpusAction",
    description="Manually trigger a specific agent-based corpus action on a document.\n\nSuperuser-only. Creates a CorpusActionExecution record and dispatches\nthe run_agent_corpus_action Celery task.",
)
class RunCorpusAction:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            CorpusActionExecutionType, strawberry.lazy("config.graphql.agent_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("RunCorpusAction", RunCorpusAction, model=None)


@strawberry.type(
    name="StartCorpusActionBatchRun",
    description="Run an agent-based corpus action against every eligible document in the corpus.",
)
class StartCorpusActionBatchRun:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    queued_count: int | None = strawberry.field(
        name="queuedCount",
        description="Number of new CorpusActionExecution rows created.",
        default=None,
    )
    skipped_already_run_count: int | None = strawberry.field(
        name="skippedAlreadyRunCount",
        description="Active documents skipped because they already have a queued, running, or completed execution for this action.",
        default=None,
    )
    total_active_documents: int | None = strawberry.field(
        name="totalActiveDocuments",
        description="Total active documents in the corpus at evaluation time.",
        default=None,
    )
    executions: None | (
        list[
            None
            | (
                Annotated[
                    CorpusActionExecutionType,
                    strawberry.lazy("config.graphql.agent_types"),
                ]
            )
        ]
    ) = strawberry.field(
        name="executions",
        description="The freshly created execution rows (status=QUEUED).",
        default=None,
    )


register_type("StartCorpusActionBatchRun", StartCorpusActionBatchRun, model=None)


@strawberry.type(
    name="AddTemplateToCorpus",
    description="Add an action template to a corpus by cloning it into a CorpusAction.\n\nThis is the core of the Action Library feature: users browse available\ntemplates and opt-in per corpus. Once cloned, the action is a regular\nCorpusAction that can be edited/toggled/deleted like any other.\n\nPrevents duplicates: the same template cannot be added twice to the same\ncorpus (checked via source_template FK).\n\nRequires the user to be the corpus creator or have CRUD permission.",
)
class AddTemplateToCorpus:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusActionType, strawberry.lazy("config.graphql.agent_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("AddTemplateToCorpus", AddTemplateToCorpus, model=None)


@strawberry.type(
    name="SetupCorpusIntelligence",
    description="One-click collection-intelligence setup.\n\nComposes the default enrichment bundle in a single idempotent call:\ninstalls the reference-enrichment analyzer as an ``add_document`` action\nand starts the first weave (deterministic), then clones the description +\nsummary action templates and batch-runs each over every document already\nin the corpus (LLM). Safe to repeat — every step skips work that already\nexists. Requires CRUD permission on the corpus — the tier\nAddTemplateToCorpus and CreateCorpusAction gate the identical writes at.",
)
class SetupCorpusIntelligence:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    summary: None | (
        Annotated[
            CorpusIntelligenceSetupSummaryType,
            strawberry.lazy("config.graphql.corpus_types"),
        ]
    ) = strawberry.field(name="summary", default=None)


register_type("SetupCorpusIntelligence", SetupCorpusIntelligence, model=None)


@strawberry.type(
    name="ToggleCorpusMemory",
    description="Toggle the agent memory system on/off for a corpus.\n\nWhen enabled, agents accumulate reusable insights from conversations\ninto a memory document. The memory document is a first-class Document\nin the corpus, visible and editable by users.\n\nIMPORTANT: When memory is enabled, conversation patterns (NOT specific\ncontent) may be distilled into the memory document. Users should be\naware of this when discussing sensitive topics.\n\nRequires CRUD permission on the corpus.",
)
class ToggleCorpusMemory:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    corpus: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="corpus", default=None)


register_type("ToggleCorpusMemory", ToggleCorpusMemory, model=None)


@strawberry.type(
    name="CreateArtifact",
    description="Create a shareable poster (Artifact) of a corpus from a template.\n\nREAD-gated on the corpus (you can make a poster of any collection you can\nsee): its ``/a/<slug>`` link is shareable to anyone who can read the\nsource corpus (corpus-as-gate ONLY — there is no per-artifact visibility\noverride), and its data still only renders to viewers who can read the\ncorpus. ``template`` is validated against the service's registry.",
)
class CreateArtifact:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    artifact: None | (
        Annotated[ArtifactType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="artifact", default=None)


register_type("CreateArtifact", CreateArtifact, model=None)


@strawberry.type(
    name="UpdateArtifact",
    description="Edit an artifact's configurable captions — creator only.",
)
class UpdateArtifact:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    artifact: None | (
        Annotated[ArtifactType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="artifact", default=None)


register_type("UpdateArtifact", UpdateArtifact, model=None)


@strawberry.type(
    name="SetArtifactImage",
    description="Persist the rendered poster PNG so ``/a/<slug>`` has a stable og:image.\n\nThe poster is an SVG rendered client-side; the editor rasterises it and\nuploads the bytes here on save. (A production deploy can swap in a headless\nserver render behind the same field without changing the contract.)\nCreator-only.",
)
class SetArtifactImage:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    image_url: str | None = strawberry.field(name="imageUrl", default=None)


register_type("SetArtifactImage", SetArtifactImage, model=None)


def _mutate_StartCorpusFork(
    payload_cls, root, info, corpus_id, preferred_embedder=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:559

    Port of StartCorpusFork.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    ok = False
    message = ""
    new_corpus = None

    try:

        # Get annotation ids for the old corpus - these refer to a corpus, doc and label by id, so easaiest way to
        # copy these is to first filter by annotations for our corpus. Then, later, we'll use a dict to map old ids
        # for labels and docs to new obj ids
        # Pre-guard ``from_global_id``: a malformed base64 id raises before
        # the helper is reached, so catch it here and return the same
        # unified IDOR-safe message as a missing / hidden corpus.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return payload_cls(
                ok=False,
                message="Corpus not found or you don't have permission to fork it.",
                new_corpus=None,
            )

        # IDOR protection: ``get_for_user_or_none`` filters through
        # ``visible_to_user``, which already enforces READ — missing
        # pk and no-READ collapse to the same ``None`` return.
        corpus = get_for_user_or_none(Corpus, corpus_pk, info.context.user)
        if corpus is None:
            return payload_cls(
                ok=False,
                message="Corpus not found or you don't have permission to fork it.",
                new_corpus=None,
            )

        # Collect all object IDs using the shared collector
        collected = collect_corpus_objects(corpus, include_metadata=True)

        # Clone the corpus: https://docs.djangoproject.com/en/3.1/topics/db/queries/copying-model-instances
        corpus.pk = None
        corpus.slug = ""  # Clear slug so save() generates a new unique one

        # Adjust the title to indicate it's a fork
        corpus.title = f"[FORK] {corpus.title}"

        # Issue #437: Allow specifying a different embedder for the forked corpus.
        # If provided, the fork's ensure_embeddings_for_corpus will automatically
        # generate new embeddings using the target embedder when documents are added.
        if preferred_embedder:
            corpus.preferred_embedder = preferred_embedder

        # lock the corpus which will tell frontend to show this as loading and disable selection
        corpus.backend_lock = True
        corpus.creator = info.context.user  # switch the creator to the current user
        corpus.parent_id = corpus_pk
        corpus.save()

        set_permissions_for_obj_to_user(
            info.context.user,
            corpus,
            [PermissionTypes.CRUD],
            request=info.context,
        )

        # Now remove references to related objects on our new object, as these point to original docs and labels
        # Note: New forked corpus has no DocumentPath records yet, so no document cleanup needed
        corpus.label_set = None

        # Copy docs, annotations, folders, relationships, and metadata using async task
        # to avoid massive lag if we have large dataset or lots of users requesting copies.
        # Use on_commit to ensure corpus is persisted before task runs.
        # Capture args as defaults to avoid late-binding closure issues.
        def dispatch_fork_task(
            _corpus_id=corpus.id,
            _collected=collected,
            _user_id=info.context.user.id,
        ) -> Any:
            fork_corpus.si(
                _corpus_id,
                _collected.document_ids,
                _collected.label_set_id,
                _collected.annotation_ids,
                _collected.folder_ids,
                _collected.relationship_ids,
                _user_id,
                _collected.metadata_column_ids,
                _collected.metadata_datacell_ids,
            ).apply_async()

        transaction.on_commit(dispatch_fork_task)

        ok = True
        new_corpus = corpus

    except Exception as e:
        message = f"Error trying to fork corpus with id {corpus_id}: {e}"
        logger.error(message)

    record_event(
        "corpus_forked",
        {
            "env": settings.MODE,
            "user_id": info.context.user.id,
        },
    )

    return payload_cls(ok=ok, message=message, new_corpus=new_corpus)


def m_fork_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId",
            description="Graphene id of the corpus you want to package for export",
        ),
    ] = strawberry.UNSET,
    preferred_embedder: Annotated[
        str | None,
        strawberry.argument(
            name="preferredEmbedder",
            description="Override the embedder for the forked corpus. If provided and different from the source corpus, the fork will generate new embeddings using this embedder. If not provided, inherits the source corpus's preferred_embedder.",
        ),
    ] = strawberry.UNSET,
) -> StartCorpusFork | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "preferred_embedder": preferred_embedder}
    )
    return _mutate_StartCorpusFork(StartCorpusFork, None, info, **kwargs)


def _mutate_ReEmbedCorpus(payload_cls, root, info, corpus_id, new_embedder):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:700

    Port of ReEmbedCorpus.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.pipeline.base.embedder import BaseEmbedder
    from opencontractserver.pipeline.utils import get_component_by_name
    from opencontractserver.tasks.corpus_tasks import reembed_corpus

    user = info.context.user

    try:
        corpus_pk = from_global_id(corpus_id)[1]
    except Exception:
        return payload_cls(ok=False, message="Corpus not found")

    # IDOR protection: same response for missing pk, hidden pk, and
    # caller-is-not-creator.
    corpus = get_for_user_or_none(Corpus, corpus_pk, user)
    if corpus is None or corpus.creator != user:
        return payload_cls(ok=False, message="Corpus not found")

    # Validate the new embedder exists in the registry and is an embedder
    try:
        embedder_class = get_component_by_name(new_embedder)
        if embedder_class is None:
            return payload_cls(
                ok=False,
                message=f"Embedder '{new_embedder}' not found in the registry.",
            )
        if not issubclass(embedder_class, BaseEmbedder):
            return payload_cls(
                ok=False,
                message=f"'{new_embedder}' is not an embedder component.",
            )
    except Exception as e:
        return payload_cls(
            ok=False,
            message=f"Invalid embedder path: {e}",
        )

    # No-op if the embedder is already the same
    if corpus.preferred_embedder == new_embedder:
        return payload_cls(
            ok=True,
            message="Corpus already uses this embedder. No re-embedding needed.",
        )

    # Atomically lock the corpus to prevent concurrent re-embed operations.
    # Uses UPDATE ... WHERE to avoid TOCTOU race conditions.
    locked = Corpus.objects.filter(pk=corpus.pk, backend_lock=False).update(
        backend_lock=True, modified=timezone.now()
    )

    if locked == 0:
        return payload_cls(
            ok=False,
            message="Corpus is currently locked by another operation. "
            "Please wait for it to complete.",
        )

    transaction.on_commit(
        lambda: reembed_corpus.delay(
            corpus_id=corpus.pk,
            new_embedder_path=new_embedder,
        )
    )

    return payload_cls(
        ok=True,
        message=f"Re-embedding started. The corpus will use "
        f"'{new_embedder}' once complete.",
    )


def m_re_embed_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="Global ID of the corpus to re-embed"
        ),
    ] = strawberry.UNSET,
    new_embedder: Annotated[
        str,
        strawberry.argument(
            name="newEmbedder",
            description="Fully qualified Python path to the new embedder class (e.g., 'opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder')",
        ),
    ] = strawberry.UNSET,
) -> ReEmbedCorpus | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "new_embedder": new_embedder})
    return _mutate_ReEmbedCorpus(ReEmbedCorpus, None, info, **kwargs)


def _mutate_SetCorpusVisibility(payload_cls, root, info, corpus_id, is_public):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:83

    Port of SetCorpusVisibility.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit is applied to an inner ``mutate`` so the calling
    # convention (root, info, ...) and the rate-limit cache group ("mutate")
    # match the graphene original.
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id, is_public):
        user = info.context.user

        # IDOR protection: same response whether the global ID is malformed,
        # the corpus doesn't exist, the caller can't READ it, or the caller
        # can READ but lacks PERMISSION. ``get_for_user_or_none`` enforces the
        # READ gate; ``CorpusService.set_visibility`` adds the PERMISSION check.
        not_found_msg = "Corpus not found or you don't have permission"

        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return payload_cls(ok=False, message=not_found_msg)

        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return payload_cls(ok=False, message=not_found_msg)

        result = CorpusService.set_visibility(
            user, corpus, is_public, request=info.context
        )
        return payload_cls(
            ok=result.ok,
            message=result.value if result.ok else result.error,
        )

    return mutate(root, info, corpus_id=corpus_id, is_public=is_public)


def m_set_corpus_visibility(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="ID of the corpus to change visibility for"
        ),
    ] = strawberry.UNSET,
    is_public: Annotated[
        bool,
        strawberry.argument(
            name="isPublic", description="True to make public, False to make private"
        ),
    ] = strawberry.UNSET,
) -> SetCorpusVisibility | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "is_public": is_public})
    return _mutate_SetCorpusVisibility(SetCorpusVisibility, None, info, **kwargs)


def _mutate_CreateCorpusMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.corpus_mutations.CreateCorpusMutation.mutate

    Port of CreateCorpusMutation.mutate
    """
    # Pre-fill the install-wide default LabelSet when the caller didn't
    # pick one, so corpuses created through the API land with a usable
    # starter palette. We default here (mutation layer) rather than in
    # Corpus.save() to keep direct ORM creates in tests/scripts opt-in.
    if not kwargs.get("label_set"):
        from opencontractserver.annotations.models import LabelSet

        default_labelset = (
            BaseService.filter_visible(
                LabelSet, info.context.user, request=info.context
            )
            .filter(is_default=True)
            .first()
        )
        if default_labelset is not None:
            kwargs["label_set"] = to_global_id("LabelSetType", default_labelset.pk)

    # ``super().mutate()`` in the graphene original — the DRF create/update
    # recipe (login gate, WRITE_MEDIUM rate limit, serializer validation,
    # CRUD grant) now lives in ``config.graphql.core.mutations.drf_mutation``.
    result = drf_mutation(
        payload_cls=payload_cls,
        model=Corpus,
        serializer=CorpusSerializer,
        type_name="CorpusType",
        pk_fields=("label_set", "categories"),
        lookup_field="id",
        root=root,
        info=info,
        kwargs=kwargs,
    )

    if result.ok and result.obj_id:
        obj_pk = from_global_id(result.obj_id)[1]
        corpus = Corpus.objects.get(pk=obj_pk)
        # Grant creator full permissions including PERMISSION to manage access
        CorpusService.grant_creator_permissions(
            info.context.user, corpus, request=info.context
        )

        # Deterministic structural Readme.CAML so the corpus composes the
        # live intelligence overview by default. The LLM auto-branding agent
        # (queued by the post_save signal) writes its own README when it
        # runs, so only seed the structural default when branding will NOT
        # produce one — otherwise the default would pre-empt the agent (its
        # ``readme_caml_document_id`` guard skips if an article exists). The
        # README agent runs only when branding is eligible AND no icon was
        # uploaded (the signal skips the whole task on an uploaded icon), so
        # mirror that exact condition here. Creator-gated inside the service.
        readme_agent_will_run = (
            corpus_readme_will_be_auto_branded(corpus) and not corpus.icon
        )
        if not readme_agent_will_run:
            CorpusService.ensure_readme_caml_default(info.context.user, corpus)

    return result


def m_create_corpus(
    info: strawberry.Info,
    categories: Annotated[
        list[strawberry.ID | None] | None,
        strawberry.argument(name="categories", description="Category IDs to assign"),
    ] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    label_set: Annotated[
        str | None, strawberry.argument(name="labelSet")
    ] = strawberry.UNSET,
    license: Annotated[
        str | None,
        strawberry.argument(
            name="license", description="SPDX license identifier (e.g. CC-BY-4.0)"
        ),
    ] = strawberry.UNSET,
    license_link: Annotated[
        str | None,
        strawberry.argument(
            name="licenseLink",
            description="URL to full license text (required for CUSTOM license)",
        ),
    ] = strawberry.UNSET,
    preferred_embedder: Annotated[
        str | None, strawberry.argument(name="preferredEmbedder")
    ] = strawberry.UNSET,
    preferred_llm: Annotated[
        str | None,
        strawberry.argument(
            name="preferredLlm",
            description="Optional pydantic-ai model spec for this corpus's agents (e.g. 'anthropic:claude-opus-4-6'). When unset, agents fall back to settings.DEFAULT_LLM / settings.OPENAI_MODEL.",
        ),
    ] = strawberry.UNSET,
    slug: Annotated[str | None, strawberry.argument(name="slug")] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
) -> CreateCorpusMutation | None:
    kwargs = strip_unset(
        {
            "categories": categories,
            "description": description,
            "icon": icon,
            "label_set": label_set,
            "license": license,
            "license_link": license_link,
            "preferred_embedder": preferred_embedder,
            "preferred_llm": preferred_llm,
            "slug": slug,
            "title": title,
        }
    )
    return _mutate_CreateCorpusMutation(CreateCorpusMutation, None, info, **kwargs)


def _mutate_UpdateCorpusMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.corpus_mutations.UpdateCorpusMutation.mutate

    Port of UpdateCorpusMutation.mutate
    """
    # Issue #437: Prevent changing preferred_embedder after documents exist.
    # This avoids creating inconsistent embeddings within a corpus.
    # Use the ReEmbedCorpus mutation instead for controlled embedder
    # migration. We filter through ``visible_to_user`` so a caller who
    # can't see the corpus doesn't get a leaked "this corpus has docs"
    # signal from the early-exit — they fall through to the parent's
    # standard not-found / not-permitted response.
    if "preferred_embedder" in kwargs:
        corpus_global_id = kwargs.get("id")
        if corpus_global_id:
            # A malformed base64 id raises in ``from_global_id``; skip the
            # pre-check and let the parent ``super().mutate()`` return its
            # standard not-found / not-permitted response.
            try:
                corpus_pk = from_global_id(corpus_global_id)[1]
            except Exception:
                corpus_pk = None
            corpus = (
                get_for_user_or_none(Corpus, corpus_pk, info.context.user)
                if corpus_pk is not None
                else None
            )
            if corpus is not None:
                embedder_error = CorpusService.assert_embedder_change_allowed(
                    corpus, kwargs["preferred_embedder"]
                )
                if embedder_error:
                    return payload_cls(ok=False, message=embedder_error)

    # ``super().mutate()`` in the graphene original (see
    # _mutate_CreateCorpusMutation).
    return drf_mutation(
        payload_cls=payload_cls,
        model=Corpus,
        serializer=CorpusSerializer,
        type_name="CorpusType",
        pk_fields=("label_set", "categories"),
        lookup_field="id",
        root=root,
        info=info,
        kwargs=kwargs,
    )


def m_update_corpus(
    info: strawberry.Info,
    categories: Annotated[
        list[strawberry.ID | None] | None,
        strawberry.argument(
            name="categories", description="Category IDs to assign (replaces existing)"
        ),
    ] = strawberry.UNSET,
    corpus_agent_instructions: Annotated[
        str | None, strawberry.argument(name="corpusAgentInstructions")
    ] = strawberry.UNSET,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    document_agent_instructions: Annotated[
        str | None, strawberry.argument(name="documentAgentInstructions")
    ] = strawberry.UNSET,
    icon: Annotated[str | None, strawberry.argument(name="icon")] = strawberry.UNSET,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
    label_set: Annotated[
        str | None, strawberry.argument(name="labelSet")
    ] = strawberry.UNSET,
    license: Annotated[
        str | None,
        strawberry.argument(
            name="license", description="SPDX license identifier (e.g. CC-BY-4.0)"
        ),
    ] = strawberry.UNSET,
    license_link: Annotated[
        str | None,
        strawberry.argument(
            name="licenseLink",
            description="URL to full license text (required for CUSTOM license)",
        ),
    ] = strawberry.UNSET,
    preferred_embedder: Annotated[
        str | None, strawberry.argument(name="preferredEmbedder")
    ] = strawberry.UNSET,
    preferred_llm: Annotated[
        str | None,
        strawberry.argument(
            name="preferredLlm",
            description="Optional pydantic-ai model spec for this corpus's agents (e.g. 'anthropic:claude-opus-4-6'). Pass empty string to clear and fall back to settings.DEFAULT_LLM / settings.OPENAI_MODEL.",
        ),
    ] = strawberry.UNSET,
    slug: Annotated[str | None, strawberry.argument(name="slug")] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
) -> UpdateCorpusMutation | None:
    kwargs = strip_unset(
        {
            "categories": categories,
            "corpus_agent_instructions": corpus_agent_instructions,
            "description": description,
            "document_agent_instructions": document_agent_instructions,
            "icon": icon,
            "id": id,
            "label_set": label_set,
            "license": license,
            "license_link": license_link,
            "preferred_embedder": preferred_embedder,
            "preferred_llm": preferred_llm,
            "slug": slug,
            "title": title,
        }
    )
    return _mutate_UpdateCorpusMutation(UpdateCorpusMutation, None, info, **kwargs)


def _mutate_UpdateCorpusDescription(payload_cls, root, info, corpus_id, new_content):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:279

    Port of UpdateCorpusDescription.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.corpuses.models import Corpus

    try:
        user = info.context.user
        corpus_pk = from_global_id(corpus_id)[1]

        # Unified message prevents IDOR enumeration of corpora the caller cannot edit
        not_found_msg = "Corpus not found or you do not have permission to update it."

        # ``get_for_user_or_none`` enforces the READ gate;
        # ``CorpusService.update_description`` enforces the creator-only
        # rule (collaborators with a guardian UPDATE grant still cannot
        # edit the description, so its history stays attributable to a
        # single author) and returns the same unified IDOR-safe message.
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return payload_cls(ok=False, message=not_found_msg, obj=None, version=None)

        result = CorpusService.update_description(user, corpus, new_content)
        if not result.ok:
            return payload_cls(ok=False, message=result.error, obj=None, version=None)
        new_caml_doc = result.value

        if new_caml_doc is None:
            # No changes were made — return the current version count so
            # the caller knows where the description stands. The version
            # count reads from the legacy ``Corpus.revisions`` relation
            # as a transitional signal; it should be replaced by the
            # Readme.CAML version-tree count once the frontend migrates.
            return payload_cls(
                ok=True,
                message="No changes detected. Description remains at current version.",
                obj=corpus,
                version=corpus.revisions.count(),
            )

        # Refresh the corpus to get the updated state (the signal
        # cascaded the cache columns onto the row).
        corpus.refresh_from_db()

        # Derive the version from the Readme.CAML content-tree —
        # ``import_document`` returns the new head and the version is
        # the count of ancestors up the version_tree (Rule C2). This
        # matches what the GraphQL schema previously surfaced (the
        # 1-indexed ``CorpusDescriptionRevision.version`` counter).
        new_version = calculate_content_version(new_caml_doc)

        return payload_cls(
            ok=True,
            message=f"Corpus description updated successfully. Now at version {new_version}.",
            obj=corpus,
            version=new_version,
        )

    except Exception as e:
        logger.error(f"Error updating corpus description: {e}")
        return payload_cls(
            ok=False,
            message=f"Failed to update corpus description: {str(e)}",
            obj=None,
            version=None,
        )


def m_update_corpus_description(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="corpusId", description="ID of the corpus to update"),
    ] = strawberry.UNSET,
    new_content: Annotated[
        str,
        strawberry.argument(
            name="newContent",
            description="New markdown content for the corpus description",
        ),
    ] = strawberry.UNSET,
) -> UpdateCorpusDescription | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "new_content": new_content})
    return _mutate_UpdateCorpusDescription(
        UpdateCorpusDescription, None, info, **kwargs
    )


def _mutate_DeleteCorpusMutation(payload_cls, root, info, id):
    """PORT: config.graphql.corpus_mutations.DeleteCorpusMutation.mutate

    Port of DeleteCorpusMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, id):
        # Unified IDOR-safe envelope: same response whether the corpus
        # doesn't exist, the caller can't see it, or they can see it but
        # lack DELETE permission.  ``get_for_user_or_none`` enforces the READ
        # gate; ``CorpusService.delete_corpus`` runs the personal-corpus,
        # user-lock, and DELETE-permission checks. Returning ``ok=False``
        # (rather than raising ``Corpus.DoesNotExist``) keeps the response
        # shape consistent so the frontend can always pattern-match on
        # ``data.deleteCorpus.ok``.
        not_found_msg = "Corpus not found or you don't have permission to delete it."

        try:
            corpus_pk = from_global_id(id)[1]
        except Exception:
            return payload_cls(ok=False, message=not_found_msg)

        obj = get_for_user_or_none(Corpus, corpus_pk, info.context.user)
        if obj is None:
            return payload_cls(ok=False, message=not_found_msg)

        result = CorpusService.delete_corpus(
            info.context.user, obj, request=info.context
        )
        return payload_cls(
            ok=result.ok,
            message="Success!" if result.ok else result.error,
        )

    return mutate(root, info, id=id)


def m_delete_corpus(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteCorpusMutation | None:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteCorpusMutation(DeleteCorpusMutation, None, info, **kwargs)


def _mutate_AddDocumentsToCorpus(payload_cls, root, info, corpus_id, document_ids):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:412

    Port of AddDocumentsToCorpus.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.corpuses.services import CorpusDocumentService

    # Unified message prevents enumeration of corpora the caller cannot see/edit
    not_found_msg = (
        "Corpus not found or you do not have permission to add documents to it"
    )
    # Decode global ids up-front so a malformed id surfaces as a clean
    # envelope rather than echoing raw exception text through the outer
    # ``except Exception`` (IDOR review on PR #1693). The corpus and the
    # document ids are decoded separately so a malformed *document* id
    # does not return a misleading corpus-scoped message.
    try:
        corpus_pk = from_global_id(corpus_id)[1]
    except Exception:
        return payload_cls(message=not_found_msg, ok=False)
    try:
        doc_pks = [int(from_global_id(doc_id)[1]) for doc_id in document_ids]
    except Exception:
        return payload_cls(message="One or more document ids are invalid", ok=False)
    try:
        user = info.context.user
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return payload_cls(message=not_found_msg, ok=False)

        # Delegate to service - handles permission checks, validation, dual-system update
        added_count, added_ids, error = CorpusDocumentService.add_documents_to_corpus(
            user=user,
            document_ids=doc_pks,
            corpus=corpus,
            folder=None,  # No folder specified - add to root
            request=info.context,
        )

        if error:
            return payload_cls(message=error, ok=False)

        return payload_cls(
            message=f"Successfully added {added_count} document(s)",
            ok=True,
        )

    except Exception as e:
        return payload_cls(message=f"Error on upload: {e}", ok=False)


def m_link_documents_to_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of corpus to add documents to."
        ),
    ] = strawberry.UNSET,
    document_ids: Annotated[
        list[str | None],
        strawberry.argument(
            name="documentIds", description="List of ids of the docs to add to corpus."
        ),
    ] = strawberry.UNSET,
) -> AddDocumentsToCorpus | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_ids": document_ids})
    return _mutate_AddDocumentsToCorpus(AddDocumentsToCorpus, None, info, **kwargs)


def _mutate_RemoveDocumentsFromCorpus(
    payload_cls, root, info, corpus_id, document_ids_to_remove
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:486

    Port of RemoveDocumentsFromCorpus.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.corpuses.services import CorpusDocumentService

    # Unified message prevents enumeration of corpora the caller cannot see/edit
    not_found_msg = (
        "Corpus not found or you do not have permission to remove documents from it"
    )
    # Decode global ids up-front so a malformed id surfaces as a clean
    # envelope rather than echoing raw exception text through the outer
    # ``except Exception`` (IDOR review on PR #1693). The corpus and the
    # document ids are decoded separately so a malformed *document* id
    # does not return a misleading corpus-scoped message.
    try:
        corpus_pk = from_global_id(corpus_id)[1]
    except Exception:
        return payload_cls(message=not_found_msg, ok=False)
    try:
        doc_pks = [int(from_global_id(doc_id)[1]) for doc_id in document_ids_to_remove]
    except Exception:
        return payload_cls(message="One or more document ids are invalid", ok=False)
    try:
        user = info.context.user
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return payload_cls(message=not_found_msg, ok=False)

        # Delegate to service - handles permission checks, soft-delete, audit trail
        removed_count, error = CorpusDocumentService.remove_documents_from_corpus(
            user=user,
            document_ids=doc_pks,
            corpus=corpus,
            request=info.context,
        )

        if error:
            return payload_cls(message=error, ok=False)

        return payload_cls(
            message=f"Successfully removed {removed_count} document(s)",
            ok=True,
        )

    except Exception as e:
        return payload_cls(message=f"Error on removal: {e}", ok=False)


def m_remove_documents_from_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of corpus to remove documents from."
        ),
    ] = strawberry.UNSET,
    document_ids_to_remove: Annotated[
        list[str | None],
        strawberry.argument(
            name="documentIdsToRemove",
            description="List of ids of the docs to remove from corpus.",
        ),
    ] = strawberry.UNSET,
) -> RemoveDocumentsFromCorpus | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "document_ids_to_remove": document_ids_to_remove}
    )
    return _mutate_RemoveDocumentsFromCorpus(
        RemoveDocumentsFromCorpus, None, info, **kwargs
    )


def _mutate_CreateCorpusAction(
    payload_cls,
    root,
    info,
    corpus_id: str,
    trigger: str,
    name: str | None = None,
    fieldset_id: str | None = None,
    analyzer_id: str | None = None,
    task_instructions: str | None = None,
    agent_config_id: str | None = None,
    pre_authorized_tools: list | None = None,
    create_agent_inline: bool = False,
    inline_agent_name: str | None = None,
    inline_agent_description: str | None = None,
    inline_agent_instructions: str | None = None,
    inline_agent_tools: list | None = None,
    disabled: bool = False,
    run_on_all_corpuses: bool = False,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:854

    Port of CreateCorpusAction.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.agents.models import AgentConfiguration

    try:
        user = info.context.user
        no_permission_msg = "You don't have permission to create actions on this corpus"
        # Pre-guard ``from_global_id``: a malformed base64 id raises before
        # the helper is reached — return the same unified message as a
        # missing / hidden / no-permission corpus.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return payload_cls(ok=False, message=no_permission_msg, obj=None)

        # Get corpus with visibility filter to prevent IDOR. ``None``
        # short-circuits to the same unified message as a no-CRUD result
        # so missing / hidden / no-permission look identical to the caller.
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None or BaseService.require_permission(
            corpus, user, PermissionTypes.CRUD, request=info.context
        ):
            return payload_cls(
                ok=False,
                message=no_permission_msg,
                obj=None,
            )

        # Validate inline agent creation parameters
        if create_agent_inline:
            if not inline_agent_name:
                return payload_cls(
                    ok=False,
                    message="inline_agent_name is required when create_agent_inline=True",
                    obj=None,
                )
            if not inline_agent_instructions:
                return payload_cls(
                    ok=False,
                    message="inline_agent_instructions is required when create_agent_inline=True",
                    obj=None,
                )
            if not task_instructions:
                return payload_cls(
                    ok=False,
                    message="task_instructions is required when creating an agent action",
                    obj=None,
                )
            # Cannot provide both inline creation and existing agent
            if agent_config_id:
                return payload_cls(
                    ok=False,
                    message="Cannot provide both agent_config_id and create_agent_inline=True",
                    obj=None,
                )

        # For thread/message triggers with inline agent, validate tools are moderation category.
        if create_agent_inline and trigger in ["new_thread", "new_message"]:
            from opencontractserver.llms.tools.tool_registry import (
                TOOL_REGISTRY,
                ToolCategory,
            )

            valid_moderation_tools = {
                tool.name
                for tool in TOOL_REGISTRY
                if tool.category == ToolCategory.MODERATION
            }

            if not inline_agent_tools:
                return payload_cls(
                    ok=False,
                    message="At least one tool is required for moderation agents. "
                    f"Available moderation tools: {', '.join(sorted(valid_moderation_tools))}",
                    obj=None,
                )

            invalid_tools = set(inline_agent_tools) - valid_moderation_tools
            if invalid_tools:
                return payload_cls(
                    ok=False,
                    message=f"Invalid tools for moderation agent: {', '.join(sorted(invalid_tools))}. "
                    f"Valid moderation tools: {', '.join(sorted(valid_moderation_tools))}",
                    obj=None,
                )

        # Determine action type: fieldset, analyzer, agent (with config),
        # agent (inline), or lightweight agent (task_instructions only)
        has_fieldset = bool(fieldset_id)
        has_analyzer = bool(analyzer_id)
        has_agent_config = bool(agent_config_id)
        has_inline_agent = bool(create_agent_inline)
        has_task_instructions = bool(task_instructions)

        # Fieldset/analyzer/agent_config/inline are mutually exclusive
        fk_count = sum([has_fieldset, has_analyzer, has_agent_config, has_inline_agent])
        if fk_count > 1:
            return payload_cls(
                ok=False,
                message=(
                    "Only one of fieldset_id, analyzer_id, "
                    "agent_config_id, or create_agent_inline can be provided"
                ),
                obj=None,
            )

        # Must have at least one action type
        if fk_count == 0 and not has_task_instructions:
            return payload_cls(
                ok=False,
                message=(
                    "Provide one of: fieldset_id, analyzer_id, agent_config_id, "
                    "create_agent_inline, or task_instructions"
                ),
                obj=None,
            )

        # task_instructions is required for all agent-type actions
        if (has_agent_config or has_inline_agent) and not has_task_instructions:
            return payload_cls(
                ok=False,
                message="task_instructions is required for agent actions",
                obj=None,
            )

        # task_instructions must not be set on fieldset/analyzer actions
        if (has_fieldset or has_analyzer) and has_task_instructions:
            return payload_cls(
                ok=False,
                message="task_instructions cannot be set on fieldset or analyzer actions",
                obj=None,
            )

        # Get fieldset, analyzer, or agent_config if provided
        fieldset = None
        analyzer = None
        agent_config = None

        if fieldset_id:
            fieldset_pk = from_global_id(fieldset_id)[1]
            fieldset = BaseService.get_or_none(
                Fieldset, fieldset_pk, user, request=info.context
            )
            if fieldset is None:
                raise Fieldset.DoesNotExist

        if analyzer_id:
            analyzer_pk = from_global_id(analyzer_id)[1]
            analyzer = BaseService.get_or_none(
                Analyzer, analyzer_pk, user, request=info.context
            )
            if analyzer is None:
                raise Analyzer.DoesNotExist

        if agent_config_id:
            agent_config_pk = from_global_id(agent_config_id)[1]
            agent_config = BaseService.get_or_none(
                AgentConfiguration,
                agent_config_pk,
                user,
                request=info.context,
            )
            if agent_config is None:
                raise AgentConfiguration.DoesNotExist
            if not agent_config.is_active:
                return payload_cls(
                    ok=False,
                    message="The selected agent configuration is not active",
                    obj=None,
                )

        # Create inline agent if requested (wrapped in transaction with action creation)
        if create_agent_inline:
            # Validation above guarantees both are populated when reaching here,
            # but use an explicit guard (not assert) so -O optimised builds are safe.
            if inline_agent_name is None or inline_agent_instructions is None:
                raise ValueError(
                    "inline_agent_name and inline_agent_instructions are required "
                    "when create_agent_inline=True"
                )
            with transaction.atomic():
                agent_config = AgentConfiguration.objects.create(
                    name=inline_agent_name,
                    description=inline_agent_description
                    or f"Moderator agent for {corpus.title}",
                    system_instructions=inline_agent_instructions,
                    available_tools=inline_agent_tools or [],
                    permission_required_tools=[],
                    badge_config={
                        "icon": "shield",
                        "color": "#6366f1",
                        "label": "Moderator",
                    },
                    scope="CORPUS",
                    corpus=corpus,
                    creator=user,
                    is_active=True,
                    is_public=False,
                )

                set_permissions_for_obj_to_user(
                    user,
                    agent_config,
                    [PermissionTypes.CRUD],
                    request=info.context,
                )

                corpus_action = CorpusAction.objects.create(
                    name=name or "Corpus Action",
                    corpus=corpus,
                    fieldset=fieldset,
                    analyzer=analyzer,
                    agent_config=agent_config,
                    task_instructions=task_instructions or "",
                    pre_authorized_tools=pre_authorized_tools or [],
                    trigger=trigger,
                    disabled=disabled,
                    run_on_all_corpuses=run_on_all_corpuses,
                    creator=user,
                )

                set_permissions_for_obj_to_user(
                    user,
                    corpus_action,
                    [PermissionTypes.CRUD],
                    request=info.context,
                )

                return payload_cls(
                    ok=True,
                    message="Successfully created corpus action with inline agent",
                    obj=corpus_action,
                )

        # Standard path: Create the corpus action
        corpus_action = CorpusAction.objects.create(
            name=name or "Corpus Action",
            corpus=corpus,
            fieldset=fieldset,
            analyzer=analyzer,
            agent_config=agent_config,
            task_instructions=task_instructions or "",
            pre_authorized_tools=pre_authorized_tools or [],
            trigger=trigger,
            disabled=disabled,
            run_on_all_corpuses=run_on_all_corpuses,
            creator=user,
        )

        set_permissions_for_obj_to_user(
            user,
            corpus_action,
            [PermissionTypes.CRUD],
            request=info.context,
        )

        return payload_cls(
            ok=True, message="Successfully created corpus action", obj=corpus_action
        )

    except AgentConfiguration.DoesNotExist:
        return payload_cls(
            ok=False,
            message="Agent configuration not found",
            obj=None,
        )

    except Exception as e:
        return payload_cls(
            ok=False, message=f"Failed to create corpus action: {str(e)}", obj=None
        )


def m_create_corpus_action(
    info: strawberry.Info,
    agent_config_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="agentConfigId",
            description="Optional agent configuration for persona/tool defaults. Not required — task_instructions alone is sufficient for agent actions.",
        ),
    ] = strawberry.UNSET,
    analyzer_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(name="analyzerId", description="ID of the analyzer to run"),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="ID of the corpus this action is for"
        ),
    ] = strawberry.UNSET,
    create_agent_inline: Annotated[
        bool | None,
        strawberry.argument(
            name="createAgentInline",
            description="Create a new agent inline instead of using existing agent_config_id",
        ),
    ] = strawberry.UNSET,
    disabled: Annotated[
        bool | None,
        strawberry.argument(
            name="disabled", description="Whether the action is disabled"
        ),
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(name="fieldsetId", description="ID of the fieldset to run"),
    ] = strawberry.UNSET,
    inline_agent_description: Annotated[
        str | None,
        strawberry.argument(
            name="inlineAgentDescription",
            description="Description for the new inline agent",
        ),
    ] = strawberry.UNSET,
    inline_agent_instructions: Annotated[
        str | None,
        strawberry.argument(
            name="inlineAgentInstructions",
            description="System instructions for the new inline agent (required if create_agent_inline=True)",
        ),
    ] = strawberry.UNSET,
    inline_agent_name: Annotated[
        str | None,
        strawberry.argument(
            name="inlineAgentName",
            description="Name for the new inline agent (required if create_agent_inline=True)",
        ),
    ] = strawberry.UNSET,
    inline_agent_tools: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="inlineAgentTools",
            description="Tools available to the new inline agent",
        ),
    ] = strawberry.UNSET,
    name: Annotated[
        str | None,
        strawberry.argument(name="name", description="Name of the action"),
    ] = strawberry.UNSET,
    pre_authorized_tools: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="preAuthorizedTools",
            description="Tools pre-authorized to run without approval. If empty, uses agent_config tools or trigger-appropriate defaults.",
        ),
    ] = strawberry.UNSET,
    run_on_all_corpuses: Annotated[
        bool | None,
        strawberry.argument(
            name="runOnAllCorpuses",
            description="Whether to run this action on all corpuses",
        ),
    ] = strawberry.UNSET,
    task_instructions: Annotated[
        str | None,
        strawberry.argument(
            name="taskInstructions",
            description="What the agent should do. This is the single required field for agent actions (e.g., 'Read this document and update its description with a one-paragraph summary').",
        ),
    ] = strawberry.UNSET,
    trigger: Annotated[
        str,
        strawberry.argument(
            name="trigger",
            description="When to trigger: add_document, edit_document, new_thread, new_message",
        ),
    ] = strawberry.UNSET,
) -> CreateCorpusAction | None:
    kwargs = strip_unset(
        {
            "agent_config_id": agent_config_id,
            "analyzer_id": analyzer_id,
            "corpus_id": corpus_id,
            "create_agent_inline": create_agent_inline,
            "disabled": disabled,
            "fieldset_id": fieldset_id,
            "inline_agent_description": inline_agent_description,
            "inline_agent_instructions": inline_agent_instructions,
            "inline_agent_name": inline_agent_name,
            "inline_agent_tools": inline_agent_tools,
            "name": name,
            "pre_authorized_tools": pre_authorized_tools,
            "run_on_all_corpuses": run_on_all_corpuses,
            "task_instructions": task_instructions,
            "trigger": trigger,
        }
    )
    return _mutate_CreateCorpusAction(CreateCorpusAction, None, info, **kwargs)


def _mutate_UpdateCorpusAction(
    payload_cls,
    root,
    info,
    id: str,
    name: str | None = None,
    trigger: str | None = None,
    fieldset_id: str | None = None,
    analyzer_id: str | None = None,
    agent_config_id: str | None = None,
    task_instructions: str | None = None,
    pre_authorized_tools: list | None = None,
    disabled: bool | None = None,
    run_on_all_corpuses: bool | None = None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1196

    Port of UpdateCorpusAction.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.agents.models import AgentConfiguration

    try:
        user = info.context.user
        action_pk = from_global_id(id)[1]

        # Get the corpus action via service layer (IDOR-safe).
        corpus_action = BaseService.get_or_none(
            CorpusAction, action_pk, user, request=info.context
        )
        if corpus_action is None:
            raise CorpusAction.DoesNotExist

        # Check if user is the creator
        if corpus_action.creator.id != user.id:
            return payload_cls(
                ok=False,
                message="You can only update your own corpus actions",
                obj=None,
            )

        # Update simple fields if provided
        if name is not None:
            corpus_action.name = name

        if trigger is not None:
            corpus_action.trigger = trigger

        if disabled is not None:
            corpus_action.disabled = disabled

        if run_on_all_corpuses is not None:
            corpus_action.run_on_all_corpuses = run_on_all_corpuses

        # Handle action type changes (fieldset, analyzer, or agent)
        # If any of these are provided, clear the others and set the new one
        if fieldset_id is not None:
            fieldset_pk = from_global_id(fieldset_id)[1]
            fieldset = BaseService.get_or_none(
                Fieldset, fieldset_pk, user, request=info.context
            )
            if fieldset is None:
                raise Fieldset.DoesNotExist
            corpus_action.fieldset = fieldset
            corpus_action.analyzer = None
            corpus_action.agent_config = None
            corpus_action.task_instructions = ""
            corpus_action.pre_authorized_tools = []

        elif analyzer_id is not None:
            analyzer_pk = from_global_id(analyzer_id)[1]
            analyzer = BaseService.get_or_none(
                Analyzer, analyzer_pk, user, request=info.context
            )
            if analyzer is None:
                raise Analyzer.DoesNotExist
            corpus_action.analyzer = analyzer
            corpus_action.fieldset = None
            corpus_action.agent_config = None
            corpus_action.task_instructions = ""
            corpus_action.pre_authorized_tools = []

        elif agent_config_id is not None:
            agent_config_pk = from_global_id(agent_config_id)[1]
            agent_config = BaseService.get_or_none(
                AgentConfiguration,
                agent_config_pk,
                user,
                request=info.context,
            )
            if agent_config is None:
                raise AgentConfiguration.DoesNotExist
            if not agent_config.is_active:
                return payload_cls(
                    ok=False,
                    message="The selected agent configuration is not active",
                    obj=None,
                )
            corpus_action.agent_config = agent_config
            corpus_action.fieldset = None
            corpus_action.analyzer = None

        # Reject task_instructions on non-agent actions early,
        # before setting fields that model validation would later reject.
        will_be_agent = corpus_action.is_agent_action or agent_config_id is not None
        if not will_be_agent and task_instructions:
            return payload_cls(
                ok=False,
                message="task_instructions can only be set on agent-based actions",
                obj=None,
            )

        # Update agent-specific fields if this is (or is becoming) an agent action
        if will_be_agent or task_instructions is not None:
            if task_instructions is not None:
                corpus_action.task_instructions = task_instructions
            if pre_authorized_tools is not None:
                corpus_action.pre_authorized_tools = pre_authorized_tools

        corpus_action.save()

        return payload_cls(
            ok=True, message="Successfully updated corpus action", obj=corpus_action
        )

    except CorpusAction.DoesNotExist:
        return payload_cls(
            ok=False,
            message="Corpus action not found",
            obj=None,
        )

    except AgentConfiguration.DoesNotExist:
        return payload_cls(
            ok=False,
            message="Agent configuration not found",
            obj=None,
        )

    except Fieldset.DoesNotExist:
        return payload_cls(
            ok=False,
            message="Fieldset not found",
            obj=None,
        )

    except Analyzer.DoesNotExist:
        return payload_cls(
            ok=False,
            message="Analyzer not found",
            obj=None,
        )

    except Exception as e:
        return payload_cls(
            ok=False, message=f"Failed to update corpus action: {str(e)}", obj=None
        )


def m_update_corpus_action(
    info: strawberry.Info,
    agent_config_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="agentConfigId",
            description="ID of the agent configuration (clears other action types)",
        ),
    ] = strawberry.UNSET,
    analyzer_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="analyzerId",
            description="ID of the analyzer to run (clears other action types)",
        ),
    ] = strawberry.UNSET,
    disabled: Annotated[
        bool | None,
        strawberry.argument(
            name="disabled", description="Whether the action is disabled"
        ),
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="fieldsetId",
            description="ID of the fieldset to run (clears other action types)",
        ),
    ] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="ID of the corpus action to update"),
    ] = strawberry.UNSET,
    name: Annotated[
        str | None,
        strawberry.argument(name="name", description="Updated name of the action"),
    ] = strawberry.UNSET,
    pre_authorized_tools: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="preAuthorizedTools",
            description="Tools pre-authorized to run without approval",
        ),
    ] = strawberry.UNSET,
    run_on_all_corpuses: Annotated[
        bool | None,
        strawberry.argument(
            name="runOnAllCorpuses",
            description="Whether to run this action on all corpuses",
        ),
    ] = strawberry.UNSET,
    task_instructions: Annotated[
        str | None,
        strawberry.argument(
            name="taskInstructions", description="What the agent should do"
        ),
    ] = strawberry.UNSET,
    trigger: Annotated[
        str | None,
        strawberry.argument(
            name="trigger",
            description="Updated trigger (add_document, edit_document, new_thread, new_message)",
        ),
    ] = strawberry.UNSET,
) -> UpdateCorpusAction | None:
    kwargs = strip_unset(
        {
            "agent_config_id": agent_config_id,
            "analyzer_id": analyzer_id,
            "disabled": disabled,
            "fieldset_id": fieldset_id,
            "id": id,
            "name": name,
            "pre_authorized_tools": pre_authorized_tools,
            "run_on_all_corpuses": run_on_all_corpuses,
            "task_instructions": task_instructions,
            "trigger": trigger,
        }
    )
    return _mutate_UpdateCorpusAction(UpdateCorpusAction, None, info, **kwargs)


def m_delete_corpus_action(
    info: strawberry.Info,
    id: Annotated[
        str,
        strawberry.argument(name="id", description="ID of the corpus action to delete"),
    ] = strawberry.UNSET,
) -> DeleteCorpusAction | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteCorpusAction,
        model=CorpusAction,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_RunCorpusAction(
    payload_cls, root, info, corpus_action_id: str, document_id: str
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1389

    Port of RunCorpusAction.mutate
    """
    # @user_passes_test(lambda user: user.is_superuser) (graphql_jwt) —
    # inlined; see _mutate_StartCorpusFork for why decorators can't be
    # applied to mutate stubs directly.
    if not info.context.user.is_superuser:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.ADMIN_OPERATION)
    def mutate(root, info, corpus_action_id: str, document_id: str):
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
        from graphql_relay import from_global_id

        from opencontractserver.corpuses.models import CorpusActionExecution
        from opencontractserver.documents.models import DocumentPath
        from opencontractserver.tasks.agent_tasks import run_agent_corpus_action

        user = info.context.user

        # Decode Relay global IDs to database PKs
        _, action_pk = from_global_id(corpus_action_id)
        _, doc_pk = from_global_id(document_id)

        # Superuser-only: the @user_passes_test decorator above guarantees only
        # superusers reach this point, so raw .objects.get() is intentional and
        # bypasses visible_to_user() filtering by design. Defence-in-depth check
        # uses an explicit raise (not ``assert``) so it survives ``python -O``
        # which strips assertions.
        if not user.is_superuser:
            raise DjangoPermissionDenied(
                "RunCorpusAction requires superuser privileges."
            )

        # Validate action exists
        try:
            action = CorpusAction.objects.get(pk=action_pk)
        except CorpusAction.DoesNotExist:
            return payload_cls(ok=False, message="Corpus action not found.")

        # Must be an agent action
        if not action.is_agent_action:
            return payload_cls(
                ok=False,
                message="Only agent-based actions can be manually triggered.",
            )

        # Validate document exists and belongs to the action's corpus
        try:
            document = Document.objects.get(pk=doc_pk)
        except Document.DoesNotExist:
            return payload_cls(ok=False, message="Document not found.")

        if not DocumentPath.objects.filter(
            document=document, corpus=action.corpus
        ).exists():
            return payload_cls(
                ok=False,
                message="Document is not in this action's corpus.",
            )

        # Create execution record
        execution = CorpusActionExecution.objects.create(
            corpus_action=action,
            document=document,
            corpus=action.corpus,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.QUEUED,
            trigger=action.trigger,
            queued_at=timezone.now(),
            creator=user,
        )

        # Dispatch Celery task after transaction commits (ATOMIC_REQUESTS
        # wraps the entire request — dispatching inside the transaction
        # causes Celery to look up the execution before it's visible).
        transaction.on_commit(
            lambda: run_agent_corpus_action.delay(
                corpus_action_id=action.id,
                document_id=document.id,
                user_id=user.id,
                execution_id=execution.id,
                force=True,
            )
        )

        # Refresh so Django TextChoices enums are properly stored as
        # plain strings, which Graphene's enum serialization expects.
        execution.refresh_from_db()

        return payload_cls(
            ok=True,
            message="Action queued successfully.",
            obj=execution,
        )

    return mutate(
        root, info, corpus_action_id=corpus_action_id, document_id=document_id
    )


def m_run_corpus_action(
    info: strawberry.Info,
    corpus_action_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusActionId", description="ID of the CorpusAction to run"
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="documentId",
            description="ID of the Document to run the action against",
        ),
    ] = strawberry.UNSET,
) -> RunCorpusAction | None:
    kwargs = strip_unset(
        {"corpus_action_id": corpus_action_id, "document_id": document_id}
    )
    return _mutate_RunCorpusAction(RunCorpusAction, None, info, **kwargs)


def _mutate_StartCorpusActionBatchRun(payload_cls, root, info, corpus_action_id: str):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1505

    Port of StartCorpusActionBatchRun.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_HEAVY)
    def mutate(root, info, corpus_action_id: str):
        user = info.context.user

        try:
            _, action_pk = from_global_id(corpus_action_id)
            action_id = int(action_pk)
        except (ValueError, TypeError):
            # Malformed Relay global id — same generic error as the not-found
            # branch so it isn't a side channel for enumeration.
            return payload_cls(ok=False, message="Corpus action not found.")

        result = CorpusActionService.batch_run_on_corpus(
            user=user,
            action_id=action_id,
            request=info.context,
        )
        if not result.ok or result.value is None:
            return payload_cls(ok=False, message=result.error)

        summary = result.value
        if summary.queued_count == 0:
            message = (
                "No eligible documents — every active document in this corpus "
                f"has already been run through this action "
                f"({summary.skipped_already_run_count} skipped)."
            )
        else:
            message = (
                f"Queued {summary.queued_count} document(s) for processing; "
                f"skipped {summary.skipped_already_run_count} already-run."
            )

        return payload_cls(
            ok=True,
            message=message,
            queued_count=summary.queued_count,
            skipped_already_run_count=summary.skipped_already_run_count,
            total_active_documents=summary.total_active_documents,
            executions=summary.executions,
        )

    return mutate(root, info, corpus_action_id=corpus_action_id)


def m_start_corpus_action_batch_run(
    info: strawberry.Info,
    corpus_action_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusActionId",
            description="ID of the agent-based CorpusAction to batch-run",
        ),
    ] = strawberry.UNSET,
) -> StartCorpusActionBatchRun | None:
    kwargs = strip_unset({"corpus_action_id": corpus_action_id})
    return _mutate_StartCorpusActionBatchRun(
        StartCorpusActionBatchRun, None, info, **kwargs
    )


def _mutate_AddTemplateToCorpus(
    payload_cls, root, info, template_id: str, corpus_id: str
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1576

    Port of AddTemplateToCorpus.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    try:
        user = info.context.user
        no_permission_msg = "You don't have permission to add templates to this corpus"
        # Pre-guard both ``from_global_id`` decodes: a malformed base64
        # corpus or template id raises before the helper is reached —
        # return the same unified message rather than a leaked decode error.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
            template_pk = from_global_id(template_id)[1]
        except Exception:
            return payload_cls(ok=False, message=no_permission_msg, obj=None)

        # Get corpus with visibility filter to prevent IDOR. ``None``
        # collapses missing / hidden / no-CRUD into the same response.
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None or BaseService.require_permission(
            corpus, user, PermissionTypes.CRUD, request=info.context
        ):
            return payload_cls(
                ok=False,
                message=no_permission_msg,
                obj=None,
            )

        # Get the template (templates are global, no user filter needed)
        template = CorpusActionTemplate.objects.get(pk=template_pk, is_active=True)

        # Shared install recipe (dedupe fast-path, savepoint-wrapped
        # clone, IntegrityError race recovery, CRUD grant) — the same
        # method the one-click intelligence setup uses, so the two
        # install paths cannot drift.
        from opencontractserver.corpuses.services import CorpusActionService

        action, created = CorpusActionService.install_template(
            user, corpus, template, request=info.context
        )
        if not created:
            return payload_cls(
                ok=False,
                message="This template has already been added to the corpus",
                obj=None,
            )

        return payload_cls(
            ok=True,
            message="Template added to corpus successfully",
            obj=action,
        )

    except CorpusActionTemplate.DoesNotExist:
        return payload_cls(ok=False, message="Template not found or inactive", obj=None)

    except DatabaseError:
        logger.exception("Database error adding template to corpus")
        return payload_cls(
            ok=False,
            message="Failed to add template. Please try again.",
            obj=None,
        )


def m_add_template_to_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId", description="ID of the corpus to add the template to"
        ),
    ] = strawberry.UNSET,
    template_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="templateId", description="ID of the CorpusActionTemplate to clone"
        ),
    ] = strawberry.UNSET,
) -> AddTemplateToCorpus | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "template_id": template_id})
    return _mutate_AddTemplateToCorpus(AddTemplateToCorpus, None, info, **kwargs)


def _mutate_SetupCorpusIntelligence(payload_cls, root, info, corpus_id: str):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1667

    Port of SetupCorpusIntelligence.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_HEAVY)
    def mutate(root, info, corpus_id: str):
        from opencontractserver.corpuses.services import (
            CorpusIntelligenceSetupService,
        )

        failure_msg = "Corpus not found or you don't have permission."
        try:
            corpus_pk = int(from_global_id(corpus_id)[1])
        except Exception:
            return payload_cls(ok=False, message=failure_msg, summary=None)

        result = CorpusIntelligenceSetupService.setup(
            info.context.user, corpus_pk, request=info.context
        )
        if not result.ok:
            return payload_cls(ok=False, message=result.error, summary=None)
        return payload_cls(
            ok=True,
            message="Collection intelligence setup started.",
            summary=result.value,
        )

    return mutate(root, info, corpus_id=corpus_id)


def m_setup_corpus_intelligence(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="corpusId", description="ID of the corpus to set up."),
    ] = strawberry.UNSET,
) -> SetupCorpusIntelligence | None:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_SetupCorpusIntelligence(
        SetupCorpusIntelligence, None, info, **kwargs
    )


def _mutate_ToggleCorpusMemory(payload_cls, root, info, corpus_id, enabled):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1721

    Port of ToggleCorpusMemory.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(root, info, corpus_id, enabled):
        user = info.context.user
        # IDOR protection: same response whether the pk is malformed,
        # corpus doesn't exist, is hidden from the caller, or the caller has
        # READ but no CRUD on it.
        not_found_msg = "Corpus not found or you don't have permission to modify it."
        # ``from_global_id`` can raise a bare ``Exception`` (via
        # ``binascii.Error``) on malformed base64 input — narrower
        # ``(ValueError, IndexError)`` would let those slip through as
        # raw GraphQL ``errors``.  Mirrors the broader catch used at
        # the other migrated ``from_global_id`` sites in this file.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return payload_cls(ok=False, message=not_found_msg, corpus=None)

        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None or BaseService.require_permission(
            corpus, user, PermissionTypes.CRUD, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg, corpus=None)

        corpus.memory_enabled = enabled
        corpus.save(update_fields=["memory_enabled", "modified"])

        status = "enabled" if enabled else "disabled"
        return payload_cls(
            ok=True,
            message=f"Agent memory {status} for corpus '{corpus.title}'",
            corpus=corpus,
        )

    return mutate(root, info, corpus_id=corpus_id, enabled=enabled)


def m_toggle_corpus_memory(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="corpusId",
            description="The global ID of the corpus to toggle memory for",
        ),
    ] = strawberry.UNSET,
    enabled: Annotated[
        bool,
        strawberry.argument(
            name="enabled",
            description="Whether to enable (true) or disable (false) memory",
        ),
    ] = strawberry.UNSET,
) -> ToggleCorpusMemory | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "enabled": enabled})
    return _mutate_ToggleCorpusMemory(ToggleCorpusMemory, None, info, **kwargs)


def _mutate_CreateArtifact(
    payload_cls,
    root,
    info,
    corpus_id,
    template,
    title="",
    subtitle="",
    byline="",
    config=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1778

    Port of CreateArtifact.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(
        root, info, corpus_id, template, title="", subtitle="", byline="", config=None
    ):
        import json

        from config.graphql.corpus_queries import _artifact_to_type
        from opencontractserver.constants.artifacts import MAX_ARTIFACT_CONFIG_BYTES
        from opencontractserver.corpuses.services.artifact_service import (
            ArtifactService,
        )

        fail = "Couldn't create artifact (unknown template or no access)."
        try:
            corpus_pk = int(from_global_id(corpus_id)[1])
        except Exception:
            return payload_cls(ok=False, message="Invalid corpus id.", artifact=None)
        if config and len(json.dumps(config)) > MAX_ARTIFACT_CONFIG_BYTES:
            return payload_cls(
                ok=False, message="Config payload too large.", artifact=None
            )
        artifact = ArtifactService.create(
            info.context.user,
            corpus_pk,
            template,
            title=title or "",
            subtitle=subtitle or "",
            byline=byline or "",
            config=config or {},
            request=info.context,
        )
        if artifact is None:
            return payload_cls(ok=False, message=fail, artifact=None)
        return payload_cls(
            ok=True, message="Artifact created.", artifact=_artifact_to_type(artifact)
        )

    return mutate(
        root,
        info,
        corpus_id=corpus_id,
        template=template,
        title=title,
        subtitle=subtitle,
        byline=byline,
        config=config,
    )


def m_create_artifact(
    info: strawberry.Info,
    byline: Annotated[
        str | None, strawberry.argument(name="byline")
    ] = strawberry.UNSET,
    config: Annotated[
        GenericScalar | None, strawberry.argument(name="config")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    subtitle: Annotated[
        str | None, strawberry.argument(name="subtitle")
    ] = strawberry.UNSET,
    template: Annotated[str, strawberry.argument(name="template")] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
) -> CreateArtifact | None:
    kwargs = strip_unset(
        {
            "byline": byline,
            "config": config,
            "corpus_id": corpus_id,
            "subtitle": subtitle,
            "template": template,
            "title": title,
        }
    )
    return _mutate_CreateArtifact(CreateArtifact, None, info, **kwargs)


def _mutate_UpdateArtifact(
    payload_cls, root, info, slug, title=None, subtitle=None, byline=None, config=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1838

    Port of UpdateArtifact.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, slug, title=None, subtitle=None, byline=None, config=None):
        import json

        from config.graphql.corpus_queries import _artifact_to_type
        from opencontractserver.constants.artifacts import MAX_ARTIFACT_CONFIG_BYTES
        from opencontractserver.corpuses.services.artifact_service import (
            ArtifactService,
        )

        if config and len(json.dumps(config)) > MAX_ARTIFACT_CONFIG_BYTES:
            return payload_cls(
                ok=False, message="Config payload too large.", artifact=None
            )
        artifact = ArtifactService.update_captions(
            info.context.user,
            slug,
            title=title,
            subtitle=subtitle,
            byline=byline,
            config=config,
            request=info.context,
        )
        if artifact is None:
            return payload_cls(
                ok=False,
                message="Artifact not found or you don't have permission.",
                artifact=None,
            )
        return payload_cls(
            ok=True, message="Artifact updated.", artifact=_artifact_to_type(artifact)
        )

    return mutate(
        root,
        info,
        slug=slug,
        title=title,
        subtitle=subtitle,
        byline=byline,
        config=config,
    )


def m_update_artifact(
    info: strawberry.Info,
    byline: Annotated[
        str | None, strawberry.argument(name="byline")
    ] = strawberry.UNSET,
    config: Annotated[
        GenericScalar | None, strawberry.argument(name="config")
    ] = strawberry.UNSET,
    slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET,
    subtitle: Annotated[
        str | None, strawberry.argument(name="subtitle")
    ] = strawberry.UNSET,
    title: Annotated[str | None, strawberry.argument(name="title")] = strawberry.UNSET,
) -> UpdateArtifact | None:
    kwargs = strip_unset(
        {
            "byline": byline,
            "config": config,
            "slug": slug,
            "subtitle": subtitle,
            "title": title,
        }
    )
    return _mutate_UpdateArtifact(UpdateArtifact, None, info, **kwargs)


def _mutate_SetArtifactImage(payload_cls, root, info, slug, base64_png):
    """PORT: /home/user/oc-graphene-ref/config/graphql/corpus_mutations.py:1894

    Port of SetArtifactImage.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_StartCorpusFork.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # @graphql_ratelimit on an inner ``mutate`` — see _mutate_SetCorpusVisibility.
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, slug, base64_png):
        import base64

        from opencontractserver.constants.artifacts import (
            MAX_ARTIFACT_IMAGE_BASE64_BYTES,
        )
        from opencontractserver.corpuses.services.artifact_service import (
            ArtifactService,
        )

        # Reject oversized payloads before the decode allocates them in memory.
        if len(base64_png) > MAX_ARTIFACT_IMAGE_BASE64_BYTES:
            return payload_cls(ok=False, message="Image too large.", image_url=None)
        raw = base64_png.split(",", 1)[-1] if "," in base64_png else base64_png
        try:
            data = base64.b64decode(raw)
        except Exception:
            return payload_cls(ok=False, message="Bad image data.", image_url=None)
        # PNG-format validation lives in ArtifactService.set_image (single home
        # for image handling, per its docstring) so any future caller — not
        # just this mutation — is protected.
        try:
            artifact = ArtifactService.set_image(
                info.context.user, slug, data, request=info.context
            )
        except ValueError as exc:
            return payload_cls(ok=False, message=str(exc), image_url=None)
        if artifact is None:
            return payload_cls(
                ok=False, message="Artifact not found or not yours.", image_url=None
            )
        return payload_cls(
            ok=True, message="Image saved.", image_url=artifact.image.url
        )

    return mutate(root, info, slug=slug, base64_png=base64_png)


def m_set_artifact_image(
    info: strawberry.Info,
    base64_png: Annotated[
        str,
        strawberry.argument(
            name="base64Png", description="data-URL or raw base64 PNG bytes."
        ),
    ] = strawberry.UNSET,
    slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET,
) -> SetArtifactImage | None:
    kwargs = strip_unset({"base64_png": base64_png, "slug": slug})
    return _mutate_SetArtifactImage(SetArtifactImage, None, info, **kwargs)


MUTATION_FIELDS = {
    "fork_corpus": strawberry.field(resolver=m_fork_corpus, name="forkCorpus"),
    "re_embed_corpus": strawberry.field(
        resolver=m_re_embed_corpus,
        name="reEmbedCorpus",
        description="Re-embed all annotations in a corpus with a different embedder (Issue #437).\n\nThis is the controlled migration path for changing a corpus's embedder\nafter documents have been added. It:\n1. Validates the new embedder exists in the registry\n2. Locks the corpus (backend_lock=True)\n3. Queues a background task that updates preferred_embedder and\n   generates new embeddings for all annotations\n4. The corpus unlocks automatically when re-embedding completes\n\nOnly the corpus creator can trigger re-embedding.",
    ),
    "set_corpus_visibility": strawberry.field(
        resolver=m_set_corpus_visibility,
        name="setCorpusVisibility",
        description="Set corpus visibility (public/private).\n\nRequires one of:\n- User is the corpus creator (owner), OR\n- User has PERMISSION permission on the corpus, OR\n- User is superuser\n\nSecurity notes:\n- Permission check prevents users from escalating access\n- Uses existing make_corpus_public_task for cascading public visibility\n- Making private only affects the corpus flag (child objects remain public)",
    ),
    "create_corpus": strawberry.field(resolver=m_create_corpus, name="createCorpus"),
    "update_corpus": strawberry.field(resolver=m_update_corpus, name="updateCorpus"),
    "update_corpus_description": strawberry.field(
        resolver=m_update_corpus_description,
        name="updateCorpusDescription",
        description="Mutation to update a corpus's markdown description, creating a new version in the process.\nOnly the corpus creator can update the description.",
    ),
    "delete_corpus": strawberry.field(resolver=m_delete_corpus, name="deleteCorpus"),
    "link_documents_to_corpus": strawberry.field(
        resolver=m_link_documents_to_corpus,
        name="linkDocumentsToCorpus",
        description="Add existing documents to a corpus.\n\nDelegates to CorpusDocumentService.add_documents_to_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Document validation (user owns or public)\n- Dual-system update (DocumentPath + corpus.add_document)",
    ),
    "remove_documents_from_corpus": strawberry.field(
        resolver=m_remove_documents_from_corpus,
        name="removeDocumentsFromCorpus",
        description="Remove documents from a corpus (soft-delete).\n\nDelegates to CorpusDocumentService.remove_documents_from_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Soft-delete via DocumentPath (creates is_deleted=True record)\n- Audit trail",
    ),
    "create_corpus_action": strawberry.field(
        resolver=m_create_corpus_action,
        name="createCorpusAction",
        description="Create a new CorpusAction that will be triggered when events occur in a corpus.\n\nAction types:\n- **Fieldset**: Run data extraction (fieldset_id)\n- **Analyzer**: Run classification/annotation (analyzer_id)\n- **Agent**: Execute an AI agent task. Provide task_instructions describing what the\n  agent should do. Optionally link an agent_config_id for custom persona/tool defaults,\n  or use create_agent_inline=True for thread/message moderation.\n- **Lightweight agent**: Just provide task_instructions (no agent_config needed).\n  The system auto-selects tools based on the trigger type.\n\nRequires UPDATE permission on the corpus.",
    ),
    "update_corpus_action": strawberry.field(
        resolver=m_update_corpus_action,
        name="updateCorpusAction",
        description="Update an existing CorpusAction.\nAllows updating name, trigger, action type (fieldset/analyzer/agent), disabled state,\nand agent-specific settings.\nRequires the user to be the creator of the action.",
    ),
    "delete_corpus_action": strawberry.field(
        resolver=m_delete_corpus_action,
        name="deleteCorpusAction",
        description="Mutation to delete a CorpusAction.\nRequires the user to be the creator of the action or have appropriate permissions.",
    ),
    "run_corpus_action": strawberry.field(
        resolver=m_run_corpus_action,
        name="runCorpusAction",
        description="Manually trigger a specific agent-based corpus action on a document.\n\nSuperuser-only. Creates a CorpusActionExecution record and dispatches\nthe run_agent_corpus_action Celery task.",
    ),
    "start_corpus_action_batch_run": strawberry.field(
        resolver=m_start_corpus_action_batch_run,
        name="startCorpusActionBatchRun",
        description="Run an agent-based corpus action against every eligible document in the corpus.",
    ),
    "add_template_to_corpus": strawberry.field(
        resolver=m_add_template_to_corpus,
        name="addTemplateToCorpus",
        description="Add an action template to a corpus by cloning it into a CorpusAction.\n\nThis is the core of the Action Library feature: users browse available\ntemplates and opt-in per corpus. Once cloned, the action is a regular\nCorpusAction that can be edited/toggled/deleted like any other.\n\nPrevents duplicates: the same template cannot be added twice to the same\ncorpus (checked via source_template FK).\n\nRequires the user to be the corpus creator or have CRUD permission.",
    ),
    "setup_corpus_intelligence": strawberry.field(
        resolver=m_setup_corpus_intelligence,
        name="setupCorpusIntelligence",
        description="One-click collection-intelligence setup.\n\nComposes the default enrichment bundle in a single idempotent call:\ninstalls the reference-enrichment analyzer as an ``add_document`` action\nand starts the first weave (deterministic), then clones the description +\nsummary action templates and batch-runs each over every document already\nin the corpus (LLM). Safe to repeat — every step skips work that already\nexists. Requires CRUD permission on the corpus — the tier\nAddTemplateToCorpus and CreateCorpusAction gate the identical writes at.",
    ),
    "toggle_corpus_memory": strawberry.field(
        resolver=m_toggle_corpus_memory,
        name="toggleCorpusMemory",
        description="Toggle the agent memory system on/off for a corpus.\n\nWhen enabled, agents accumulate reusable insights from conversations\ninto a memory document. The memory document is a first-class Document\nin the corpus, visible and editable by users.\n\nIMPORTANT: When memory is enabled, conversation patterns (NOT specific\ncontent) may be distilled into the memory document. Users should be\naware of this when discussing sensitive topics.\n\nRequires CRUD permission on the corpus.",
    ),
    "create_artifact": strawberry.field(
        resolver=m_create_artifact,
        name="createArtifact",
        description="Create a shareable poster (Artifact) of a corpus from a template.\n\nREAD-gated on the corpus (you can make a poster of any collection you can\nsee): its ``/a/<slug>`` link is shareable to anyone who can read the\nsource corpus (corpus-as-gate ONLY — there is no per-artifact visibility\noverride), and its data still only renders to viewers who can read the\ncorpus. ``template`` is validated against the service's registry.",
    ),
    "update_artifact": strawberry.field(
        resolver=m_update_artifact,
        name="updateArtifact",
        description="Edit an artifact's configurable captions — creator only.",
    ),
    "set_artifact_image": strawberry.field(
        resolver=m_set_artifact_image,
        name="setArtifactImage",
        description="Persist the rendered poster PNG so ``/a/<slug>`` has a stable og:image.\n\nThe poster is an SVG rendered client-side; the editor rasterises it and\nuploads the bytes here on save. (A production deploy can swap in a headless\nserver render behind the same field without changing the contract.)\nCreator-only.",
    ),
}
