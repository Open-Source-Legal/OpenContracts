#!/usr/bin/env bash
set -euo pipefail

# Reads shared PostgreSQL settings from a config file and appends them as
# -c flags to the postgres command, then delegates to the real entrypoint.
# This ensures shared values are defined in one place (shared.conf) rather
# than duplicated across local.yml, production.yml, and test.yml.

SHARED_CONF="/etc/postgresql-custom/shared.conf"
EXTRA_ARGS=()

if [ -f "$SHARED_CONF" ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Trim leading/trailing whitespace
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"

        # Skip blank lines, comments, and malformed lines (no = sign)
        [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue

        key="${line%%=*}"
        value="${line#*=}"

        # Trim whitespace around key and value
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"

        [[ -z "$key" ]] && continue

        EXTRA_ARGS+=("-c" "$key=$value")
    done < "$SHARED_CONF"
fi

# Pass the command (e.g. "postgres") first so docker-entrypoint.sh recognises
# it as $1, then shared defaults, then per-environment args (postgres uses
# last-wins for -c flags, so per-environment settings correctly override
# shared defaults).
CMD="$1"
shift
exec /usr/local/bin/docker-entrypoint.sh "$CMD" "${EXTRA_ARGS[@]}" "$@"
