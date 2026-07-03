"""Extract orchestration: fan a fieldset out over documents.

Standalone analogue of
``opencontractserver/tasks/extract_orchestrator_tasks.py::run_extract`` —
asyncio replaces the Celery chord: one cell per (document x field), processed
concurrently under a semaphore, with the extract marked finished when every
cell has settled.
"""

from __future__ import annotations

import asyncio
import logging

from .constants import DEFAULT_CONCURRENCY, NONE_RESULT_ERROR
from .engine import ExtractionEngine
from .store import Store

logger = logging.getLogger(__name__)


async def run_extract(
    store: Store,
    extract_id: int,
    *,
    engine: ExtractionEngine | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict:
    """Run every (document x field) cell of *extract_id* and persist results.

    Returns the finished extract record (with cell counts).
    """
    extract = store.get_extract(extract_id)

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def process(cell_id: int, doc_id: int, field_row: dict) -> None:
        # The whole cell lifecycle sits inside one try so a failure in ANY
        # step (including mark_cell_started) is contained to this cell and
        # recorded on it — asyncio.gather never sees an exception, so sibling
        # cells can't be orphaned mid-write by an early gather raise.
        async with semaphore:
            try:
                store.mark_cell_started(cell_id)
                document = store.get_document(doc_id)
                outcome = await engine.extract_cell(
                    document, Store.field_spec(field_row)
                )
            except Exception as exc:  # noqa: BLE001 - cell isolation barrier
                logger.exception("cell %s crashed", cell_id)
                store.mark_cell_failed(
                    cell_id, failure_mode=NONE_RESULT_ERROR, stacktrace=str(exc)
                )
                return
            if outcome.status == "completed":
                store.mark_cell_completed(
                    cell_id,
                    outcome.value,
                    outcome.sources,
                    failure_mode=outcome.failure_mode,
                    llm_log=outcome.llm_log,
                )
            else:
                store.mark_cell_failed(
                    cell_id,
                    failure_mode=outcome.failure_mode or NONE_RESULT_ERROR,
                    stacktrace=outcome.error or "unknown failure",
                    llm_log=outcome.llm_log,
                )

    # Everything after this point must end in mark_extract_finished — a
    # setup failure (engine construction, cell creation) that escaped the
    # try would otherwise leave a permanent zombie extract: started set,
    # finished/error forever NULL, and no running task.
    store.mark_extract_started(extract_id)
    try:
        fieldset = store.get_fieldset(extract["fieldset_id"])
        if engine is None:
            engine = ExtractionEngine(model=extract.get("model"))

        cells: list[tuple[int, int, dict]] = []  # (cell_id, doc_id, field_row)
        for doc_id in extract["document_ids"]:
            for field_row in fieldset["fields"]:
                cell_id = store.create_cell(
                    extract_id, field_row["id"], doc_id, field_row["output_type"]
                )
                cells.append((cell_id, doc_id, field_row))

        await asyncio.gather(*(process(*cell) for cell in cells))
        store.mark_extract_finished(extract_id)
    except Exception as exc:  # noqa: BLE001 - record run-level failure
        logger.exception("extract %s crashed", extract_id)
        store.mark_extract_finished(extract_id, error=str(exc))
    return store.get_extract(extract_id)


def run_extract_sync(store: Store, extract_id: int, **kwargs) -> dict:
    """Blocking convenience wrapper around :func:`run_extract`."""
    return asyncio.run(run_extract(store, extract_id, **kwargs))
