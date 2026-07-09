"""Management command: measure heavy-RAG vs RAG + agentic traversal.

Runs the SAME corpus questions under two agent tool configurations and reports
tokens / tool-call counts / latency / authority-grounding side by side. See
``opencontractserver/benchmarks/traversal_benchmark.py`` for the rationale.

Usage::

    docker compose -f local.yml run django python manage.py benchmark_traversal \\
        --questions opencontractserver/benchmarks/fixtures/traversal_questions.yaml \\
        --user admin \\
        --model openai:gpt-4o-mini \\
        --run-dir /tmp/traversal_run
"""

from __future__ import annotations

import argparse
import asyncio

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.benchmarks.traversal_benchmark import (
    load_questions,
    render_markdown,
    run_benchmark_traversal,
    summarize,
    write_report,
)


class Command(BaseCommand):
    help = (
        "Compare 'heavy RAG' (similarity_search only) vs 'RAG + traversal' "
        "(similarity_search + graph-navigation tools) over a set of corpus "
        "questions, reporting tokens, tool calls, latency and grounding."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--questions",
            required=True,
            help="Path to the YAML/JSON question set (see fixtures/).",
        )
        parser.add_argument(
            "--user",
            required=True,
            help="Username the agents run as (scopes visibility).",
        )
        parser.add_argument(
            "--model",
            default=None,
            help="LLM identifier (defaults to the corpus / settings default).",
        )
        parser.add_argument(
            "--run-dir",
            default=None,
            help="Directory to write report.md / report.json. Skipped if omitted.",
        )

    def handle(self, *args, **options) -> None:
        username = options["user"]
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User {username!r} not found") from exc

        questions = load_questions(options["questions"])
        if not questions:
            raise CommandError("No questions loaded.")

        self.stdout.write(
            self.style.NOTICE(
                f"Running traversal benchmark: {len(questions)} question(s) as "
                f"{user.username} (2 configs each)…"
            )
        )

        results = asyncio.run(
            run_benchmark_traversal(
                questions, user_id=user.id, model=options.get("model")
            )
        )

        self.stdout.write(render_markdown(results))

        summary = summarize(results)
        for config, block in summary.items():
            self.stdout.write(self.style.SUCCESS(f"{config}: {block}"))

        run_dir = options.get("run_dir")
        if run_dir:
            out = write_report(results, run_dir)
            self.stdout.write(f"Report written to {out}")
