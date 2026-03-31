"""Management command to import Legal RAG Bench into OpenContracts.

Downloads the dataset from HuggingFace, creates a corpus with passages
as annotations, and stores Q&A pairs for evaluation.

Usage:
    # Basic setup (uses default embedder)
    python manage.py setup_legal_rag_benchmark --username admin

    # With specific embedder
    python manage.py setup_legal_rag_benchmark --username admin \
        --embedder opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder

    # Skip embedding generation (just import data)
    python manage.py setup_legal_rag_benchmark --username admin --skip-embeddings

    # Dry run (show what would be created)
    python manage.py setup_legal_rag_benchmark --username admin --dry-run
"""

import json
import logging
import re
import time
from collections import defaultdict
from io import BytesIO

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.benchmarks.constants import (
    DEFAULT_BENCHMARK_NAME,
    HF_ROWS_API_MAX_LIMIT,
    LEGAL_RAG_BENCH_CORPUS_URL,
    LEGAL_RAG_BENCH_DATASET,
    LEGAL_RAG_BENCH_QA_URL,
)
from opencontractserver.benchmarks.models import (
    BenchmarkCorpus,
    BenchmarkQuestion,
    BenchmarkStatus,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


def _fetch_hf_rows(base_url: str, max_rows: int | None = None) -> list[dict]:
    """Fetch all rows from a HuggingFace datasets-server endpoint.

    Handles pagination automatically. The datasets-server /rows endpoint
    returns up to 100 rows per request.
    """
    all_rows = []
    offset = 0

    while True:
        url = f"{base_url}&offset={offset}&length={HF_ROWS_API_MAX_LIMIT}"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = response.json()

        rows = data.get("rows", [])
        if not rows:
            break

        all_rows.extend(row["row"] for row in rows)
        offset += len(rows)

        if max_rows and len(all_rows) >= max_rows:
            all_rows = all_rows[:max_rows]
            break

        # Check if we've fetched all available rows
        total = data.get("num_rows_total", 0)
        if total and offset >= total:
            break

    return all_rows


def _extract_chapter_key(passage_id: str) -> str:
    """Extract a chapter grouping key from a passage ID.

    Legal RAG Bench passage IDs follow patterns like '1.1-c1-s1'.
    We group by the first numeric part (e.g., '1.1' → chapter '1').
    """
    match = re.match(r"^(\d+)", passage_id)
    return match.group(1) if match else "misc"


class Command(BaseCommand):
    help = (
        "Import Legal RAG Bench dataset from HuggingFace into an OpenContracts corpus. "
        "Creates documents grouped by chapter, with each passage as an annotation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="Username of the corpus owner",
        )
        parser.add_argument(
            "--embedder",
            default=None,
            help=(
                "Fully qualified embedder path. "
                "Defaults to DEFAULT_EMBEDDER from settings."
            ),
        )
        parser.add_argument(
            "--skip-embeddings",
            action="store_true",
            help="Skip embedding generation (data import only)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without making changes",
        )
        parser.add_argument(
            "--max-passages",
            type=int,
            default=None,
            help="Limit the number of passages to import (for testing)",
        )
        parser.add_argument(
            "--max-questions",
            type=int,
            default=None,
            help="Limit the number of questions to import (for testing)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of annotations to create per batch (default: 50)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing benchmark for this user and re-import",
        )

    def handle(self, *args, **options):
        username = options["username"]
        dry_run = options["dry_run"]
        skip_embeddings = options["skip_embeddings"]
        max_passages = options["max_passages"]
        max_questions = options["max_questions"]
        batch_size = options["batch_size"]
        force = options["force"]
        embedder_path = options["embedder"] or getattr(
            settings, "DEFAULT_EMBEDDER", ""
        )

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist")

        # Check for existing benchmark
        existing = BenchmarkCorpus.objects.filter(
            dataset_source=LEGAL_RAG_BENCH_DATASET, creator=user
        ).first()
        if existing:
            if force:
                self.stdout.write(
                    f"Deleting existing benchmark (ID={existing.pk}) and its corpus..."
                )
                if not dry_run:
                    corpus = existing.corpus
                    existing.delete()
                    corpus.delete()
            else:
                raise CommandError(
                    f"Benchmark already exists for user '{username}' (ID={existing.pk}). "
                    "Use --force to replace it."
                )

        # Step 1: Download corpus passages
        self.stdout.write("Downloading corpus passages from HuggingFace...")
        start = time.time()
        passages = _fetch_hf_rows(LEGAL_RAG_BENCH_CORPUS_URL, max_rows=max_passages)
        self.stdout.write(
            f"  Downloaded {len(passages)} passages in {time.time() - start:.1f}s"
        )

        # Step 2: Download Q&A pairs
        self.stdout.write("Downloading Q&A pairs from HuggingFace...")
        start = time.time()
        qa_pairs = _fetch_hf_rows(LEGAL_RAG_BENCH_QA_URL, max_rows=max_questions)
        self.stdout.write(
            f"  Downloaded {len(qa_pairs)} questions in {time.time() - start:.1f}s"
        )

        if dry_run:
            self._print_dry_run_summary(passages, qa_pairs)
            return

        # Step 3: Create corpus and benchmark tracking objects
        self.stdout.write("Creating corpus and benchmark...")
        benchmark, corpus, label = self._create_corpus_and_benchmark(
            user, embedder_path
        )

        try:
            benchmark.status = BenchmarkStatus.IMPORTING
            benchmark.save(update_fields=["status"])

            # Step 4: Group passages by chapter and create documents + annotations
            self.stdout.write("Creating documents and annotations...")
            passage_id_map = self._create_documents_and_annotations(
                corpus, user, passages, label, batch_size
            )

            benchmark.passage_id_map = passage_id_map
            benchmark.passage_count = len(passage_id_map)
            benchmark.save(update_fields=["passage_id_map", "passage_count"])

            # Step 5: Create benchmark questions
            self.stdout.write("Creating benchmark questions...")
            question_count = self._create_questions(benchmark, qa_pairs, passage_id_map)
            benchmark.question_count = question_count
            benchmark.save(update_fields=["question_count"])

            # Step 6: Generate embeddings (optional)
            if not skip_embeddings:
                self.stdout.write("Generating embeddings...")
                benchmark.status = BenchmarkStatus.EMBEDDING
                benchmark.save(update_fields=["status"])
                self._generate_embeddings(
                    passage_id_map, corpus, embedder_path, batch_size
                )

            benchmark.status = BenchmarkStatus.READY
            benchmark.save(update_fields=["status"])

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nBenchmark setup complete!\n"
                    f"  Benchmark ID: {benchmark.pk}\n"
                    f"  Corpus ID: {corpus.pk}\n"
                    f"  Passages: {benchmark.passage_count}\n"
                    f"  Questions: {benchmark.question_count}\n"
                    f"  Embeddings: {'generated' if not skip_embeddings else 'skipped'}\n"
                    f"\nRun the benchmark with:\n"
                    f"  python manage.py run_legal_rag_benchmark --benchmark-id {benchmark.pk}"
                )
            )

        except Exception as e:
            benchmark.status = BenchmarkStatus.FAILED
            benchmark.error_message = str(e)
            benchmark.save(update_fields=["status", "error_message"])
            raise CommandError(f"Benchmark setup failed: {e}") from e

    def _print_dry_run_summary(self, passages, qa_pairs):
        """Print a summary of what would be created in dry-run mode."""
        # Group passages by chapter
        chapters = defaultdict(list)
        for p in passages:
            chapters[_extract_chapter_key(p["id"])].append(p)

        self.stdout.write(
            self.style.WARNING(
                f"\n[DRY RUN] Would create:\n"
                f"  1 Corpus: '{DEFAULT_BENCHMARK_NAME}'\n"
                f"  {len(chapters)} Documents (one per chapter)\n"
                f"  {len(passages)} Annotations (one per passage)\n"
                f"  {len(qa_pairs)} Benchmark questions\n"
            )
        )

        self.stdout.write("\nChapter breakdown:")
        for chapter_key in sorted(chapters.keys(), key=lambda x: float(x) if x.replace(".", "").isdigit() else float("inf")):
            plist = chapters[chapter_key]
            self.stdout.write(f"  Chapter {chapter_key}: {len(plist)} passages")

        # Show passage ID coverage for questions
        passage_ids = {p["id"] for p in passages}
        covered = sum(1 for q in qa_pairs if q["relevant_passage_id"] in passage_ids)
        self.stdout.write(
            f"\nQ&A coverage: {covered}/{len(qa_pairs)} questions have matching passages"
        )

    @transaction.atomic
    def _create_corpus_and_benchmark(self, user, embedder_path):
        """Create the OpenContracts corpus and BenchmarkCorpus tracking object."""
        corpus = Corpus.objects.create(
            title=DEFAULT_BENCHMARK_NAME,
            description=(
                "Legal RAG Bench: 4,876 passages from the Victorian Criminal Charge Book "
                "with 100 complex legal questions. Source: isaacus/legal-rag-bench"
            ),
            creator=user,
            is_public=False,
            preferred_embedder=embedder_path,
            created_with_embedder=embedder_path,
        )
        set_permissions_for_obj_to_user(
            user, corpus, [PermissionTypes.ALL]
        )

        # Create a label for benchmark passages
        label, _ = AnnotationLabel.objects.get_or_create(
            text="Benchmark Passage",
            label_type="SPAN_LABEL",
            creator=user,
            defaults={
                "color": "#2196F3",
                "description": "A passage from a RAG benchmark dataset",
                "icon": "bookmark",
            },
        )

        benchmark = BenchmarkCorpus.objects.create(
            name=DEFAULT_BENCHMARK_NAME,
            dataset_source=LEGAL_RAG_BENCH_DATASET,
            corpus=corpus,
            creator=user,
        )

        return benchmark, corpus, label

    def _create_documents_and_annotations(
        self, corpus, user, passages, label, batch_size
    ):
        """Create documents grouped by chapter, and annotations for each passage.

        Returns a dict mapping passage IDs to annotation PKs.
        """
        # Group passages by chapter
        chapters = defaultdict(list)
        for passage in passages:
            chapter_key = _extract_chapter_key(passage["id"])
            chapters[chapter_key].append(passage)

        passage_id_map = {}
        total_created = 0

        for chapter_key in sorted(
            chapters.keys(),
            key=lambda x: float(x)
            if x.replace(".", "").isdigit()
            else float("inf"),
        ):
            chapter_passages = chapters[chapter_key]

            # Build full chapter text for the document
            chapter_title = f"Chapter {chapter_key}"
            # Use the first passage's title as a more descriptive chapter name
            if chapter_passages:
                first_title = chapter_passages[0].get("title", "")
                # Extract the chapter-level title (before any sub-section indicator)
                if first_title:
                    chapter_title = first_title.split(" - ")[0].strip()
                    if not chapter_title:
                        chapter_title = f"Chapter {chapter_key}"

            chapter_text = "\n\n---\n\n".join(
                f"## {p.get('title', p['id'])}\n\n{p['text']}"
                + (f"\n\n{p['footnotes']}" if p.get("footnotes") else "")
                for p in chapter_passages
            )

            # Create document
            doc = Document.objects.create(
                title=chapter_title,
                description=f"Legal RAG Bench - {chapter_title} ({len(chapter_passages)} passages)",
                file_type="text/plain",
                creator=user,
                is_public=False,
                processing_started=None,
                backend_lock=False,
            )

            # Store chapter text as txt_extract_file
            doc.txt_extract_file.save(
                f"legal_rag_bench_ch{chapter_key}.txt",
                ContentFile(chapter_text.encode("utf-8")),
                save=True,
            )

            set_permissions_for_obj_to_user(
                user, doc, [PermissionTypes.ALL]
            )

            # Create DocumentPath to link document to corpus
            DocumentPath.objects.create(
                document=doc,
                corpus=corpus,
                path=f"/benchmark/chapter-{chapter_key}",
                version_number=1,
                is_current=True,
                is_deleted=False,
                creator=user,
            )

            # Create annotations in batches
            annotations_to_create = []
            passage_data_for_batch = []

            for passage in chapter_passages:
                text = passage["text"]
                footnotes = passage.get("footnotes", "")
                if footnotes:
                    text = f"{text}\n\n{footnotes}"

                annotation = Annotation(
                    raw_text=text,
                    annotation_label=label,
                    annotation_type="SPAN_LABEL",
                    document=doc,
                    corpus=corpus,
                    page=1,
                    creator=user,
                    is_public=False,
                    structural=False,
                )
                annotations_to_create.append(annotation)
                passage_data_for_batch.append(passage["id"])

                if len(annotations_to_create) >= batch_size:
                    created = Annotation.objects.bulk_create(annotations_to_create)
                    for ann, pid in zip(created, passage_data_for_batch):
                        passage_id_map[pid] = ann.pk
                    total_created += len(created)
                    annotations_to_create = []
                    passage_data_for_batch = []

            # Flush remaining
            if annotations_to_create:
                created = Annotation.objects.bulk_create(annotations_to_create)
                for ann, pid in zip(created, passage_data_for_batch):
                    passage_id_map[pid] = ann.pk
                total_created += len(created)

            self.stdout.write(
                f"  Chapter {chapter_key}: {len(chapter_passages)} passages "
                f"(total: {total_created})"
            )

        return passage_id_map

    def _create_questions(self, benchmark, qa_pairs, passage_id_map):
        """Create BenchmarkQuestion records from Q&A pairs."""
        questions = []
        skipped = 0

        for qa in qa_pairs:
            passage_id = qa["relevant_passage_id"]
            if passage_id not in passage_id_map:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Skipping Q{qa['id']}: passage '{passage_id}' not imported"
                    )
                )
                skipped += 1
                continue

            questions.append(
                BenchmarkQuestion(
                    benchmark=benchmark,
                    external_id=str(qa["id"]),
                    question=qa["question"],
                    expected_answer=qa["answer"],
                    relevant_passage_id=passage_id,
                )
            )

        BenchmarkQuestion.objects.bulk_create(questions)
        if skipped:
            self.stdout.write(
                self.style.WARNING(f"  Skipped {skipped} questions (missing passages)")
            )
        self.stdout.write(f"  Created {len(questions)} questions")
        return len(questions)

    def _generate_embeddings(self, passage_id_map, corpus, embedder_path, batch_size):
        """Generate embeddings for all benchmark annotations.

        Uses the configured embedder to generate vectors synchronously,
        bypassing the Celery task queue for deterministic benchmark setup.
        """
        from opencontractserver.utils.embeddings import generate_embeddings_from_text

        annotation_ids = list(passage_id_map.values())
        annotations = Annotation.objects.filter(pk__in=annotation_ids).only(
            "pk", "raw_text"
        )

        total = len(annotation_ids)
        embedded = 0
        errors = 0

        for annotation in annotations.iterator(chunk_size=batch_size):
            try:
                result_path, vector = generate_embeddings_from_text(
                    annotation.raw_text,
                    corpus_id=corpus.pk,
                )
                if vector is not None:
                    annotation.add_embedding(result_path, vector)
                    embedded += 1
                else:
                    errors += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  No embedding generated for annotation {annotation.pk}"
                        )
                    )
            except Exception as e:
                errors += 1
                logger.warning(
                    "Failed to generate embedding for annotation %d: %s",
                    annotation.pk,
                    e,
                )

            if (embedded + errors) % 100 == 0:
                self.stdout.write(f"  Progress: {embedded + errors}/{total} ({errors} errors)")

        self.stdout.write(f"  Embedded {embedded}/{total} annotations ({errors} errors)")
