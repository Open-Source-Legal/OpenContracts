#!/usr/bin/env bash
# =============================================================================
# scripts/easypanel/deploy.sh
#
# One-command production deploy. Runs on the EasyPanel host (or any Docker
# host). Asks four questions, generates every secret, patches Traefik,
# brings the stack up, runs migrations, and seeds the Bolivian-laws
# scrape so you can test immediately.
#
# Usage:
#   ./scripts/easypanel/deploy.sh
#
# Or fully non-interactive:
#   ./scripts/easypanel/deploy.sh \
#       --domain oc.example.com \
#       --email you@example.com \
#       --openai-key sk-... \
#       --admin-password 'StrongPass!'
#
# Re-runs are safe: env files are kept, Traefik is re-patched idempotently,
# Compose just brings any missing services up.
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
OPENAI_KEY="${OPENAI_KEY:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
SKIP_SCRAPE_TEST=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email) EMAIL="$2"; shift 2 ;;
        --openai-key) OPENAI_KEY="$2"; shift 2 ;;
        --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
        --skip-scrape-test) SKIP_SCRAPE_TEST=1; shift ;;
        -h|--help)
            sed -n '2,/^# =\{20,\}$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

# --- prompts (only ask for what wasn't passed) ---------------------------
if [[ -z "$DOMAIN" ]]; then read -r -p "Public domain (e.g. oc.example.com): " DOMAIN; fi
if [[ -z "$EMAIL" ]]; then read -r -p "Contact / Let's Encrypt email: " EMAIL; fi
if [[ -z "$OPENAI_KEY" ]]; then read -r -s -p "OpenAI API key (sk-...): " OPENAI_KEY; echo; fi
if [[ -z "$ADMIN_PASSWORD" ]]; then read -r -s -p "Initial admin password: " ADMIN_PASSWORD; echo; fi

for var in DOMAIN EMAIL OPENAI_KEY ADMIN_PASSWORD; do
    if [[ -z "${!var}" ]]; then
        echo "Missing $var; aborting." >&2; exit 2
    fi
done

# --- step 1: env files ---------------------------------------------------
echo
echo "[1/4] Generating .envs/.production/* with strong random secrets..."
"$REPO_ROOT/scripts/easypanel/generate-env.sh" \
    --domain "$DOMAIN" \
    --email "$EMAIL" \
    --openai-key "$OPENAI_KEY" \
    --superuser-password "$ADMIN_PASSWORD"

# --- step 2: Traefik config ----------------------------------------------
echo
echo "[2/4] Patching Traefik with your domain + ACME email..."
"$REPO_ROOT/scripts/easypanel/configure-traefik.sh" \
    --domain "$DOMAIN" \
    --email "$EMAIL"

# --- step 3: bring up + migrate -----------------------------------------
echo
echo "[3/4] Building images and starting the stack (this can take a while)..."
docker compose -f production.yml build
docker compose -f production.yml --profile migrate up migrate
docker compose -f production.yml up -d

# --- step 4: smoke-test the Bolivian-laws scrape ------------------------
if [[ "$SKIP_SCRAPE_TEST" -eq 1 ]]; then
    echo
    echo "[4/4] Skipping scrape smoke test (--skip-scrape-test)."
else
    echo
    echo "[4/4] Smoke-testing the Bolivian-laws scrape (--max-entries 3 per source)..."
    docker compose -f production.yml exec -T django \
        python manage.py scrape_bolivian_laws --all --since-days 7 --max-entries 3 --sync \
        || echo "  (scrape returned non-zero — sites may be unreachable; check logs)"
fi

echo
echo "================================================================"
echo "Deploy complete."
echo
echo "  App:    https://$DOMAIN"
echo "  Admin:  https://$DOMAIN/$(grep DJANGO_ADMIN_URL .envs/.production/.django | cut -d= -f2)"
echo "  Flower: https://$DOMAIN:5555"
echo
echo "Useful follow-ups:"
echo "  - tail logs:   docker compose -f production.yml logs -f django celeryworker celerybeat"
echo "  - re-deploy:   git pull && docker compose -f production.yml up -d --build"
echo "  - migrations:  docker compose -f production.yml --profile migrate up migrate"
echo "================================================================"
