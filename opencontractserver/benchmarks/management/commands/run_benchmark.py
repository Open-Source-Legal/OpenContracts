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
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.benchmarks.adapters.legalbench_rag import (
    LEGALBENCH_RAG_SUBSETS,
    PAPER_MAX_TESTS_PER_BENCHMARK,
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
            help=(
                "Cap TOTAL number of tasks across all subsets (smoke-test "
                "mode). Applies after --paper-sampling truncation."
            ),
        )
        parser.add_argument(
            "--no-paper-sampling",
            dest="paper_sampling",
            action="store_false",
            default=True,
            help=(
                "Disable upstream-faithful per-subset sampling. By default "
                "the adapter reproduces "
                "``legalbenchrag/benchmark.py``'s SORT_BY_DOCUMENT=True "
                "selection (sort by random(seed=file_path), keep first 194 "
                "per subset). Pass this flag to load every task in JSON "
                "file order — useful for fixtures, NOT comparable to the "
                "paper's published numbers."
            ),
        )
        parser.add_argument(
            "--max-per-subset",
            type=int,
            default=PAPER_MAX_TESTS_PER_BENCHMARK,
            help=(
                "Per-subset cap when --paper-sampling is on. Defaults to "
                "upstream's MAX_TESTS_PER_BENCHMARK "
                f"= {PAPER_MAX_TESTS_PER_BENCHMARK}."
            ),
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
        parser.add_argument(
            "--retrieval-only",
            action="store_true",
            help=(
                "Skip the agent extract pass and score only the single-shot "
                "top-k retrieval probe. Produces LegalBench-RAG-parity char "
                "recall / precision numbers with no LLM calls."
            ),
        )
        parser.add_argument(
            "--corpus-wide",
            action="store_true",
            help=(
                "Widen the probe to the full corpus instead of filtering to "
                "the task's target document. Required for direct "
                "apples-to-apples comparison with LegalBench-RAG's paper, "
                "which has no document filter and forces the retriever to "
                "find the right file plus the right span in a single shot."
            ),
        )

    def handle(self, *args, **options) -> None:
        # Mark the process as a benchmark CLI invocation so
        # ``force_celery_eager`` will accept the global Celery-config
        # mutation. Without this opt-in env var the helper refuses to
        # run in non-test mode (issue #1410).
        os.environ.setdefault("OC_BENCHMARK_CLI", "1")

        username = options["user"]
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User {username!r} not found") from exc

        benchmark_name = options["benchmark"]
        adapter_cls = BENCHMARK_REGISTRY[benchmark_name]
        adapter_kwargs: dict[str, object] = {
            "root": options["path"],
            "subsets": options.get("subsets") or None,
            "limit": options.get("limit"),
        }
        # Only pass paper-sampling kwargs to adapters that accept them.
        # Today only LegalBenchRAGAdapter does; future adapters can opt in.
        if benchmark_name == "legalbench-rag":
            adapter_kwargs["paper_sampling"] = options.get("paper_sampling", True)
            adapter_kwargs["max_per_subset"] = options.get(
                "max_per_subset", PAPER_MAX_TESTS_PER_BENCHMARK
            )
        # mypy can't statically narrow ``adapter_kwargs: dict[str, object]``
        # against each adapter subclass's specific parameter types. The dict
        # values are sourced from argparse, which already validated them.
        adapter = adapter_cls(**adapter_kwargs)  # type: ignore[arg-type]

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
            retrieval_only=options.get("retrieval_only", False),
            corpus_wide=options.get("corpus_wide", False),
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
            elif isinstance(value, dict):
                # ``per_subset`` is the only dict-valued aggregate today.
                # Print each subset on its own indented line so multi-subset
                # runs stay readable without exploding into JSON.
                for subset_name, subset_block in sorted(value.items()):
                    metrics_str = " ".join(
                        f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                        for k, v in sorted(subset_block.items())
                    )
                    self.stdout.write(f"  {key}[{subset_name}]: {metrics_str}")
            else:
                self.stdout.write(f"  {key:<28} {value}")
