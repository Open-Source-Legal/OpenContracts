"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums

from opencontractserver.corpuses.models import CorpusAction


@strawberry.type(name="StartCorpusFork")
class StartCorpusFork:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    new_corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="newCorpus", default=None)


register_type("StartCorpusFork", StartCorpusFork, model=None)


@strawberry.type(name="ReEmbedCorpus", description="Re-embed all annotations in a corpus with a different embedder (Issue #437).\n\nThis is the controlled migration path for changing a corpus's embedder\nafter documents have been added. It:\n1. Validates the new embedder exists in the registry\n2. Locks the corpus (backend_lock=True)\n3. Queues a background task that updates preferred_embedder and\n   generates new embeddings for all annotations\n4. The corpus unlocks automatically when re-embedding completes\n\nOnly the corpus creator can trigger re-embedding.")
class ReEmbedCorpus:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("ReEmbedCorpus", ReEmbedCorpus, model=None)


@strawberry.type(name="SetCorpusVisibility", description='Set corpus visibility (public/private).\n\nRequires one of:\n- User is the corpus creator (owner), OR\n- User has PERMISSION permission on the corpus, OR\n- User is superuser\n\nSecurity notes:\n- Permission check prevents users from escalating access\n- Uses existing make_corpus_public_task for cascading public visibility\n- Making private only affects the corpus flag (child objects remain public)')
class SetCorpusVisibility:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("SetCorpusVisibility", SetCorpusVisibility, model=None)


@strawberry.type(name="CreateCorpusMutation")
class CreateCorpusMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("CreateCorpusMutation", CreateCorpusMutation, model=None)


@strawberry.type(name="UpdateCorpusMutation")
class UpdateCorpusMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="objId")
    def obj_id(self, info: strawberry.Info) -> Optional[strawberry.ID]:
        return coerce_str(getattr(self, "obj_id", None))


register_type("UpdateCorpusMutation", UpdateCorpusMutation, model=None)


@strawberry.type(name="UpdateCorpusDescription", description="Mutation to update a corpus's markdown description, creating a new version in the process.\nOnly the corpus creator can update the description.")
class UpdateCorpusDescription:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="obj", default=None)
    version: Optional[int] = strawberry.field(name="version", description='The new version number after update', default=None)


register_type("UpdateCorpusDescription", UpdateCorpusDescription, model=None)


@strawberry.type(name="DeleteCorpusMutation")
class DeleteCorpusMutation:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteCorpusMutation", DeleteCorpusMutation, model=None)


@strawberry.type(name="AddDocumentsToCorpus", description='Add existing documents to a corpus.\n\nDelegates to CorpusDocumentService.add_documents_to_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Document validation (user owns or public)\n- Dual-system update (DocumentPath + corpus.add_document)')
class AddDocumentsToCorpus:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("AddDocumentsToCorpus", AddDocumentsToCorpus, model=None)


@strawberry.type(name="RemoveDocumentsFromCorpus", description='Remove documents from a corpus (soft-delete).\n\nDelegates to CorpusDocumentService.remove_documents_from_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Soft-delete via DocumentPath (creates is_deleted=True record)\n- Audit trail')
class RemoveDocumentsFromCorpus:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("RemoveDocumentsFromCorpus", RemoveDocumentsFromCorpus, model=None)


@strawberry.type(name="CreateCorpusAction", description='Create a new CorpusAction that will be triggered when events occur in a corpus.\n\nAction types:\n- **Fieldset**: Run data extraction (fieldset_id)\n- **Analyzer**: Run classification/annotation (analyzer_id)\n- **Agent**: Execute an AI agent task. Provide task_instructions describing what the\n  agent should do. Optionally link an agent_config_id for custom persona/tool defaults,\n  or use create_agent_inline=True for thread/message moderation.\n- **Lightweight agent**: Just provide task_instructions (no agent_config needed).\n  The system auto-selects tools based on the trigger type.\n\nRequires UPDATE permission on the corpus.')
class CreateCorpusAction:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="obj", default=None)


register_type("CreateCorpusAction", CreateCorpusAction, model=None)


@strawberry.type(name="UpdateCorpusAction", description='Update an existing CorpusAction.\nAllows updating name, trigger, action type (fieldset/analyzer/agent), disabled state,\nand agent-specific settings.\nRequires the user to be the creator of the action.')
class UpdateCorpusAction:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="obj", default=None)


register_type("UpdateCorpusAction", UpdateCorpusAction, model=None)


@strawberry.type(name="DeleteCorpusAction", description='Mutation to delete a CorpusAction.\nRequires the user to be the creator of the action or have appropriate permissions.')
class DeleteCorpusAction:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))


register_type("DeleteCorpusAction", DeleteCorpusAction, model=None)


@strawberry.type(name="RunCorpusAction", description='Manually trigger a specific agent-based corpus action on a document.\n\nSuperuser-only. Creates a CorpusActionExecution record and dispatches\nthe run_agent_corpus_action Celery task.')
class RunCorpusAction:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusActionExecutionType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="obj", default=None)


register_type("RunCorpusAction", RunCorpusAction, model=None)


@strawberry.type(name="StartCorpusActionBatchRun", description='Run an agent-based corpus action against every eligible document in the corpus.')
class StartCorpusActionBatchRun:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    queued_count: Optional[int] = strawberry.field(name="queuedCount", description='Number of new CorpusActionExecution rows created.', default=None)
    skipped_already_run_count: Optional[int] = strawberry.field(name="skippedAlreadyRunCount", description='Active documents skipped because they already have a queued, running, or completed execution for this action.', default=None)
    total_active_documents: Optional[int] = strawberry.field(name="totalActiveDocuments", description='Total active documents in the corpus at evaluation time.', default=None)
    @strawberry.field(name="executions", description='The freshly created execution rows (status=QUEUED).')
    def executions(self, info: strawberry.Info) -> Optional[list[Optional[Annotated["CorpusActionExecutionType", strawberry.lazy("config.graphql.agent_types")]]]]:
        return resolve_django_list(self, info, getattr(self, "executions"), "CorpusActionExecutionType")


register_type("StartCorpusActionBatchRun", StartCorpusActionBatchRun, model=None)


@strawberry.type(name="AddTemplateToCorpus", description='Add an action template to a corpus by cloning it into a CorpusAction.\n\nThis is the core of the Action Library feature: users browse available\ntemplates and opt-in per corpus. Once cloned, the action is a regular\nCorpusAction that can be edited/toggled/deleted like any other.\n\nPrevents duplicates: the same template cannot be added twice to the same\ncorpus (checked via source_template FK).\n\nRequires the user to be the corpus creator or have CRUD permission.')
class AddTemplateToCorpus:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusActionType", strawberry.lazy("config.graphql.agent_types")]] = strawberry.field(name="obj", default=None)


register_type("AddTemplateToCorpus", AddTemplateToCorpus, model=None)


@strawberry.type(name="SetupCorpusIntelligence", description='One-click collection-intelligence setup.\n\nComposes the default enrichment bundle in a single idempotent call:\ninstalls the reference-enrichment analyzer as an ``add_document`` action\nand starts the first weave (deterministic), then clones the description +\nsummary action templates and batch-runs each over every document already\nin the corpus (LLM). Safe to repeat — every step skips work that already\nexists. Requires CRUD permission on the corpus — the tier\nAddTemplateToCorpus and CreateCorpusAction gate the identical writes at.')
class SetupCorpusIntelligence:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    summary: Optional[Annotated["CorpusIntelligenceSetupSummaryType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="summary", default=None)


register_type("SetupCorpusIntelligence", SetupCorpusIntelligence, model=None)


@strawberry.type(name="ToggleCorpusMemory", description='Toggle the agent memory system on/off for a corpus.\n\nWhen enabled, agents accumulate reusable insights from conversations\ninto a memory document. The memory document is a first-class Document\nin the corpus, visible and editable by users.\n\nIMPORTANT: When memory is enabled, conversation patterns (NOT specific\ncontent) may be distilled into the memory document. Users should be\naware of this when discussing sensitive topics.\n\nRequires CRUD permission on the corpus.')
class ToggleCorpusMemory:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    corpus: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="corpus", default=None)


register_type("ToggleCorpusMemory", ToggleCorpusMemory, model=None)


@strawberry.type(name="CreateArtifact", description="Create a shareable poster (Artifact) of a corpus from a template.\n\nREAD-gated on the corpus (you can make a poster of any collection you can\nsee): its ``/a/<slug>`` link is shareable to anyone who can read the\nsource corpus (corpus-as-gate ONLY — there is no per-artifact visibility\noverride), and its data still only renders to viewers who can read the\ncorpus. ``template`` is validated against the service's registry.")
class CreateArtifact:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    artifact: Optional[Annotated["ArtifactType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="artifact", default=None)


register_type("CreateArtifact", CreateArtifact, model=None)


@strawberry.type(name="UpdateArtifact", description="Edit an artifact's configurable captions — creator only.")
class UpdateArtifact:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    artifact: Optional[Annotated["ArtifactType", strawberry.lazy("config.graphql.corpus_types")]] = strawberry.field(name="artifact", default=None)


register_type("UpdateArtifact", UpdateArtifact, model=None)


@strawberry.type(name="SetArtifactImage", description='Persist the rendered poster PNG so ``/a/<slug>`` has a stable og:image.\n\nThe poster is an SVG rendered client-side; the editor rasterises it and\nuploads the bytes here on save. (A production deploy can swap in a headless\nserver render behind the same field without changing the contract.)\nCreator-only.')
class SetArtifactImage:
    ok: Optional[bool] = strawberry.field(name="ok", default=None)
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    @strawberry.field(name="imageUrl")
    def image_url(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "image_url", None))


register_type("SetArtifactImage", SetArtifactImage, model=None)


def _mutate_StartCorpusFork(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:558

    Port of StartCorpusFork.mutate
    """
    raise NotImplementedError("_mutate_StartCorpusFork not yet ported — see manifest")


def m_fork_corpus(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Graphene id of the corpus you want to package for export')] = strawberry.UNSET, preferred_embedder: Annotated[Optional[str], strawberry.argument(name="preferredEmbedder", description="Override the embedder for the forked corpus. If provided and different from the source corpus, the fork will generate new embeddings using this embedder. If not provided, inherits the source corpus's preferred_embedder.")] = strawberry.UNSET) -> Optional["StartCorpusFork"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "preferred_embedder": preferred_embedder})
    return _mutate_StartCorpusFork(StartCorpusFork, None, info, **kwargs)


def _mutate_ReEmbedCorpus(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:699

    Port of ReEmbedCorpus.mutate
    """
    raise NotImplementedError("_mutate_ReEmbedCorpus not yet ported — see manifest")


def m_re_embed_corpus(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Global ID of the corpus to re-embed')] = strawberry.UNSET, new_embedder: Annotated[str, strawberry.argument(name="newEmbedder", description="Fully qualified Python path to the new embedder class (e.g., 'opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder')")] = strawberry.UNSET) -> Optional["ReEmbedCorpus"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "new_embedder": new_embedder})
    return _mutate_ReEmbedCorpus(ReEmbedCorpus, None, info, **kwargs)


def _mutate_SetCorpusVisibility(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:81

    Port of SetCorpusVisibility.mutate
    """
    raise NotImplementedError("_mutate_SetCorpusVisibility not yet ported — see manifest")


def m_set_corpus_visibility(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus to change visibility for')] = strawberry.UNSET, is_public: Annotated[bool, strawberry.argument(name="isPublic", description='True to make public, False to make private')] = strawberry.UNSET) -> Optional["SetCorpusVisibility"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "is_public": is_public})
    return _mutate_SetCorpusVisibility(SetCorpusVisibility, None, info, **kwargs)


def _mutate_CreateCorpusMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.corpus_mutations.CreateCorpusMutation.mutate

    Port of CreateCorpusMutation.mutate
    """
    raise NotImplementedError("_mutate_CreateCorpusMutation not yet ported — see manifest")


def m_create_corpus(info: strawberry.Info, categories: Annotated[Optional[list[Optional[strawberry.ID]]], strawberry.argument(name="categories", description='Category IDs to assign')] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, label_set: Annotated[Optional[str], strawberry.argument(name="labelSet")] = strawberry.UNSET, license: Annotated[Optional[str], strawberry.argument(name="license", description='SPDX license identifier (e.g. CC-BY-4.0)')] = strawberry.UNSET, license_link: Annotated[Optional[str], strawberry.argument(name="licenseLink", description='URL to full license text (required for CUSTOM license)')] = strawberry.UNSET, preferred_embedder: Annotated[Optional[str], strawberry.argument(name="preferredEmbedder")] = strawberry.UNSET, preferred_llm: Annotated[Optional[str], strawberry.argument(name="preferredLlm", description="Optional pydantic-ai model spec for this corpus's agents (e.g. 'anthropic:claude-opus-4-6'). When unset, agents fall back to settings.DEFAULT_LLM / settings.OPENAI_MODEL.")] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["CreateCorpusMutation"]:
    kwargs = strip_unset({"categories": categories, "description": description, "icon": icon, "label_set": label_set, "license": license, "license_link": license_link, "preferred_embedder": preferred_embedder, "preferred_llm": preferred_llm, "slug": slug, "title": title})
    return _mutate_CreateCorpusMutation(CreateCorpusMutation, None, info, **kwargs)


def _mutate_UpdateCorpusMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.corpus_mutations.UpdateCorpusMutation.mutate

    Port of UpdateCorpusMutation.mutate
    """
    raise NotImplementedError("_mutate_UpdateCorpusMutation not yet ported — see manifest")


def m_update_corpus(info: strawberry.Info, categories: Annotated[Optional[list[Optional[strawberry.ID]]], strawberry.argument(name="categories", description='Category IDs to assign (replaces existing)')] = strawberry.UNSET, corpus_agent_instructions: Annotated[Optional[str], strawberry.argument(name="corpusAgentInstructions")] = strawberry.UNSET, description: Annotated[Optional[str], strawberry.argument(name="description")] = strawberry.UNSET, document_agent_instructions: Annotated[Optional[str], strawberry.argument(name="documentAgentInstructions")] = strawberry.UNSET, icon: Annotated[Optional[str], strawberry.argument(name="icon")] = strawberry.UNSET, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET, label_set: Annotated[Optional[str], strawberry.argument(name="labelSet")] = strawberry.UNSET, license: Annotated[Optional[str], strawberry.argument(name="license", description='SPDX license identifier (e.g. CC-BY-4.0)')] = strawberry.UNSET, license_link: Annotated[Optional[str], strawberry.argument(name="licenseLink", description='URL to full license text (required for CUSTOM license)')] = strawberry.UNSET, preferred_embedder: Annotated[Optional[str], strawberry.argument(name="preferredEmbedder")] = strawberry.UNSET, preferred_llm: Annotated[Optional[str], strawberry.argument(name="preferredLlm", description="Optional pydantic-ai model spec for this corpus's agents (e.g. 'anthropic:claude-opus-4-6'). Pass empty string to clear and fall back to settings.DEFAULT_LLM / settings.OPENAI_MODEL.")] = strawberry.UNSET, slug: Annotated[Optional[str], strawberry.argument(name="slug")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["UpdateCorpusMutation"]:
    kwargs = strip_unset({"categories": categories, "corpus_agent_instructions": corpus_agent_instructions, "description": description, "document_agent_instructions": document_agent_instructions, "icon": icon, "id": id, "label_set": label_set, "license": license, "license_link": license_link, "preferred_embedder": preferred_embedder, "preferred_llm": preferred_llm, "slug": slug, "title": title})
    return _mutate_UpdateCorpusMutation(UpdateCorpusMutation, None, info, **kwargs)


def _mutate_UpdateCorpusDescription(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:278

    Port of UpdateCorpusDescription.mutate
    """
    raise NotImplementedError("_mutate_UpdateCorpusDescription not yet ported — see manifest")


def m_update_corpus_description(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus to update')] = strawberry.UNSET, new_content: Annotated[str, strawberry.argument(name="newContent", description='New markdown content for the corpus description')] = strawberry.UNSET) -> Optional["UpdateCorpusDescription"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "new_content": new_content})
    return _mutate_UpdateCorpusDescription(UpdateCorpusDescription, None, info, **kwargs)


def _mutate_DeleteCorpusMutation(payload_cls, root, info, **kwargs):
    """PORT: config.graphql.corpus_mutations.DeleteCorpusMutation.mutate

    Port of DeleteCorpusMutation.mutate
    """
    raise NotImplementedError("_mutate_DeleteCorpusMutation not yet ported — see manifest")


def m_delete_corpus(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET) -> Optional["DeleteCorpusMutation"]:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteCorpusMutation(DeleteCorpusMutation, None, info, **kwargs)


def _mutate_AddDocumentsToCorpus(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:411

    Port of AddDocumentsToCorpus.mutate
    """
    raise NotImplementedError("_mutate_AddDocumentsToCorpus not yet ported — see manifest")


def m_link_documents_to_corpus(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of corpus to add documents to.')] = strawberry.UNSET, document_ids: Annotated[list[Optional[str]], strawberry.argument(name="documentIds", description='List of ids of the docs to add to corpus.')] = strawberry.UNSET) -> Optional["AddDocumentsToCorpus"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_ids": document_ids})
    return _mutate_AddDocumentsToCorpus(AddDocumentsToCorpus, None, info, **kwargs)


def _mutate_RemoveDocumentsFromCorpus(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:485

    Port of RemoveDocumentsFromCorpus.mutate
    """
    raise NotImplementedError("_mutate_RemoveDocumentsFromCorpus not yet ported — see manifest")


def m_remove_documents_from_corpus(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='ID of corpus to remove documents from.')] = strawberry.UNSET, document_ids_to_remove: Annotated[list[Optional[str]], strawberry.argument(name="documentIdsToRemove", description='List of ids of the docs to remove from corpus.')] = strawberry.UNSET) -> Optional["RemoveDocumentsFromCorpus"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "document_ids_to_remove": document_ids_to_remove})
    return _mutate_RemoveDocumentsFromCorpus(RemoveDocumentsFromCorpus, None, info, **kwargs)


def _mutate_CreateCorpusAction(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:853

    Port of CreateCorpusAction.mutate
    """
    raise NotImplementedError("_mutate_CreateCorpusAction not yet ported — see manifest")


def m_create_corpus_action(info: strawberry.Info, agent_config_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfigId", description='Optional agent configuration for persona/tool defaults. Not required — task_instructions alone is sufficient for agent actions.')] = strawberry.UNSET, analyzer_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzerId", description='ID of the analyzer to run')] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus this action is for')] = strawberry.UNSET, create_agent_inline: Annotated[Optional[bool], strawberry.argument(name="createAgentInline", description='Create a new agent inline instead of using existing agent_config_id')] = strawberry.UNSET, disabled: Annotated[Optional[bool], strawberry.argument(name="disabled", description='Whether the action is disabled')] = strawberry.UNSET, fieldset_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldsetId", description='ID of the fieldset to run')] = strawberry.UNSET, inline_agent_description: Annotated[Optional[str], strawberry.argument(name="inlineAgentDescription", description='Description for the new inline agent')] = strawberry.UNSET, inline_agent_instructions: Annotated[Optional[str], strawberry.argument(name="inlineAgentInstructions", description='System instructions for the new inline agent (required if create_agent_inline=True)')] = strawberry.UNSET, inline_agent_name: Annotated[Optional[str], strawberry.argument(name="inlineAgentName", description='Name for the new inline agent (required if create_agent_inline=True)')] = strawberry.UNSET, inline_agent_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="inlineAgentTools", description='Tools available to the new inline agent')] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name", description='Name of the action')] = strawberry.UNSET, pre_authorized_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="preAuthorizedTools", description='Tools pre-authorized to run without approval. If empty, uses agent_config tools or trigger-appropriate defaults.')] = strawberry.UNSET, run_on_all_corpuses: Annotated[Optional[bool], strawberry.argument(name="runOnAllCorpuses", description='Whether to run this action on all corpuses')] = strawberry.UNSET, task_instructions: Annotated[Optional[str], strawberry.argument(name="taskInstructions", description="What the agent should do. This is the single required field for agent actions (e.g., 'Read this document and update its description with a one-paragraph summary').")] = strawberry.UNSET, trigger: Annotated[str, strawberry.argument(name="trigger", description='When to trigger: add_document, edit_document, new_thread, new_message')] = strawberry.UNSET) -> Optional["CreateCorpusAction"]:
    kwargs = strip_unset({"agent_config_id": agent_config_id, "analyzer_id": analyzer_id, "corpus_id": corpus_id, "create_agent_inline": create_agent_inline, "disabled": disabled, "fieldset_id": fieldset_id, "inline_agent_description": inline_agent_description, "inline_agent_instructions": inline_agent_instructions, "inline_agent_name": inline_agent_name, "inline_agent_tools": inline_agent_tools, "name": name, "pre_authorized_tools": pre_authorized_tools, "run_on_all_corpuses": run_on_all_corpuses, "task_instructions": task_instructions, "trigger": trigger})
    return _mutate_CreateCorpusAction(CreateCorpusAction, None, info, **kwargs)


def _mutate_UpdateCorpusAction(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1195

    Port of UpdateCorpusAction.mutate
    """
    raise NotImplementedError("_mutate_UpdateCorpusAction not yet ported — see manifest")


def m_update_corpus_action(info: strawberry.Info, agent_config_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="agentConfigId", description='ID of the agent configuration (clears other action types)')] = strawberry.UNSET, analyzer_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="analyzerId", description='ID of the analyzer to run (clears other action types)')] = strawberry.UNSET, disabled: Annotated[Optional[bool], strawberry.argument(name="disabled", description='Whether the action is disabled')] = strawberry.UNSET, fieldset_id: Annotated[Optional[strawberry.ID], strawberry.argument(name="fieldsetId", description='ID of the fieldset to run (clears other action types)')] = strawberry.UNSET, id: Annotated[strawberry.ID, strawberry.argument(name="id", description='ID of the corpus action to update')] = strawberry.UNSET, name: Annotated[Optional[str], strawberry.argument(name="name", description='Updated name of the action')] = strawberry.UNSET, pre_authorized_tools: Annotated[Optional[list[Optional[str]]], strawberry.argument(name="preAuthorizedTools", description='Tools pre-authorized to run without approval')] = strawberry.UNSET, run_on_all_corpuses: Annotated[Optional[bool], strawberry.argument(name="runOnAllCorpuses", description='Whether to run this action on all corpuses')] = strawberry.UNSET, task_instructions: Annotated[Optional[str], strawberry.argument(name="taskInstructions", description='What the agent should do')] = strawberry.UNSET, trigger: Annotated[Optional[str], strawberry.argument(name="trigger", description='Updated trigger (add_document, edit_document, new_thread, new_message)')] = strawberry.UNSET) -> Optional["UpdateCorpusAction"]:
    kwargs = strip_unset({"agent_config_id": agent_config_id, "analyzer_id": analyzer_id, "disabled": disabled, "fieldset_id": fieldset_id, "id": id, "name": name, "pre_authorized_tools": pre_authorized_tools, "run_on_all_corpuses": run_on_all_corpuses, "task_instructions": task_instructions, "trigger": trigger})
    return _mutate_UpdateCorpusAction(UpdateCorpusAction, None, info, **kwargs)


def m_delete_corpus_action(info: strawberry.Info, id: Annotated[str, strawberry.argument(name="id", description='ID of the corpus action to delete')] = strawberry.UNSET) -> Optional["DeleteCorpusAction"]:
    kwargs = strip_unset({"id": id})
    return drf_deletion(payload_cls=DeleteCorpusAction, model=CorpusAction, lookup_field="id", root=None, info=info, kwargs=kwargs)


def _mutate_RunCorpusAction(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1387

    Port of RunCorpusAction.mutate
    """
    raise NotImplementedError("_mutate_RunCorpusAction not yet ported — see manifest")


def m_run_corpus_action(info: strawberry.Info, corpus_action_id: Annotated[strawberry.ID, strawberry.argument(name="corpusActionId", description='ID of the CorpusAction to run')] = strawberry.UNSET, document_id: Annotated[strawberry.ID, strawberry.argument(name="documentId", description='ID of the Document to run the action against')] = strawberry.UNSET) -> Optional["RunCorpusAction"]:
    kwargs = strip_unset({"corpus_action_id": corpus_action_id, "document_id": document_id})
    return _mutate_RunCorpusAction(RunCorpusAction, None, info, **kwargs)


def _mutate_StartCorpusActionBatchRun(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1503

    Port of StartCorpusActionBatchRun.mutate
    """
    raise NotImplementedError("_mutate_StartCorpusActionBatchRun not yet ported — see manifest")


def m_start_corpus_action_batch_run(info: strawberry.Info, corpus_action_id: Annotated[strawberry.ID, strawberry.argument(name="corpusActionId", description='ID of the agent-based CorpusAction to batch-run')] = strawberry.UNSET) -> Optional["StartCorpusActionBatchRun"]:
    kwargs = strip_unset({"corpus_action_id": corpus_action_id})
    return _mutate_StartCorpusActionBatchRun(StartCorpusActionBatchRun, None, info, **kwargs)


def _mutate_AddTemplateToCorpus(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1575

    Port of AddTemplateToCorpus.mutate
    """
    raise NotImplementedError("_mutate_AddTemplateToCorpus not yet ported — see manifest")


def m_add_template_to_corpus(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus to add the template to')] = strawberry.UNSET, template_id: Annotated[strawberry.ID, strawberry.argument(name="templateId", description='ID of the CorpusActionTemplate to clone')] = strawberry.UNSET) -> Optional["AddTemplateToCorpus"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "template_id": template_id})
    return _mutate_AddTemplateToCorpus(AddTemplateToCorpus, None, info, **kwargs)


def _mutate_SetupCorpusIntelligence(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1665

    Port of SetupCorpusIntelligence.mutate
    """
    raise NotImplementedError("_mutate_SetupCorpusIntelligence not yet ported — see manifest")


def m_setup_corpus_intelligence(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='ID of the corpus to set up.')] = strawberry.UNSET) -> Optional["SetupCorpusIntelligence"]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_SetupCorpusIntelligence(SetupCorpusIntelligence, None, info, **kwargs)


def _mutate_ToggleCorpusMemory(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1719

    Port of ToggleCorpusMemory.mutate
    """
    raise NotImplementedError("_mutate_ToggleCorpusMemory not yet ported — see manifest")


def m_toggle_corpus_memory(info: strawberry.Info, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId", description='The global ID of the corpus to toggle memory for')] = strawberry.UNSET, enabled: Annotated[bool, strawberry.argument(name="enabled", description='Whether to enable (true) or disable (false) memory')] = strawberry.UNSET) -> Optional["ToggleCorpusMemory"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "enabled": enabled})
    return _mutate_ToggleCorpusMemory(ToggleCorpusMemory, None, info, **kwargs)


def _mutate_CreateArtifact(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1776

    Port of CreateArtifact.mutate
    """
    raise NotImplementedError("_mutate_CreateArtifact not yet ported — see manifest")


def m_create_artifact(info: strawberry.Info, byline: Annotated[Optional[str], strawberry.argument(name="byline")] = strawberry.UNSET, config: Annotated[Optional[GenericScalar], strawberry.argument(name="config")] = strawberry.UNSET, corpus_id: Annotated[strawberry.ID, strawberry.argument(name="corpusId")] = strawberry.UNSET, subtitle: Annotated[Optional[str], strawberry.argument(name="subtitle")] = strawberry.UNSET, template: Annotated[str, strawberry.argument(name="template")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["CreateArtifact"]:
    kwargs = strip_unset({"byline": byline, "config": config, "corpus_id": corpus_id, "subtitle": subtitle, "template": template, "title": title})
    return _mutate_CreateArtifact(CreateArtifact, None, info, **kwargs)


def _mutate_UpdateArtifact(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1836

    Port of UpdateArtifact.mutate
    """
    raise NotImplementedError("_mutate_UpdateArtifact not yet ported — see manifest")


def m_update_artifact(info: strawberry.Info, byline: Annotated[Optional[str], strawberry.argument(name="byline")] = strawberry.UNSET, config: Annotated[Optional[GenericScalar], strawberry.argument(name="config")] = strawberry.UNSET, slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET, subtitle: Annotated[Optional[str], strawberry.argument(name="subtitle")] = strawberry.UNSET, title: Annotated[Optional[str], strawberry.argument(name="title")] = strawberry.UNSET) -> Optional["UpdateArtifact"]:
    kwargs = strip_unset({"byline": byline, "config": config, "slug": slug, "subtitle": subtitle, "title": title})
    return _mutate_UpdateArtifact(UpdateArtifact, None, info, **kwargs)


def _mutate_SetArtifactImage(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1892

    Port of SetArtifactImage.mutate
    """
    raise NotImplementedError("_mutate_SetArtifactImage not yet ported — see manifest")


def m_set_artifact_image(info: strawberry.Info, base64_png: Annotated[str, strawberry.argument(name="base64Png", description='data-URL or raw base64 PNG bytes.')] = strawberry.UNSET, slug: Annotated[str, strawberry.argument(name="slug")] = strawberry.UNSET) -> Optional["SetArtifactImage"]:
    kwargs = strip_unset({"base64_png": base64_png, "slug": slug})
    return _mutate_SetArtifactImage(SetArtifactImage, None, info, **kwargs)



MUTATION_FIELDS = {
    "fork_corpus": strawberry.field(resolver=m_fork_corpus, name="forkCorpus"),
    "re_embed_corpus": strawberry.field(resolver=m_re_embed_corpus, name="reEmbedCorpus", description="Re-embed all annotations in a corpus with a different embedder (Issue #437).\n\nThis is the controlled migration path for changing a corpus's embedder\nafter documents have been added. It:\n1. Validates the new embedder exists in the registry\n2. Locks the corpus (backend_lock=True)\n3. Queues a background task that updates preferred_embedder and\n   generates new embeddings for all annotations\n4. The corpus unlocks automatically when re-embedding completes\n\nOnly the corpus creator can trigger re-embedding."),
    "set_corpus_visibility": strawberry.field(resolver=m_set_corpus_visibility, name="setCorpusVisibility", description='Set corpus visibility (public/private).\n\nRequires one of:\n- User is the corpus creator (owner), OR\n- User has PERMISSION permission on the corpus, OR\n- User is superuser\n\nSecurity notes:\n- Permission check prevents users from escalating access\n- Uses existing make_corpus_public_task for cascading public visibility\n- Making private only affects the corpus flag (child objects remain public)'),
    "create_corpus": strawberry.field(resolver=m_create_corpus, name="createCorpus"),
    "update_corpus": strawberry.field(resolver=m_update_corpus, name="updateCorpus"),
    "update_corpus_description": strawberry.field(resolver=m_update_corpus_description, name="updateCorpusDescription", description="Mutation to update a corpus's markdown description, creating a new version in the process.\nOnly the corpus creator can update the description."),
    "delete_corpus": strawberry.field(resolver=m_delete_corpus, name="deleteCorpus"),
    "link_documents_to_corpus": strawberry.field(resolver=m_link_documents_to_corpus, name="linkDocumentsToCorpus", description='Add existing documents to a corpus.\n\nDelegates to CorpusDocumentService.add_documents_to_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Document validation (user owns or public)\n- Dual-system update (DocumentPath + corpus.add_document)'),
    "remove_documents_from_corpus": strawberry.field(resolver=m_remove_documents_from_corpus, name="removeDocumentsFromCorpus", description='Remove documents from a corpus (soft-delete).\n\nDelegates to CorpusDocumentService.remove_documents_from_corpus() for:\n- Permission checking (corpus UPDATE permission)\n- Soft-delete via DocumentPath (creates is_deleted=True record)\n- Audit trail'),
    "create_corpus_action": strawberry.field(resolver=m_create_corpus_action, name="createCorpusAction", description='Create a new CorpusAction that will be triggered when events occur in a corpus.\n\nAction types:\n- **Fieldset**: Run data extraction (fieldset_id)\n- **Analyzer**: Run classification/annotation (analyzer_id)\n- **Agent**: Execute an AI agent task. Provide task_instructions describing what the\n  agent should do. Optionally link an agent_config_id for custom persona/tool defaults,\n  or use create_agent_inline=True for thread/message moderation.\n- **Lightweight agent**: Just provide task_instructions (no agent_config needed).\n  The system auto-selects tools based on the trigger type.\n\nRequires UPDATE permission on the corpus.'),
    "update_corpus_action": strawberry.field(resolver=m_update_corpus_action, name="updateCorpusAction", description='Update an existing CorpusAction.\nAllows updating name, trigger, action type (fieldset/analyzer/agent), disabled state,\nand agent-specific settings.\nRequires the user to be the creator of the action.'),
    "delete_corpus_action": strawberry.field(resolver=m_delete_corpus_action, name="deleteCorpusAction", description='Mutation to delete a CorpusAction.\nRequires the user to be the creator of the action or have appropriate permissions.'),
    "run_corpus_action": strawberry.field(resolver=m_run_corpus_action, name="runCorpusAction", description='Manually trigger a specific agent-based corpus action on a document.\n\nSuperuser-only. Creates a CorpusActionExecution record and dispatches\nthe run_agent_corpus_action Celery task.'),
    "start_corpus_action_batch_run": strawberry.field(resolver=m_start_corpus_action_batch_run, name="startCorpusActionBatchRun", description='Run an agent-based corpus action against every eligible document in the corpus.'),
    "add_template_to_corpus": strawberry.field(resolver=m_add_template_to_corpus, name="addTemplateToCorpus", description='Add an action template to a corpus by cloning it into a CorpusAction.\n\nThis is the core of the Action Library feature: users browse available\ntemplates and opt-in per corpus. Once cloned, the action is a regular\nCorpusAction that can be edited/toggled/deleted like any other.\n\nPrevents duplicates: the same template cannot be added twice to the same\ncorpus (checked via source_template FK).\n\nRequires the user to be the corpus creator or have CRUD permission.'),
    "setup_corpus_intelligence": strawberry.field(resolver=m_setup_corpus_intelligence, name="setupCorpusIntelligence", description='One-click collection-intelligence setup.\n\nComposes the default enrichment bundle in a single idempotent call:\ninstalls the reference-enrichment analyzer as an ``add_document`` action\nand starts the first weave (deterministic), then clones the description +\nsummary action templates and batch-runs each over every document already\nin the corpus (LLM). Safe to repeat — every step skips work that already\nexists. Requires CRUD permission on the corpus — the tier\nAddTemplateToCorpus and CreateCorpusAction gate the identical writes at.'),
    "toggle_corpus_memory": strawberry.field(resolver=m_toggle_corpus_memory, name="toggleCorpusMemory", description='Toggle the agent memory system on/off for a corpus.\n\nWhen enabled, agents accumulate reusable insights from conversations\ninto a memory document. The memory document is a first-class Document\nin the corpus, visible and editable by users.\n\nIMPORTANT: When memory is enabled, conversation patterns (NOT specific\ncontent) may be distilled into the memory document. Users should be\naware of this when discussing sensitive topics.\n\nRequires CRUD permission on the corpus.'),
    "create_artifact": strawberry.field(resolver=m_create_artifact, name="createArtifact", description="Create a shareable poster (Artifact) of a corpus from a template.\n\nREAD-gated on the corpus (you can make a poster of any collection you can\nsee): its ``/a/<slug>`` link is shareable to anyone who can read the\nsource corpus (corpus-as-gate ONLY — there is no per-artifact visibility\noverride), and its data still only renders to viewers who can read the\ncorpus. ``template`` is validated against the service's registry."),
    "update_artifact": strawberry.field(resolver=m_update_artifact, name="updateArtifact", description="Edit an artifact's configurable captions — creator only."),
    "set_artifact_image": strawberry.field(resolver=m_set_artifact_image, name="setArtifactImage", description='Persist the rendered poster PNG so ``/a/<slug>`` has a stable og:image.\n\nThe poster is an SVG rendered client-side; the editor rasterises it and\nuploads the bytes here on save. (A production deploy can swap in a headless\nserver render behind the same field without changing the contract.)\nCreator-only.'),
}
