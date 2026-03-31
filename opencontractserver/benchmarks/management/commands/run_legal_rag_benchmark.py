"""Management command to evaluate OpenContracts' RAG against Legal RAG Bench.

Runs retrieval evaluation (and optionally LLM-based answer evaluation) against
a previously imported Legal RAG Bench benchmark corpus.

Usage:
    # Retrieval-only evaluation
    python manage.py run_legal_rag_benchmark --benchmark-id 1

    # Full RAG evaluation with LLM judge
    python manage.py run_legal_rag_benchmark --benchmark-id 1 \
        --llm-model gpt-4o --judge-model gpt-4o

    # Custom top-k
    python manage.py run_legal_rag_benchmark --benchmark-id 1 --top-k 10

    # Output detailed results to JSONL
    python manage.py run_legal_rag_benchmark --benchmark-id 1 --output results.jsonl
"""

import json
import logging
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from opencontractserver.benchmarks.constants import (
    DEFAULT_TOP_K,
    JUDGE_PROMPT,
    RAG_PROMPT,
)
from opencontractserver.benchmarks.models import (
    BenchmarkCorpus,
    BenchmarkQuestion,
    BenchmarkQuestionResult,
    BenchmarkRun,
    BenchmarkStatus,
)
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
    VectorSearchQuery,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def _build_reverse_passage_map(passage_id_map: dict) -> dict[int, str]:
    """Build annotation_pk → passage_id reverse mapping."""
    return {v: k for k, v in passage_id_map.items()}


class Command(BaseCommand):
    help = (
        "Run Legal RAG Bench evaluation against an OpenContracts corpus. "
        "Measures retrieval accuracy (Recall@k, MRR) and optionally "
        "generation quality via LLM judge."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--benchmark-id",
            type=int,
            required=True,
            help="ID of the BenchmarkCorpus to evaluate",
        )
        parser.add_argument(
            "--top-k",
            type=int,
            default=DEFAULT_TOP_K,
            help=f"Number of passages to retrieve per query (default: {DEFAULT_TOP_K})",
        )
        parser.add_argument(
            "--llm-model",
            default="",
            help="LLM model for answer generation (e.g., 'gpt-4o'). If empty, retrieval-only eval.",
        )
        parser.add_argument(
            "--judge-model",
            default="",
            help="LLM model for judging answers. Defaults to --llm-model if set.",
        )
        parser.add_argument(
            "--output",
            default="",
            help="Path to write detailed JSONL results file",
        )
        parser.add_argument(
            "--question-ids",
            nargs="*",
            help="Specific question external IDs to evaluate (default: all)",
        )

    def handle(self, *args, **options):
        benchmark_id = options["benchmark_id"]
        top_k = options["top_k"]
        llm_model = options["llm_model"]
        judge_model = options["judge_model"] or llm_model
        output_path = options["output"]
        question_ids = options.get("question_ids")

        try:
            benchmark = BenchmarkCorpus.objects.get(pk=benchmark_id)
        except BenchmarkCorpus.DoesNotExist:
            raise CommandError(f"BenchmarkCorpus with ID {benchmark_id} does not exist")

        if benchmark.status != BenchmarkStatus.READY:
            raise CommandError(
                f"Benchmark is not ready (status: {benchmark.status}). "
                "Run setup_legal_rag_benchmark first."
            )

        # Create benchmark run record
        run = BenchmarkRun.objects.create(
            benchmark=benchmark,
            embedder_path=benchmark.corpus.preferred_embedder or "",
            llm_model=llm_model,
            top_k=top_k,
            status=BenchmarkStatus.RUNNING,
            started=timezone.now(),
            creator=benchmark.creator,
        )

        try:
            # Get questions to evaluate
            questions = benchmark.questions.all()
            if question_ids:
                questions = questions.filter(external_id__in=question_ids)

            question_list = list(questions)
            total = len(question_list)
            self.stdout.write(f"Evaluating {total} questions with top_k={top_k}...")

            # Build reverse map: annotation_pk → passage_id
            reverse_map = _build_reverse_passage_map(benchmark.passage_id_map)

            # Initialize vector store
            vector_store = CoreAnnotationVectorStore(
                user_id=benchmark.creator.pk,
                corpus_id=benchmark.corpus.pk,
                embedder_path=benchmark.corpus.preferred_embedder,
            )

            # LLM client setup (if generation eval enabled)
            llm_client = None
            judge_client = None
            if llm_model:
                llm_client = self._get_llm_client(llm_model)
            if judge_model and llm_model:
                judge_client = self._get_llm_client(judge_model)

            # Run evaluation
            results = []
            retrieval_hits = 0
            mrr_sum = 0.0
            correct_count = 0
            grounded_count = 0
            generation_count = 0

            for i, question in enumerate(question_list):
                result = self._evaluate_question(
                    question=question,
                    vector_store=vector_store,
                    reverse_map=reverse_map,
                    top_k=top_k,
                    llm_client=llm_client,
                    judge_client=judge_client,
                    run=run,
                )
                results.append(result)

                # Aggregate metrics
                if result.relevant_passage_retrieved:
                    retrieval_hits += 1
                if result.relevant_passage_rank is not None:
                    mrr_sum += 1.0 / result.relevant_passage_rank
                if result.judge_correct is True:
                    correct_count += 1
                if result.judge_grounded is True:
                    grounded_count += 1
                if result.generated_answer:
                    generation_count += 1

                if (i + 1) % 10 == 0:
                    recall = retrieval_hits / (i + 1)
                    mrr = mrr_sum / (i + 1)
                    self.stdout.write(
                        f"  Progress: {i + 1}/{total} "
                        f"(Recall@{top_k}: {recall:.3f}, MRR: {mrr:.3f})"
                    )

            # Save results
            BenchmarkQuestionResult.objects.bulk_create(results)

            # Compute and save aggregate metrics
            run.retrieval_recall_at_k = retrieval_hits / total if total else 0
            run.retrieval_mrr = mrr_sum / total if total else 0
            if generation_count:
                run.answer_correctness = correct_count / generation_count
                run.answer_groundedness = grounded_count / generation_count
            run.status = BenchmarkStatus.COMPLETED
            run.finished = timezone.now()

            if output_path:
                self._write_results_jsonl(output_path, results, question_list, reverse_map)
                run.results_file = output_path

            run.save()

            # Print summary
            self._print_summary(run, total, generation_count)

        except Exception as e:
            run.status = BenchmarkStatus.FAILED
            run.error_message = str(e)
            run.finished = timezone.now()
            run.save()
            raise CommandError(f"Benchmark run failed: {e}") from e

    def _evaluate_question(
        self,
        question: BenchmarkQuestion,
        vector_store: CoreAnnotationVectorStore,
        reverse_map: dict[int, str],
        top_k: int,
        llm_client,
        judge_client,
        run: BenchmarkRun,
    ) -> BenchmarkQuestionResult:
        """Evaluate a single benchmark question."""
        expected_passage_id = question.relevant_passage_id
        expected_annotation_pk = question.benchmark.passage_id_map.get(
            expected_passage_id
        )

        # Retrieval
        retrieval_start = time.time()
        search_query = VectorSearchQuery(
            query_text=question.question,
            similarity_top_k=top_k,
        )
        search_results = vector_store.search(search_query)
        retrieval_time_ms = int((time.time() - retrieval_start) * 1000)

        # Map results back to passage IDs
        retrieved_passage_ids = []
        similarity_scores = []
        relevant_rank = None

        for rank, result in enumerate(search_results, 1):
            ann_pk = result.annotation.pk
            passage_id = reverse_map.get(ann_pk, f"unknown-{ann_pk}")
            retrieved_passage_ids.append(passage_id)
            similarity_scores.append(round(result.similarity_score, 4))

            if ann_pk == expected_annotation_pk:
                relevant_rank = rank

        # Generation (if LLM configured)
        generated_answer = ""
        judge_correct = None
        judge_grounded = None
        judge_reasoning = ""
        generation_time_ms = None

        if llm_client:
            context = self._format_context(search_results)
            gen_start = time.time()
            generated_answer = self._generate_answer(
                llm_client, question.question, context
            )
            generation_time_ms = int((time.time() - gen_start) * 1000)

            if judge_client:
                judge_result = self._judge_answer(
                    judge_client,
                    question.expected_answer,
                    generated_answer,
                    context,
                )
                judge_correct = judge_result.get("correct")
                judge_grounded = judge_result.get("grounded")
                judge_reasoning = judge_result.get("reasoning", "")

        return BenchmarkQuestionResult(
            run=run,
            question=question,
            relevant_passage_retrieved=relevant_rank is not None,
            relevant_passage_rank=relevant_rank,
            retrieved_passage_ids=retrieved_passage_ids,
            similarity_scores=similarity_scores,
            generated_answer=generated_answer,
            judge_correct=judge_correct,
            judge_grounded=judge_grounded,
            judge_reasoning=judge_reasoning,
            retrieval_time_ms=retrieval_time_ms,
            generation_time_ms=generation_time_ms,
        )

    def _format_context(self, search_results) -> str:
        """Format search results into a context string for the LLM."""
        passages = []
        for i, result in enumerate(search_results, 1):
            text = result.annotation.raw_text
            score = result.similarity_score
            passages.append(f"[Passage {i} (score: {score:.3f})]\n{text}")
        return "\n\n".join(passages)

    def _get_llm_client(self, model_name: str):
        """Get an LLM client for the specified model.

        Currently supports OpenAI-compatible APIs. The client is returned
        as a dict with the model name and client instance for flexibility.
        """
        try:
            import openai

            client = openai.OpenAI()
            return {"client": client, "model": model_name}
        except ImportError:
            raise CommandError(
                "openai package is required for LLM evaluation. "
                "Install it with: pip install openai"
            )

    def _generate_answer(self, llm_client, question: str, context: str) -> str:
        """Generate an answer using the configured LLM."""
        prompt = RAG_PROMPT.format(context=context, question=question)
        try:
            response = llm_client["client"].chat.completions.create(
                model=llm_client["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1024,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.warning("LLM generation failed for question: %s", e)
            return f"[Generation error: {e}]"

    def _judge_answer(
        self, judge_client, expected_answer: str, generated_answer: str, context: str
    ) -> dict:
        """Use a judge LLM to evaluate the generated answer."""
        prompt = JUDGE_PROMPT.format(
            expected_answer=expected_answer,
            generated_answer=generated_answer,
            context=context,
        )
        try:
            response = judge_client["client"].chat.completions.create(
                model=judge_client["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=512,
            )
            content = response.choices[0].message.content or "{}"
            # Strip markdown code fences if present
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0]
            return json.loads(content)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Judge evaluation failed: %s", e)
            return {"correct": None, "grounded": None, "reasoning": f"Error: {e}"}

    def _write_results_jsonl(
        self, output_path, results, questions, reverse_map
    ):
        """Write detailed results to a JSONL file."""
        question_map = {q.pk: q for q in questions}

        with open(output_path, "w") as f:
            for result in results:
                question = question_map.get(result.question_id, result.question)
                entry = {
                    "question_id": question.external_id,
                    "question": question.question,
                    "expected_answer": question.expected_answer,
                    "relevant_passage_id": question.relevant_passage_id,
                    "retrieved_passage_ids": result.retrieved_passage_ids,
                    "similarity_scores": result.similarity_scores,
                    "relevant_passage_retrieved": result.relevant_passage_retrieved,
                    "relevant_passage_rank": result.relevant_passage_rank,
                    "retrieval_time_ms": result.retrieval_time_ms,
                }
                if result.generated_answer:
                    entry["generated_answer"] = result.generated_answer
                    entry["judge_verdict"] = {
                        "correct": result.judge_correct,
                        "grounded": result.judge_grounded,
                        "reasoning": result.judge_reasoning,
                    }
                    entry["generation_time_ms"] = result.generation_time_ms
                f.write(json.dumps(entry) + "\n")

        self.stdout.write(f"Results written to {output_path}")

    def _print_summary(self, run: BenchmarkRun, total: int, generation_count: int):
        """Print a formatted summary of the benchmark run."""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'=' * 60}\n"
                f"BENCHMARK RESULTS (Run ID: {run.pk})\n"
                f"{'=' * 60}\n"
                f"  Embedder: {run.embedder_path}\n"
                f"  Top-K: {run.top_k}\n"
                f"  Questions: {total}\n"
                f"\n  RETRIEVAL METRICS:\n"
                f"    Recall@{run.top_k}: {run.retrieval_recall_at_k:.4f}\n"
                f"    MRR:       {run.retrieval_mrr:.4f}\n"
            )
        )

        if generation_count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n  GENERATION METRICS (LLM: {run.llm_model}):\n"
                    f"    Correctness: {run.answer_correctness:.4f}\n"
                    f"    Groundedness: {run.answer_groundedness:.4f}\n"
                )
            )

        if run.results_file:
            self.stdout.write(f"\n  Detailed results: {run.results_file}")
