from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.authority_sources import (
    AuthoritySourceRecord,
    host_matches_declared_sources,
)
from opencontractserver.pipeline.base.base_component import PipelineComponentBase

if TYPE_CHECKING:
    from opencontractserver.pipeline.base.base_authority_discovery_provider import (
        DiscoveryCandidate,
    )


@dataclass
class AuthorityRequest:
    """A resolved, provider-specific fetch plan for one canonical_key.

    locate() turns a canonical_key into this; fetch() executes it. Keeping them
    separate lets tests assert URL/param derivation without any network call.

    ``params`` and ``extra`` are provider-owned mutable scratch, freshly built by
    each ``locate()`` call (never shared/aliased between callers), so a provider
    may read or mutate them in ``fetch()`` without copying.
    """

    canonical_key: str  # "usc-15:78j"
    url: str  # fully-formed endpoint
    # Always-dict (never None) so callers index them without guards.
    params: dict = field(default_factory=dict)  # query params (eCFR: part/section)
    citation: str | None = None  # human cite, "15 U.S.C. § 78j"
    extra: dict = field(default_factory=dict)  # provider scratch (title, volume)
    # Durable listing-discovery context, when this request originated from a
    # BaseAuthorityDiscoveryProvider candidate.  Existing citation-keyed
    # providers leave this as None; listing-backed providers can use the exact
    # discovered URL/title/extra without trying to reverse-engineer them from a
    # canonical key.
    discovery_candidate: DiscoveryCandidate | None = None


class BaseAuthoritySourceProvider(PipelineComponentBase, ABC):
    """Resolves a wanted canonical_key to one-or-more AuthoritySection objects.

    A provider owns a family of canonical-key prefixes (declared in
    supported_prefixes) and knows how to (a) recognise a key it can serve,
    (b) map that key to an external request, and (c) fetch + parse the response
    into AuthoritySection[] ready for bootstrap_authority_corpus.

    All HTTP belongs in _fetch_impl; _locate_impl is pure (no I/O) so tests
    exercise URL/citation derivation deterministically.
    """

    # canonical_key prefixes this provider serves, e.g. ("usc-15", "usc-17")
    # or a regex-able family. Used by the default can_handle().
    supported_prefixes: ClassVar[tuple[str, ...]] = ()
    # The authority body's licence — gates ingestion to public-domain only.
    license: ClassVar[str] = "public-domain"
    # Lower priority value = preferred; deterministic providers default to 100.
    # The agentic fallback uses 9999 to ensure it is always last resort.
    priority: ClassVar[int] = 100
    # When True the gate parks the result at pending_approval instead of ingesting.
    requires_approval: ClassVar[bool] = False
    # Set False to exclude a provider from _provider_for selection.
    enabled: ClassVar[bool] = True

    # ---- public API (registry/orchestrator calls these) ---------------------
    def can_handle(self, canonical_key: str) -> bool:
        """Return True if this provider serves *canonical_key*.

        MUST be stateless. The discovery orchestrator instantiates each provider
        once per ``_provider_for`` call and probes the SAME instance with multiple
        candidate keys (then reuses it for ``locate``/``fetch``), so an override
        that stashed match state on ``self`` here would leak stale state across
        keys. Derive everything ``locate``/``fetch`` need from the key passed to
        them instead.
        """
        prefix = canonical_key.split(":", 1)[0]
        return prefix in self.supported_prefixes

    def locate(
        self,
        canonical_key: str,
        *,
        discovery_candidate: DiscoveryCandidate | None = None,
        **direct_kwargs,
    ) -> AuthorityRequest:
        """Build a fetch request for *canonical_key*.

        ``discovery_candidate`` is supplied by the frontier orchestrator for
        listing-discovered documents.  It is passed to ``_locate_impl`` so a
        provider can select the exact discovered URL, then retained on the
        resulting request for fetch-time metadata/provenance.  The keyword is
        optional, preserving the citation-keyed provider contract.
        """
        merged = {**self.get_component_settings(), **direct_kwargs}
        if discovery_candidate is not None:
            merged["discovery_candidate"] = discovery_candidate
        request = self._locate_impl(canonical_key, **merged)
        if discovery_candidate is not None and request.discovery_candidate is None:
            request.discovery_candidate = discovery_candidate
        self._validate_declared_url(request.url, label="initial request")
        return request

    def fetch(
        self, request: AuthorityRequest, **direct_kwargs
    ) -> Sequence[AuthoritySection | AuthoritySourceRecord]:
        # Callers may construct AuthorityRequest directly in tests/integrations,
        # so repeat the initial-host check at the I/O boundary.
        self._validate_declared_url(request.url, label="initial request")
        merged = {**self.get_component_settings(), **direct_kwargs}
        sections = self._fetch_impl(request, **merged)
        source_hosts = self._declared_source_hosts()
        if source_hosts:
            for section in sections:
                self._validate_declared_url(
                    section.source_url or "",
                    label=f"returned source for {section.key}",
                )
                if not isinstance(section, AuthoritySourceRecord):
                    raise ValueError(
                        f"{type(self).__name__} declares source_hosts and must "
                        "return AuthoritySourceRecord with redirect provenance"
                    )
                final_host = section.metadata.get("final_source_host")
                if not isinstance(final_host, str) or not final_host.strip():
                    raise ValueError(
                        f"{type(self).__name__} record {section.canonical_key!r} "
                        "is missing final_source_host provenance"
                    )
                if not host_matches_declared_sources(final_host, source_hosts):
                    raise ValueError(
                        f"{type(self).__name__} redirect-final host "
                        f"{final_host!r} is outside declared source_hosts "
                        f"{source_hosts!r}"
                    )
        return sections

    def verify_publisher_evidence(
        self,
        canonical_key: str,
        record: AuthoritySourceRecord,
    ) -> bool:
        """Verify a rich record's key from publisher-originated evidence.

        The default is deliberately fail-closed.  Pack providers must override
        this method and derive ``canonical_key`` from the record's raw
        ``publisher_evidence``; comparing it only with ``record.canonical_key``
        would trust the request echoed by the provider and is not verification.
        """

        del canonical_key, record
        return False

    def _validate_declared_url(self, url: str, *, label: str) -> None:
        source_hosts = self._declared_source_hosts()
        if not source_hosts:
            return
        host = urlparse(url).hostname
        if not host_matches_declared_sources(host, source_hosts):
            raise ValueError(
                f"{type(self).__name__} {label} host {host!r} is outside "
                f"declared source_hosts {source_hosts!r}"
            )

    def _declared_source_hosts(self) -> tuple[str, ...]:
        # Lazy import avoids an early pipeline-registry cycle:
        # authority_pack_config itself uses authority_pack_dirs().
        from opencontractserver.enrichment.services.authority_source_hosts import (
            source_hosts_for_pack_component,
        )

        return source_hosts_for_pack_component(type(self))

    # ---- subclass contract --------------------------------------------------
    @abstractmethod
    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest: ...

    @abstractmethod
    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> Sequence[AuthoritySection | AuthoritySourceRecord]: ...
