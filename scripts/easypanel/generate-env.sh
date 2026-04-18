#!/usr/bin/env bash
# =============================================================================
# scripts/easypanel/generate-env.sh
#
# Bootstrap helper for an EasyPanel "Compose" deploy of OpenContracts
# (Option A in docs/deployment/easypanel.md).
#
# What it does:
#   1. Reads the templates under .envs.example/.production/.
#   2. Generates strong random secrets for every <REPLACE-ME-*-random> /
#      <REPLACE-ME-*-password> placeholder.
#   3. Asks (or accepts via env vars / flags) for the few values it can't
#      guess: domain, ACME email, OpenAI key, superuser password.
#   4. Writes the filled files to .envs/.production/ (gitignored).
#   5. Prints a summary so you can paste credentials into a vault.
#
# Usage:
#   ./scripts/easypanel/generate-env.sh \
#       --domain oc.example.com \
#       --email you@example.com \
#       --openai-key sk-...
#
# All flags are optional — the script will prompt for anything missing.
# Re-run safely: existing .envs/.production/* are NEVER overwritten unless
# you pass --force.
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="${REPO_ROOT}/.envs.example/.production"
DST_DIR="${REPO_ROOT}/.envs/.production"

DOMAIN=""
EMAIL=""
OPENAI_KEY=""
SUPERUSER_PASSWORD=""
FORCE=0

usage() {
    sed -n '2,/^# =\{20,\}$/p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email) EMAIL="$2"; shift 2 ;;
        --openai-key) OPENAI_KEY="$2"; shift 2 ;;
        --superuser-password) SUPERUSER_PASSWORD="$2"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

prompt() {
    local var_name="$1"
    local message="$2"
    local secret="${3:-0}"
    local current="${!var_name}"
    if [[ -n "$current" ]]; then return; fi
    if [[ "$secret" == "1" ]]; then
        read -r -s -p "$message: " value; echo
    else
        read -r -p "$message: " value
    fi
    if [[ -z "$value" ]]; then
        echo "Empty value for $var_name; aborting." >&2; exit 2
    fi
    printf -v "$var_name" '%s' "$value"
}

if [[ ! -d "$SRC_DIR" ]]; then
    echo "Templates not found at $SRC_DIR" >&2; exit 1
fi

prompt DOMAIN "Public domain (e.g. oc.example.com)"
prompt EMAIL "Contact / Let's Encrypt email"
prompt OPENAI_KEY "OpenAI API key (sk-...)" 1
prompt SUPERUSER_PASSWORD "Initial Django superuser password" 1

# --- secret generation ----------------------------------------------------
# Use Python to keep this portable across BSD/GNU grep variants.
gen() { python3 -c "import secrets;print(secrets.token_urlsafe($1))"; }
gen_admin_slug() { python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(30)))"; }

DJANGO_SECRET_KEY="$(gen 64)"
DJANGO_ADMIN_SLUG="$(gen_admin_slug)"
FLOWER_USER="$(gen 16)"
FLOWER_PASSWORD="$(gen 32)"
VECTOR_EMBEDDER_API_KEY="$(gen 24)"
POSTGRES_PASSWORD="$(gen 32)"

mkdir -p "$DST_DIR"

write_or_skip() {
    local src="$1" dst="$2"
    if [[ -e "$dst" && "$FORCE" -ne 1 ]]; then
        echo "SKIP  $dst (already exists; use --force to overwrite)"
        return
    fi
    cp "$src" "$dst"
    echo "WROTE $dst"
}

write_or_skip "$SRC_DIR/.django"   "$DST_DIR/.django"
write_or_skip "$SRC_DIR/.postgres" "$DST_DIR/.postgres"
write_or_skip "$SRC_DIR/.frontend" "$DST_DIR/.frontend"

# --- substitution --------------------------------------------------------
# Use Python for cross-platform sed semantics.
substitute() {
    local file="$1" pattern="$2" value="$3"
    python3 - "$file" "$pattern" "$value" <<'PY'
import sys, pathlib
path, pat, val = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
if pat not in text:
    sys.exit(0)  # already substituted
p.write_text(text.replace(pat, val))
PY
}

# .django substitutions — every placeholder is unique so order is irrelevant.
DJANGO="$DST_DIR/.django"
substitute "$DJANGO" "<REPLACE-ME-64-char-random>"          "$DJANGO_SECRET_KEY"
substitute "$DJANGO" "<REPLACE-ME-30-char-random>"          "$DJANGO_ADMIN_SLUG"
substitute "$DJANGO" "<REPLACE-ME-domain>"                  "$DOMAIN"
substitute "$DJANGO" "<REPLACE-ME-email>"                   "$EMAIL"
substitute "$DJANGO" "<REPLACE-ME-superuser-password>"      "$SUPERUSER_PASSWORD"
substitute "$DJANGO" "<REPLACE-ME-flower-user>"             "$FLOWER_USER"
substitute "$DJANGO" "<REPLACE-ME-flower-password>"         "$FLOWER_PASSWORD"
substitute "$DJANGO" "<REPLACE-ME-openai-key>"              "$OPENAI_KEY"
substitute "$DJANGO" "<REPLACE-ME-vector-embedder-key>"     "$VECTOR_EMBEDDER_API_KEY"

# .postgres substitutions (POSTGRES_PASSWORD appears twice; replace both)
PG="$DST_DIR/.postgres"
python3 - "$PG" "$POSTGRES_PASSWORD" <<'PY'
import sys, pathlib
path, val = sys.argv[1], sys.argv[2]
p = pathlib.Path(path)
text = p.read_text()
text = text.replace("<REPLACE-ME-strong-password>", val)
text = text.replace("<REPLACE-ME-same-strong-password>", val)
p.write_text(text)
PY

# .frontend substitutions
FE="$DST_DIR/.frontend"
substitute "$FE" "<REPLACE-ME-domain>" "$DOMAIN"

echo
echo "=== Done. Generated env files in $DST_DIR ==="
echo
echo "Save these credentials in a password manager:"
echo "  Domain:               $DOMAIN"
echo "  Admin URL:            https://$DOMAIN/admin/$DJANGO_ADMIN_SLUG/"
echo "  Superuser:            admin / (the password you provided)"
echo "  Flower user:          $FLOWER_USER"
echo "  Flower password:      $FLOWER_PASSWORD"
echo "  Postgres password:    $POSTGRES_PASSWORD"
echo
echo "Next steps:"
echo "  1. ./scripts/easypanel/configure-traefik.sh --domain $DOMAIN --email $EMAIL"
echo "  2. Commit nothing in .envs/.production/ — it is gitignored."
echo "  3. In EasyPanel: deploy this repo with production.yml, then run:"
echo "       docker compose -f production.yml --profile migrate up migrate"
