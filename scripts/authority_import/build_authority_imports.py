#!/usr/bin/env python3
"""Run pack source plans and build GUI-importable OpenContracts corpus ZIPs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one or more authority packs' standalone sources.yaml plans and "
            "write V2 corpus imports. No content is scraped by the web app."
        )
    )
    parser.add_argument(
        "pack_dirs",
        nargs="+",
        type=Path,
        help="Authority pack directories containing pack.yaml and sources.yaml",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("imports/manifest.json"),
        help="Cross-pack GUI/E2E manifest (default: imports/manifest.json)",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write artifacts and exit zero even when individual candidates failed",
    )
    parser.add_argument(
        "--rights-approved",
        action="store_true",
        help=(
            "Deliberately authorize full-content artifacts for LICENSED or "
            "REVIEW_REQUIRED records. The decision is recorded in each artifact."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    # Registry discovery needs Django's app registry, not a running web app or
    # its database. Reuse the existing off-cluster settings profile, whose
    # throwaway SQLite default lets registered providers fall back to their
    # normal code/env configuration when PipelineSettings is unavailable.
    os.environ["DJANGO_SETTINGS_MODULE"] = os.environ.get(
        "AUTHORITY_IMPORT_DJANGO_SETTINGS_MODULE",
        "config.settings.remote_worker",
    )
    import django

    django.setup()

    from opencontractserver.enrichment.authority_import_artifacts import (
        build_authority_import_artifacts,
        collect_from_source_plan,
        write_aggregate_manifest,
        write_collection_report,
    )

    all_cases = []
    had_errors = False
    for raw_pack_dir in args.pack_dirs:
        pack_dir = raw_pack_dir.resolve()
        records, report = collect_from_source_plan(
            pack_dir,
            rights_approved=args.rights_approved,
        )
        result = build_authority_import_artifacts(pack_dir, records)
        report.artifact_warnings.extend(
            {
                "archive": archive,
                "warnings": list(warnings),
            }
            for archive, warnings in result.validation_warnings.items()
            if warnings
        )
        write_collection_report(result.output_dir, report)
        all_cases.extend(result.cases)
        had_errors = had_errors or bool(report.errors)
        print(
            f"{result.pack_name}: {report.fetched} fetched, "
            f"{report.linked} link-only, "
            f"{len(result.zip_paths)} corpus import(s), "
            f"{len(report.errors)} error(s)"
        )
        for path in result.zip_paths:
            print(f"  {path}")

    manifest_path = args.manifest.resolve()
    write_aggregate_manifest(manifest_path, all_cases)
    print(f"Manifest: {manifest_path}")
    if had_errors and not args.allow_partial:
        print(
            "Collection completed with candidate errors; inspect scrape-report.json "
            "or rerun with --allow-partial to accept a partial artifact.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
