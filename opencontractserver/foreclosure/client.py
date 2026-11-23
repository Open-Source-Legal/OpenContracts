"""HTTP client for the California foreclosure compliance service.

Talks to ``legalis-ca-foreclosure-api``, which exposes the Rust ruleset over
three endpoints: ``/health``, ``/v1/rules`` and ``/v1/evaluate``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://foreclosure-api:8090"
DEFAULT_TIMEOUT_SECONDS = 30


class ForeclosureServiceError(RuntimeError):
    """The compliance service could not be reached or rejected the request."""


@dataclass(frozen=True)
class ComplianceResult:
    """What the service returned for one matter."""

    summary: dict[str, Any]
    report: dict[str, Any]
    text: str

    @property
    def violations(self) -> list[dict[str, Any]]:
        return [f for f in self.report.get("findings", []) if f.get("status") == "violation"]

    @property
    def requires_judgment(self) -> list[dict[str, Any]]:
        return [
            f
            for f in self.report.get("findings", [])
            if f.get("status") == "requires_judgment"
        ]

    @property
    def insufficient_record(self) -> list[dict[str, Any]]:
        return [
            f
            for f in self.report.get("findings", [])
            if f.get("status") == "insufficient_record"
        ]

    @property
    def needs_attention(self) -> bool:
        return bool(self.summary.get("needs_attention"))


def _base_url() -> str:
    return getattr(settings, "FORECLOSURE_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _timeout() -> int:
    return getattr(settings, "FORECLOSURE_API_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)


class ForeclosureComplianceClient:
    """Client for the compliance ruleset service."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.timeout = timeout or _timeout()

    def health(self) -> dict[str, Any]:
        """Ruleset identity and rule counts.

        Includes ``attorney_verified_count``, which the caller should surface
        rather than discard — a ruleset nobody has reviewed produces findings
        nobody should rely on unreviewed.
        """
        return self._get("/health")

    def rules(self) -> dict[str, Any]:
        """The full ruleset manifest: provisions, dated versions, review status."""
        return self._get("/v1/rules")

    def evaluate(self, matter: dict[str, Any]) -> ComplianceResult:
        """Evaluate a matter and return its compliance report."""
        payload = self._post("/v1/evaluate", matter)
        try:
            return ComplianceResult(
                summary=payload["summary"],
                report=payload["report"],
                text=payload.get("text", ""),
            )
        except KeyError as exc:
            raise ForeclosureServiceError(
                f"compliance service response missing {exc}"
            ) from exc

    # ---- transport -------------------------------------------------------- #

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}{path}", timeout=self.timeout)
        except requests.RequestException as exc:
            raise ForeclosureServiceError(
                f"could not reach the compliance service at {self.base_url}: {exc}"
            ) from exc
        return self._decode(response, path)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}{path}", json=body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise ForeclosureServiceError(
                f"could not reach the compliance service at {self.base_url}: {exc}"
            ) from exc
        return self._decode(response, path)

    @staticmethod
    def _decode(response: requests.Response, path: str) -> dict[str, Any]:
        # A 400 carries a machine-readable reason the caller can act on; keep
        # it rather than collapsing every failure into "service error".
        if response.status_code == 400:
            try:
                detail = response.json()
            except ValueError:
                detail = {"detail": response.text[:500]}
            raise ForeclosureServiceError(
                f"compliance service rejected the request: "
                f"{detail.get('error', 'bad_request')} — {detail.get('detail', '')}"
            )

        if not response.ok:
            raise ForeclosureServiceError(
                f"compliance service returned {response.status_code} for {path}: "
                f"{response.text[:500]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ForeclosureServiceError(
                f"compliance service returned non-JSON for {path}"
            ) from exc
