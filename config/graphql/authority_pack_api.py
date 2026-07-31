"""GraphQL adapters for the trusted server-side authority-pack catalog."""

from __future__ import annotations

from typing import Annotated

import strawberry
from graphql_relay import to_global_id

from config.graphql.core.scalars import GenericScalar
from opencontractserver.enrichment.services.authority_pack_service import (
    AuthorityPackPlan,
    AuthorityPackService,
)


@strawberry.type(name="AuthorityPackCorpus")
class AuthorityPackCorpusType:
    corpus_id: strawberry.ID | None = strawberry.field(name="corpusId")
    slug: str
    title: str
    approval_status: str = strawberry.field(name="approvalStatus")
    installed: bool
    is_public: bool = strawberry.field(name="isPublic")


@strawberry.type(name="AuthorityPack")
class AuthorityPackType:
    id: str
    name: str
    display_name: str = strawberry.field(name="displayName")
    description: str
    jurisdiction: str
    schema_version: int = strawberry.field(name="schemaVersion")
    fingerprint: str
    source_hosts: list[str] = strawberry.field(name="sourceHosts")
    valid: bool
    validation_error: str | None = strawberry.field(name="validationError")
    approval_status: str = strawberry.field(name="approvalStatus")
    can_install: bool = strawberry.field(name="canInstall")
    can_publish: bool = strawberry.field(name="canPublish")
    installed_count: int = strawberry.field(name="installedCount")
    public_count: int = strawberry.field(name="publicCount")
    total_corpora: int = strawberry.field(name="totalCorpora")
    installed: bool
    fully_public: bool = strawberry.field(name="fullyPublic")
    corpora: list[AuthorityPackCorpusType]


@strawberry.type(name="InstallAuthorityPackMutation")
class InstallAuthorityPackMutation:
    ok: bool
    message: str | None
    result: GenericScalar | None
    pack: AuthorityPackType | None


def _to_graphql(plan: AuthorityPackPlan) -> AuthorityPackType:
    return AuthorityPackType(
        id=plan.pack_id,
        name=plan.name,
        display_name=plan.display_name,
        description=plan.description,
        jurisdiction=plan.jurisdiction,
        schema_version=plan.schema_version,
        fingerprint=plan.fingerprint,
        source_hosts=list(plan.source_hosts),
        valid=plan.valid,
        validation_error=plan.validation_error,
        approval_status=plan.approval_status,
        can_install=plan.can_install,
        can_publish=plan.can_publish,
        installed_count=plan.installed_count,
        public_count=plan.public_count,
        total_corpora=plan.total_corpora,
        installed=plan.installed,
        fully_public=plan.fully_public,
        corpora=[
            AuthorityPackCorpusType(
                corpus_id=(
                    to_global_id("CorpusType", corpus.corpus_id)
                    if corpus.corpus_id is not None
                    else None
                ),
                slug=corpus.slug,
                title=corpus.title,
                approval_status=corpus.approval_status,
                installed=corpus.installed,
                is_public=corpus.is_public,
            )
            for corpus in plan.corpora
        ],
    )


def q_authority_packs(info: strawberry.Info) -> list[AuthorityPackType]:
    return [
        _to_graphql(plan) for plan in AuthorityPackService.catalog(info.context.user)
    ]


def q_authority_pack_preflight(
    info: strawberry.Info,
    pack_id: Annotated[str, strawberry.argument(name="packId")],
) -> AuthorityPackType | None:
    plan = AuthorityPackService.preflight(info.context.user, pack_id)
    return _to_graphql(plan) if plan is not None else None


def m_install_authority_pack(
    info: strawberry.Info,
    pack_id: Annotated[str, strawberry.argument(name="packId")],
    expected_fingerprint: Annotated[
        str, strawberry.argument(name="expectedFingerprint")
    ],
    publish: bool,
) -> InstallAuthorityPackMutation:
    result = AuthorityPackService.install(
        info.context.user,
        pack_id=pack_id,
        expected_fingerprint=expected_fingerprint,
        publish=publish,
    )
    if not result.ok or result.value is None:
        return InstallAuthorityPackMutation(
            ok=False,
            message=result.error,
            result=None,
            pack=None,
        )
    return InstallAuthorityPackMutation(
        ok=True,
        message=(
            "Authority pack installed and published."
            if publish
            else "Authority pack installed privately."
        ),
        result=result.value.as_dict(),
        pack=_to_graphql(result.value.pack),
    )


QUERY_FIELDS = {
    "authority_packs": strawberry.field(
        resolver=q_authority_packs,
        name="authorityPacks",
        description="Trusted authority packs configured on this server.",
    ),
    "authority_pack_preflight": strawberry.field(
        resolver=q_authority_pack_preflight,
        name="authorityPackPreflight",
        description="Side-effect-free validation of one trusted authority pack.",
    ),
}

MUTATION_FIELDS = {
    "install_authority_pack": strawberry.field(
        resolver=m_install_authority_pack,
        name="installAuthorityPack",
        description="Install a freshly preflighted trusted authority pack.",
    )
}
