"""Adapter for the LegalBench-RAG dataset (Pipitone & Alami, 2024).

Dataset: https://github.com/zeroentropy-ai/legalbenchrag
Paper:   https://arxiv.org/abs/2408.10343

On-disk layout (as documented in the authors' ``benchmark_types.py``)::

    <root>/
      corpus/
        contractnli/<file>.txt
        cuad/<file>.txt
        maud/<file>.txt
        privacy_qa/<file>.txt
      benchmarks/
        contractnli.json
        cuad.json
        maud.json
        privacy_qa.json

Each ``benchmarks/<subset>.json`` deserialises to::

    {"tests": [{"query": str, "snippets": [{"file_path": str,
                                              "span": [int, int]}], "tags": [str]}]}

``Snippet.file_path`` is resolved relative to ``corpus/``; ``span`` is a
half-open ``[start, end)`` character range into the referenced file.  The
gold answer is the concatenation of the text slices, which is what the
reference implementation's ``Snippet.answer`` computed field also returns.
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from opencontractserver.benchmarks.adapters.base import (
    BaseBenchmarkAdapter,
    BenchmarkDocument,
    BenchmarkTask,
)

logger = logging.getLogger(__name__)

#: The four official subsets, listed in the order the reference weights them.
LEGALBENCH_RAG_SUBSETS: tuple[str, ...] = (
    "contractnli",
    "cuad",
    "maud",
    "privacy_qa",
)

#: Upstream ``legalbenchrag/benchmark.py`` caps each subset at this many
#: tasks (constant value 194 verified verbatim from upstream master).
PAPER_MAX_TESTS_PER_BENCHMARK: int = 194


def _paper_sample_tests(
    tests: list[dict[str, Any]],
    max_per_subset: int = PAPER_MAX_TESTS_PER_BENCHMARK,
) -> list[dict[str, Any]]:
    """Reproduce upstream ``benchmark.py``'s SORT_BY_DOCUMENT=True selection.

    Upstream code (verbatim from ``legalbenchrag/benchmark.py:46-58``)::

        tests = sorted(
            tests,
            key=lambda test: (
                random.seed(test.snippets[0].file_path),
                random.random(),
            )[1],
        )
        tests = tests[:MAX_TESTS_PER_BENCHMARK]

    The seeding uses each test's first snippet's ``file_path`` as a
    deterministic per-test random key, then sorts by the resulting
    pseudo-random float and truncates to the cap. This is NOT a
    uniform shuffle — tests sharing a file_path get correlated keys —
    but it is the published selection rule.

    Tests that lack ``snippets`` or whose first snippet lacks a
    ``file_path`` are dropped before sorting (they would crash the
    upstream code too).
    """
    if len(tests) <= max_per_subset:
        return tests

    valid: list[dict[str, Any]] = []
    for test in tests:
        snippets = test.get("snippets") or []
        if not snippets:
            continue
        first = snippets[0]
        if not isinstance(first, dict) or not first.get("file_path"):
            continue
        valid.append(test)

    # Precompute sort keys with an isolated ``random.Random`` instance
    # so we don't mutate the process-wide random state on every sort
    # comparison.  Upstream code seeds the global PRNG inside the sort
    # key; we get the same per-test deterministic value without the
    # global side effect.
    def _seed_value(file_path: str) -> float:
        rng = random.Random()
        rng.seed(file_path)
        return rng.random()

    keys = {id(test): _seed_value(test["snippets"][0]["file_path"]) for test in valid}
    valid.sort(key=lambda test: keys[id(test)])
    return valid[:max_per_subset]


class LegalBenchRAGAdapter(BaseBenchmarkAdapter):
    """Load LegalBench-RAG test cases from a local dataset directory.

    Args:
        root: Path to the dataset root.  The directory must contain
            ``corpus/`` and ``benchmarks/`` children.  Both the unzipped
            ZeroEntropy release layout and the tiny micro fixture shipped
            with this repo conform to that shape.
        subsets: Restrict to a subset of the four LegalBench-RAG subsets.
            ``None`` loads whichever subset JSON files exist under
            ``benchmarks/`` — this is what you want for the micro fixture
            because it only ships one synthetic subset.
        limit: Optional cap on the total number of tasks yielded across all
            subsets.  Intended for smoke testing.
    """

    name = "legalbench-rag"

    def __init__(
        self,
        root: Path | str,
        *,
        subsets: Iterable[str] | None = None,
        limit: int | None = None,
        paper_sampling: bool = True,
        max_per_subset: int = PAPER_MAX_TESTS_PER_BENCHMARK,
    ) -> None:
        """
        Args (additions):
            paper_sampling: When True (the default), reproduce upstream
                ``legalbenchrag/benchmark.py``'s SORT_BY_DOCUMENT=True
                sampling — sort by ``random(seed=test.snippets[0].file_path)``
                then keep the first ``max_per_subset`` tests. This is the
                exact selection rule the paper's published numbers were
                computed against. Set to False to load every task in
                JSON file order (legacy behaviour, useful for fixtures
                with hand-curated test counts).
            max_per_subset: Per-subset cap when ``paper_sampling`` is on.
                Defaults to upstream's ``MAX_TESTS_PER_BENCHMARK = 194``.
        """
        self.root = Path(root).expanduser().resolve()
        self.corpus_dir = self.root / "corpus"
        self.benchmarks_dir = self.root / "benchmarks"
        if not self.corpus_dir.is_dir():
            raise FileNotFoundError(
                f"LegalBench-RAG corpus directory not found at {self.corpus_dir}"
            )
        if not self.benchmarks_dir.is_dir():
            raise FileNotFoundError(
                f"LegalBench-RAG benchmarks directory not found at "
                f"{self.benchmarks_dir}"
            )

        requested = tuple(subsets) if subsets is not None else None
        if requested is not None:
            unknown = [s for s in requested if s not in LEGALBENCH_RAG_SUBSETS]
            if unknown:
                raise ValueError(
                    f"Unknown LegalBench-RAG subset(s) {unknown!r}; "
                    f"valid subsets are {LEGALBENCH_RAG_SUBSETS!r}"
                )

        self.requested_subsets = requested
        self.limit = limit
        self.paper_sampling = paper_sampling
        self.max_per_subset = max_per_subset

        self._documents: dict[str, BenchmarkDocument] = {}
        self._tasks: list[BenchmarkTask] = []
        self._loaded = False
        self._subset_names: list[str] = []

    # ------------------------------------------------------------------ #
    # Adapter protocol
    # ------------------------------------------------------------------ #

    def iter_documents(self) -> Iterable[BenchmarkDocument]:
        self._ensure_loaded()
        return list(self._documents.values())

    def iter_tasks(self) -> Iterable[BenchmarkTask]:
        self._ensure_loaded()
        return list(self._tasks)

    def describe(self) -> dict[str, Any]:
        # Use cached subset names if loaded; otherwise discover from disk.
        subsets = (
            list(self._subset_names)
            if self._loaded
            else list(self._discover_subset_files().keys())
        )
        return {
            "adapter": self.name,
            "root": str(self.root),
            "subsets": subsets,
            "requested_subsets": (
                list(self.requested_subsets) if self.requested_subsets else None
            ),
            "limit": self.limit,
            "paper_sampling": self.paper_sampling,
            "max_per_subset": self.max_per_subset,
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _discover_subset_files(self) -> dict[str, Path]:
        """Return ``{subset_name: path_to_json}`` for present benchmark files."""
        available = {}
        for json_path in sorted(self.benchmarks_dir.glob("*.json")):
            subset_name = json_path.stem
            if (
                self.requested_subsets is not None
                and subset_name not in self.requested_subsets
            ):
                continue
            available[subset_name] = json_path
        return available

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        subset_files = self._discover_subset_files()
        if not subset_files:
            raise FileNotFoundError(
                f"No benchmark JSON files found under {self.benchmarks_dir}"
            )

        task_counter = 0
        for subset_name, json_path in subset_files.items():
            with json_path.open(encoding="utf-8") as fh:
                payload = json.load(fh)

            tests = payload.get("tests", [])
            if self.paper_sampling:
                pre_count = len(tests)
                tests = _paper_sample_tests(tests, max_per_subset=self.max_per_subset)
                logger.info(
                    "LegalBench-RAG paper-faithful sampling for subset %s: "
                    "%d -> %d tasks (sorted by random(seed=file_path), cap=%d)",
                    subset_name,
                    pre_count,
                    len(tests),
                    self.max_per_subset,
                )
            for test_index, test in enumerate(tests):
                if self.limit is not None and task_counter >= self.limit:
                    break

                query = test.get("query", "").strip()
                raw_snippets = test.get("snippets", []) or []
                tags = tuple(test.get("tags", []) or [])

                if not query or not raw_snippets:
                    logger.warning(
                        "Skipping LegalBench-RAG test %s/%s with empty "
                        "query or snippets",
                        subset_name,
                        test_index,
                    )
                    continue

                spans_by_doc: dict[str, list[tuple[int, int]]] = {}
                answer_parts: list[str] = []
                document_keys: list[str] = []

                for snippet in raw_snippets:
                    file_path = snippet.get("file_path", "")
                    span = snippet.get("span")
                    if not file_path or span is None or len(span) != 2:
                        logger.warning(
                            "Skipping malformed snippet in %s test %s: %r",
                            subset_name,
                            test_index,
                            snippet,
                        )
                        continue

                    start, end = int(span[0]), int(span[1])
                    if end < start:
                        logger.warning(
                            "Snippet span has end < start in %s test %s: %r",
                            subset_name,
                            test_index,
                            snippet,
                        )
                        continue

                    document_key = file_path
                    if document_key not in self._documents:
                        self._load_document(document_key)

                    document = self._documents[document_key]
                    # Clamp out-of-bounds gold spans defensively but emit a
                    # warning so bad benchmark rows are visible in the logs.
                    # We deliberately do NOT skip the snippet — dropping a
                    # gold span mid-stream would change evaluation semantics
                    # (fewer gold spans => easier recall), so preserve the
                    # original behavior while surfacing the condition.
                    doc_len = len(document.text)
                    orig_start, orig_end = start, end
                    start = max(0, min(start, doc_len))
                    end = max(start, min(end, doc_len))
                    if (orig_start, orig_end) != (start, end):
                        logger.warning(
                            "Gold span [%d, %d] out of bounds for document "
                            "length %d in %s test %s (%s); clamped to [%d, %d]",
                            orig_start,
                            orig_end,
                            doc_len,
                            subset_name,
                            test_index,
                            file_path,
                            start,
                            end,
                        )

                    spans_by_doc.setdefault(document_key, []).append((start, end))
                    answer_parts.append(document.text[start:end])
                    if document_key not in document_keys:
                        document_keys.append(document_key)

                if not spans_by_doc:
                    continue

                task = BenchmarkTask(
                    task_id=f"{subset_name}::{test_index:04d}",
                    query=query,
                    document_keys=tuple(document_keys),
                    gold_spans={
                        key: tuple(values) for key, values in spans_by_doc.items()
                    },
                    gold_answer="\n".join(answer_parts),
                    output_type="str",
                    extract_is_list=False,
                    tags=tags + (subset_name,),
                )
                self._tasks.append(task)
                task_counter += 1

            if self.limit is not None and task_counter >= self.limit:
                break

        self._subset_names = list(subset_files.keys())
        self._loaded = True
        logger.info(
            "LegalBench-RAG adapter loaded %d documents and %d tasks "
            "from %s (subsets: %s)",
            len(self._documents),
            len(self._tasks),
            self.root,
            ", ".join(self._subset_names),
        )

    def _load_document(self, file_path: str) -> None:
        """Read a corpus file and cache it as a :class:`BenchmarkDocument`.

        If the resolved path escapes the corpus directory (path traversal)
        or the file is missing, we log a warning and leave the document out
        of ``self._documents`` so callers can skip tasks that reference it.
        """
        absolute = (self.corpus_dir / file_path).resolve()
        try:
            absolute.relative_to(self.corpus_dir)
        except ValueError:
            logger.warning(
                "Skipping corpus file outside of corpus dir (path traversal): %s",
                file_path,
            )
            return

        if not absolute.is_file():
            logger.warning(
                "Corpus file referenced by benchmark but not on disk: %s", absolute
            )
            return

        text = absolute.read_text(encoding="utf-8")
        title = absolute.name
        self._documents[file_path] = BenchmarkDocument(
            document_key=file_path,
            title=title,
            text=text,
            metadata={"source_path": str(absolute)},
        )
