"""Management command that drives :func:`run_benchmark` from the CLI.

Usage::

    docker compose -f local.yml run django python manage.py run_benchmark \\
        --benchmark legalbench-rag \\
        --path /data/legalbench-rag \\
        --user admin \\
        --model openai:gpt-4o-mini \\
        --top-k 10 \\
        --subsets cuad privacy_qa \\
        --limit 50 \\
        --run-dir /tmp/lbrag_run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.benchmarks.adapters.legalbench_rag import (
    LEGALBENCH_RAG_SUBSETS,
    LegalBenchRAGAdapter,
)
from opencontractserver.benchmarks.runner import run_benchmark
from opencontractserver.constants.benchmarks import (
    BENCHMARK_DEFAULT_MODEL,
    BENCHMARK_DEFAULT_TOP_K,
)

logger = logging.getLogger(__name__)

# Registry of benchmark-name -> factory.  Adding a new benchmark means
# writing an adapter and registering it here; the CLI shape stays identical.
BENCHMARK_REGISTRY = {
    "legalbench-rag": LegalBenchRAGAdapter,
}


class Command(BaseCommand):
    help = (
        "Run an external RAG benchmark (e.g. LegalBench-RAG) against the "
        "OpenContracts extract pipeline and compute retrieval + answer "
        "metrics."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--benchmark",
            default="legalbench-rag",
            choices=sorted(BENCHMARK_REGISTRY.keys()),
            help="Which benchmark adapter to use.",
        )
        parser.add_argument(
            "--path",
            required=True,
            type=Path,
            help=(
                "Path to the benchmark dataset root directory "
                "(must contain corpus/ and benchmarks/ subfolders for "
                "LegalBench-RAG)."
            ),
        )
        parser.add_argument(
            "--user",
            required=True,
            help="Username of the Django user that will own created objects.",
        )
        parser.add_argument(
            "--model",
            default=BENCHMARK_DEFAULT_MODEL,
            help=(
                f"LLM identifier passed to the extractor. Default: {BENCHMARK_DEFAULT_MODEL}."
            ),
        )
        parser.add_argument(
            "--top-k",
            type=int,
            default=BENCHMARK_DEFAULT_TOP_K,
            help="Top-k used by the retrieval probe.",
        )
        parser.add_argument(
            "--subsets",
            nargs="*",
            help=(
                "Restrict to specific LegalBench-RAG subsets. "
                f"Valid choices: {', '.join(LEGALBENCH_RAG_SUBSETS)}"
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap total number of tasks (smoke-test mode).",
        )
        parser.add_argument(
            "--run-dir",
            type=Path,
            default=None,
            help=(
                "Directory to write report.json / report.csv / config.json. "
                "Defaults to ./benchmark_runs/<timestamp>_<benchmark>_<model>/."
            ),
        )
        parser.add_argument(
            "--run-label",
            default=None,
            help="Optional label stitched into the default run directory name.",
        )
        parser.add_argument(
            "--corpus-title",
            default=None,
            help="Override the generated corpus title.",
        )
        parser.add_argument(
            "--extraction-concurrency",
            type=int,
            default=1,
            help=(
                "Number of datacells to extract in parallel. 1 (default) is "
                "serial. Raise cautiously — per-provider rate limits apply. "
                "4-8 is typical for Anthropic; 8-16 for OpenAI on "
                "well-provisioned keys."
            ),
        )

    def handle(self, *args, **options) -> None:
        username = options["user"]
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User {username!r} not found") from exc

        benchmark_name = options["benchmark"]
        adapter_cls = BENCHMARK_REGISTRY[benchmark_name]
        adapter = adapter_cls(
            root=options["path"],
            subsets=options.get("subsets") or None,
            limit=options.get("limit"),
        )

        self.stdout.write(
            self.style.NOTICE(
                f"Running benchmark {benchmark_name} as user {user.username} "
                f"with model {options['model']} (top_k={options['top_k']})"
            )
        )

        report = run_benchmark(
            adapter=adapter,
            user=user,
            model=options["model"],
            top_k=options["top_k"],
            run_dir=options.get("run_dir"),
            corpus_title=options.get("corpus_title"),
            run_label=options.get("run_label"),
            extraction_concurrency=options["extraction_concurrency"],
        )

        self.stdout.write(self.style.SUCCESS("Benchmark run complete."))
        self.stdout.write(f"  Corpus ID:  {report.corpus_id}")
        self.stdout.write(f"  Extract ID: {report.extract_id}")
        # Surface the report directory so operators don't have to grep logs
        # for "Benchmark report written to …" to find report.json / report.csv.
        if report.run_dir is not None:
            self.stdout.write(f"  Report dir: {report.run_dir}")
        for key, value in sorted(report.aggregates.items()):
            if isinstance(value, float):
                self.stdout.write(f"  {key:<28} {value:.4f}")
            else:
                self.stdout.write(f"  {key:<28} {value}")
