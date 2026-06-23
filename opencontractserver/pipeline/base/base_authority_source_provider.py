from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_component import PipelineComponentBase


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
        prefix = canonical_key.split(":", 1)[0]
        return prefix in self.supported_prefixes

    def locate(self, canonical_key: str, **direct_kwargs) -> AuthorityRequest:
        merged = {**self.get_component_settings(), **direct_kwargs}
        return self._locate_impl(canonical_key, **merged)

    def fetch(
        self, request: AuthorityRequest, **direct_kwargs
    ) -> list[AuthoritySection]:
        merged = {**self.get_component_settings(), **direct_kwargs}
        return self._fetch_impl(request, **merged)

    # ---- subclass contract --------------------------------------------------
    @abstractmethod
    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest: ...

    @abstractmethod
    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySection]: ...
