"""Static safety contract for Grid Dossier's standalone corpus source plans."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import TestCase
from urllib.parse import urlparse

import yaml

from opencontractserver.enrichment.authority_import_artifacts import read_source_plan

PACK_ROOT = (
    Path(__file__).resolve().parents[1] / "enrichment" / "data" / "authority_packs"
)

EXPECTED_CORPORA = {
    "texas_electric_law": {
        "texas-electric-statutes",
        "texas-large-load-legislative-history",
    },
    "puct_electric": {
        "puct-electric-rules-and-orders",
        "puct-large-load-proceedings",
    },
    "ercot_large_load": {
        "ercot-current-large-load-rules",
        "ercot-large-load-revision-history",
        "ercot-large-load-implementation",
    },
    "oncor_delivery": {
        "oncor-current-delivery-tariff",
        "oncor-tariff-history",
        "oncor-service-requirements",
    },
}

EXPECTED_DISCOVERY_PROVIDERS = {
    "TexasBillHistoryDiscoveryProvider",
    "PUCTProjectDiscoveryProvider",
    "PUCTRuleDiscoveryProvider",
    "ERCOTGuideLibraryDiscoveryProvider",
    "ERCOTIssueIndexDiscoveryProvider",
    "ERCOTLargeLoadPageDiscoveryProvider",
    "OncorTariffIndexDiscoveryProvider",
    "OncorServiceDocumentDiscoveryProvider",
}

STABLE_SEED_KEYS = {
    "tx-util:37.0561",
    "tx-util:39.151",
    "tx-sb:89r-6:enrolled",
    "tx-admin-puct:25.214",
    "tx-admin-puct:25.361",
    "puct-project:59142",
    "ercot-planning:9",
    "ercot-protocol:16",
    "ercot-pgrr:145",
    "ercot-nprr:1325",
    "ercot-notice:M-B062326-01",
    "ercot-notice:M-B062326-02",
    "ercot-notice:M-B062326-03",
    "ercot-notice:M-B062326-04",
    "ercot-notice:M-B062326-05",
    "ercot-notice:M-B062326-06",
    "ercot-form:batch-zero-load-information-form-06172026",
    "oncor-tariff:retail-delivery",
    "oncor-tariff:retail-delivery-2017-11-27",
    "oncor-service-guide:electric-service-guidelines",
}


def _yaml(path: Path) -> dict:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{path} does not contain a YAML mapping")
    return parsed


def _urls(source: dict) -> list[str]:
    return [
        *source.get("index_urls", []),
        *[
            candidate["url"]
            for candidate in source.get("candidates", [])
            if candidate.get("url")
        ],
    ]


class GridDossierSourcePlanTests(TestCase):
    def test_manifests_bind_standalone_plans_covering_all_ten_corpora(self):
        all_target_corpora: set[str] = set()

        for pack_name, expected_corpora in EXPECTED_CORPORA.items():
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            self.assertEqual(manifest["sources"], "sources.yaml")

            source_path = pack_dir / manifest["sources"]
            plan = read_source_plan(source_path)
            target_corpora = {source["corpus_slug"] for source in plan["sources"]}
            self.assertEqual(target_corpora, expected_corpora)
            all_target_corpora.update(target_corpora)

        self.assertEqual(len(all_target_corpora), 10)

    def test_every_live_listing_is_bounded_filtered_and_official(self):
        observed_discovery_providers: set[str] = set()

        for pack_name in EXPECTED_CORPORA:
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            allowed_hosts = manifest["source_hosts"]
            plan = read_source_plan(pack_dir / manifest["sources"])

            for source in plan["sources"]:
                for url in _urls(source):
                    parsed = urlparse(url)
                    self.assertEqual(parsed.scheme, "https")
                    hostname = parsed.hostname or ""
                    self.assertTrue(
                        any(
                            hostname == allowed or hostname.endswith(f".{allowed}")
                            for allowed in allowed_hosts
                        ),
                        f"{source['id']}: {url} is outside {allowed_hosts}",
                    )

                provider = source.get("discovery_provider")
                if provider is None:
                    continue
                observed_discovery_providers.add(provider)
                self.assertIn("candidate_filters", source)
                cap = source.get("discovery_kwargs", {}).get("max_candidates")
                self.assertIsInstance(cap, int)
                self.assertGreater(cap, 0)
                self.assertLessEqual(cap, 500)

        self.assertEqual(
            observed_discovery_providers,
            EXPECTED_DISCOVERY_PROVIDERS,
        )

    def test_every_grid_dossier_source_fetches_full_publisher_content(self):
        source_ids: set[str] = set()

        for pack_name in EXPECTED_CORPORA:
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            plan = read_source_plan(pack_dir / manifest["sources"])

            for source in plan["sources"]:
                self.assertEqual(
                    source["ingestion_mode"],
                    "full_content",
                    f"{pack_name}/{source['id']} must fetch publisher bytes",
                )
                self.assertNotIn(
                    "parent_relationship_type",
                    source,
                    "full-content providers own their typed relationships",
                )
                source_ids.add(f"{pack_name}/{source['id']}")

        # Deliberately avoid a document-count assertion. Live publisher listings,
        # especially active PUCT proceedings, can add records between runs.
        self.assertGreater(len(source_ids), len(EXPECTED_CORPORA))

    def test_stable_seed_candidates_retain_warning_display_titles(self):
        candidates_by_key: dict[str, dict] = {}

        for pack_name in EXPECTED_CORPORA:
            pack_dir = PACK_ROOT / pack_name
            manifest = _yaml(pack_dir / "pack.yaml")
            plan = read_source_plan(pack_dir / manifest["sources"])
            for source in plan["sources"]:
                for candidate in source.get("candidates", []):
                    candidates_by_key[candidate["canonical_key"]] = candidate

        self.assertTrue(STABLE_SEED_KEYS <= candidates_by_key.keys())
        for canonical_key in STABLE_SEED_KEYS:
            candidate = candidates_by_key[canonical_key]
            self.assertTrue(candidate["publisher_title"].strip())
            self.assertIn(
                "REVIEW REQUIRED",
                candidate["display_title"],
                canonical_key,
            )

    def test_puct_project_root_and_all_attachment_discovery_use_pack_ca_bundle(self):
        pack_dir = PACK_ROOT / "puct_electric"
        manifest = _yaml(pack_dir / "pack.yaml")
        plan = read_source_plan(pack_dir / manifest["sources"])
        by_id = {source["id"]: source for source in plan["sources"]}

        rule_discovery = by_id["puct-electric-rule-discovery"]
        self.assertEqual(
            rule_discovery["index_urls"],
            ["https://puc.texas.gov/agency/rulesnlaws/subrules/electric/"],
        )
        project_seed = by_id["puct-project-59142-seed"]
        self.assertEqual(project_seed["ingestion_mode"], "full_content")
        self.assertNotIn("discovery_provider", project_seed)
        self.assertEqual(
            [item["canonical_key"] for item in project_seed["candidates"]],
            ["puct-project:59142"],
        )

        project_discovery = next(
            source
            for source in plan["sources"]
            if source.get("discovery_provider") == "PUCTProjectDiscoveryProvider"
        )
        self.assertEqual(project_discovery["ingestion_mode"], "full_content")
        self.assertEqual(
            project_discovery["corpus_slug"],
            "puct-large-load-proceedings",
        )
        self.assertEqual(
            project_discovery["index_urls"],
            ["https://interchange.puc.texas.gov/search/filings/?ControlNumber=59142"],
        )
        self.assertGreaterEqual(
            project_discovery["discovery_kwargs"]["max_detail_pages"],
            1,
        )

        ca_path = "certificates/interchange-missing-intermediates.pem"
        for source, kwargs_name in (
            (project_seed, "fetch_kwargs"),
            (project_discovery, "discovery_kwargs"),
            (project_discovery, "fetch_kwargs"),
        ):
            self.assertEqual(
                source[kwargs_name]["extra_ca_certificates"],
                [ca_path],
            )
        self.assertTrue((pack_dir / ca_path).is_file())

    def test_texas_sb6_excludes_only_enrolled_billtext_representations(self):
        pack_dir = PACK_ROOT / "texas_electric_law"
        manifest = _yaml(pack_dir / "pack.yaml")
        plan = read_source_plan(pack_dir / manifest["sources"])
        history = next(
            source
            for source in plan["sources"]
            if source["id"] == "texas-sb6-history-discovery"
        )
        exclude_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in history["candidate_filters"]["exclude_url"]
        ]

        def excluded(url: str) -> bool:
            return any(pattern.search(url) for pattern in exclude_patterns)

        for url in (
            "https://capitol.texas.gov/tlodocs/89R/billtext/html/SB00006F.htm",
            "https://capitol.texas.gov/tlodocs/89R/billtext/pdf/SB00006F.pdf",
            "https://capitol.texas.gov/tlodocs/89R/billtext/doc/SB00006F.docx",
        ):
            self.assertTrue(excluded(url), url)
        for url in (
            "https://capitol.texas.gov/tlodocs/89R/fiscalnotes/html/SB00006F.htm",
            "https://capitol.texas.gov/tlodocs/89R/analysis/html/SB00006F.htm",
        ):
            self.assertFalse(excluded(url), url)

    def test_real_oncor_history_lineage_replaces_synthetic_fixture(self):
        pack_dir = PACK_ROOT / "oncor_delivery"
        manifest = _yaml(pack_dir / "pack.yaml")
        relationships = _yaml(pack_dir / manifest["relationships"])["relationships"]
        by_source: dict[str, set[tuple[str, str]]] = {}
        for relationship in relationships:
            by_source.setdefault(relationship["source_key"], set()).add(
                (
                    relationship["relationship_type"],
                    relationship["target_key"],
                )
            )

        logical_key = "oncor-tariff:retail-delivery"
        real_key = "oncor-tariff:retail-delivery-2017-11-27"
        expected_edges = {
            ("EFFECTIVE_VERSION_OF", logical_key),
            ("SUPERSEDED_BY", logical_key),
        }
        self.assertTrue(expected_edges <= by_source[real_key])
        self.assertNotIn(
            "oncor-tariff:retail-delivery-2025-03-01",
            by_source,
        )

        service_spec = json.loads(
            (
                pack_dir / "specs" / "oncor-service-and-construction-requirements.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn(
            "Electric%20Service%20Guidelines%20Book.pdf",
            service_spec["sections"][0]["source_url"],
        )
