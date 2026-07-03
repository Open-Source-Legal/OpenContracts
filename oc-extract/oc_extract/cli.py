"""Minimal CLI: serve the microservice or drive the pipeline offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import DEFAULT_DB_PATH
from .documents import load_path
from .runner import run_extract_sync
from .schema import FieldSet
from .store import Store


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .service import create_app

    uvicorn.run(create_app(args.db), host=args.host, port=args.port)
    return 0


def _cmd_add_docs(args: argparse.Namespace) -> int:
    store = Store(args.db)
    for path in args.paths:
        doc = load_path(path)
        doc_id = store.add_document(
            doc.title, doc.text, page_offsets=doc.page_offsets, meta=doc.meta
        )
        print(f"{doc_id}\t{doc.title}\t{len(doc.text)} chars")
    return 0


def _cmd_add_fieldset(args: argparse.Namespace) -> int:
    store = Store(args.db)
    fieldset = FieldSet.model_validate_json(Path(args.file).read_text())
    fieldset_id = store.create_fieldset(fieldset)
    print(f"fieldset {fieldset_id}: {fieldset.name} ({len(fieldset.fields)} fields)")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    store = Store(args.db)
    doc_ids = (
        [doc["id"] for doc in store.list_documents()]
        if args.documents == ["all"]
        else [int(d) for d in args.documents]
    )
    extract_id = store.create_extract(
        args.name, args.fieldset, doc_ids, model=args.model
    )
    result = run_extract_sync(store, extract_id)
    print(json.dumps(result, indent=2))
    print(json.dumps({"table": store.extract_table(extract_id)}, indent=2))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    store = Store(args.db)
    payload = {
        "extract": store.get_extract(args.extract_id),
        "table": store.extract_table(args.extract_id),
    }
    if args.cells:
        payload["cells"] = store.get_cells(args.extract_id)
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oc-extract",
        description="Structured data extraction with citations, backed by SQLite.",
    )
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the HTTP microservice")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8500)
    p_serve.set_defaults(func=_cmd_serve)

    p_docs = sub.add_parser("add-docs", help="ingest local documents (pdf/txt/md)")
    p_docs.add_argument("paths", nargs="+")
    p_docs.set_defaults(func=_cmd_add_docs)

    p_fs = sub.add_parser("add-fieldset", help="register a fieldset from a JSON file")
    p_fs.add_argument("file")
    p_fs.set_defaults(func=_cmd_add_fieldset)

    p_run = sub.add_parser("run", help="run a fieldset over documents (blocking)")
    p_run.add_argument("--fieldset", type=int, required=True)
    p_run.add_argument(
        "--documents", nargs="+", default=["all"], help="document ids or 'all'"
    )
    p_run.add_argument("--name", default="extract")
    p_run.add_argument("--model", default=None)
    p_run.set_defaults(func=_cmd_run)

    p_show = sub.add_parser("show", help="print a stored extract's results")
    p_show.add_argument("extract_id", type=int)
    p_show.add_argument("--cells", action="store_true", help="include full cells")
    p_show.set_defaults(func=_cmd_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
