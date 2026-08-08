"""Tests for the discover_authority_candidates management command (issue #2054).

The operator-invocable surface for Phase 2 discovery -- no admin UI, by design
(see the command's module docstring). HTTP is mocked (patching safe_fetch_text);
no network calls are made.
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
    DiscoveryResult,
)

_SAFE_FETCH_PATH = (
    "opencontractserver.pipeline.authority_discovery_providers."
    "listing_index_provider.safe_fetch_text"
)

_FIXTURE_HTML = """
<html><body>
<a href="/doc/1">Document One</a>
<a href="/doc/2">Document Two</a>
</body></html>
"""


class _CommandDiscoveryProvider:
    def discover_candidates(self, index_urls, *, max_candidates, exclude_identities):
        del max_candidates, exclude_identities
        return DiscoveryResult(
            candidates=[
                DiscoveryCandidate(
                    canonical_key="demo-provider:7",
                    url=f"{index_urls[0]}/document-7",
                    title="Provider document 7",
                )
            ],
            skipped_index_urls={},
            capped=False,
        )


class DiscoverAuthorityCandidatesCommandTests(TestCase):
    def _run(self, *extra_args):
        out, err = io.StringIO(), io.StringIO()
        call_command(
            "discover_authority_candidates",
            "--index-url=https://example.gov/listing",
            r'--link-pattern=<a href="(?P<url>/doc/(?P<id>\d+))">(?P<title>[^<]+)</a>',
            "--canonical-key-template={prefix}:{id}",
            "--prefix=demo",
            *extra_args,
            stdout=out,
            stderr=err,
        )
        return out.getvalue(), err.getvalue()

    def test_seeds_frontier_by_default(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "example.gov")):
            out, _ = self._run()
        self.assertIn("discovered 2 candidate(s)", out)
        self.assertIn("frontier seeded: created=2 appended=0 skipped=0", out)
        self.assertEqual(
            set(
                AuthorityFrontier.objects.filter(
                    canonical_key__in=["demo:1", "demo:2"]
                ).values_list("canonical_key", flat=True)
            ),
            {"demo:1", "demo:2"},
        )

    def test_dry_run_does_not_seed_frontier(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "example.gov")):
            out, _ = self._run("--dry-run")
        self.assertIn("--dry-run", out)
        self.assertFalse(
            AuthorityFrontier.objects.filter(
                canonical_key__in=["demo:1", "demo:2"]
            ).exists()
        )

    def test_rerun_is_idempotent(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "example.gov")):
            self._run()
            out, _ = self._run()
        self.assertIn("discovered 0 candidate(s); skipped 2 previously seeded", out)
        self.assertIn("frontier seeded: created=0 appended=0 skipped=0", out)

    def test_capped_reruns_make_deterministic_forward_progress(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "example.gov")):
            first, _ = self._run("--max-candidates=1")
            second, _ = self._run("--max-candidates=1")
        self.assertIn("demo:1", first)
        self.assertNotIn("demo:2", first)
        self.assertIn("demo:2", second)
        self.assertEqual(
            set(AuthorityFrontier.objects.values_list("canonical_key", flat=True)),
            {"demo:1", "demo:2"},
        )

    def test_max_candidates_cap_applied(self):
        with patch(_SAFE_FETCH_PATH, return_value=(_FIXTURE_HTML, "example.gov")):
            out, _ = self._run("--max-candidates=1", "--dry-run")
        self.assertIn("discovered 1 candidate(s) (capped)", out)

    def test_registered_provider_mode_needs_no_regex_rule(self):
        definition = SimpleNamespace(
            name="_CommandDiscoveryProvider",
            class_name="tests._CommandDiscoveryProvider",
            component_class=_CommandDiscoveryProvider,
        )
        out = io.StringIO()
        with patch(
            "opencontractserver.annotations.management.commands."
            "discover_authority_candidates."
            "get_all_authority_discovery_providers_cached",
            return_value=[definition],
        ):
            call_command(
                "discover_authority_candidates",
                "--index-url=https://example.gov/listing",
                "--provider=_CommandDiscoveryProvider",
                "--dry-run",
                stdout=out,
            )
        self.assertIn("demo-provider:7", out.getvalue())
        self.assertFalse(
            AuthorityFrontier.objects.filter(canonical_key="demo-provider:7").exists()
        )
