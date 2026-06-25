#!/bin/bash
# Entrypoint for the remote-ingest worker container.
#
# Prepends the fixed in-container paths (ledger + mounted PDF root) to every
# invocation, so the user only types the subcommand + tuning flags, e.g.:
#
#   docker compose -f remote_worker.yml run --rm worker plan
#   docker compose -f remote_worker.yml run --rm worker run --max-workers 8
#   docker compose -f remote_worker.yml run --rm worker verify
#   docker compose -f remote_worker.yml run --rm worker status
#
# Target URL + token come from the environment (OC_TARGET_URL / OC_WORKER_TOKEN).
set -o errexit
set -o nounset

exec python /app/scripts/remote_ingest/oc_remote_ingest.py \
    --ledger /ledger/ledger.sqlite3 \
    --root-dir /data \
    "$@"
