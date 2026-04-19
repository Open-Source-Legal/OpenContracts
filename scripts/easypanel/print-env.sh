#!/usr/bin/env bash
# =============================================================================
# scripts/easypanel/print-env.sh
#
# Generates every random secret the EasyPanel-native deploy needs
# (easypanel.yml) and prints them in the format EasyPanel's "Environment"
# section expects. Copy the output, paste it into the EasyPanel app's
# Environment tab, then fill in DOMAIN / ADMIN_EMAIL / ADMIN_PASSWORD /
# OPENAI_API_KEY manually (those can't be auto-generated).
#
# Usage:
#   ./scripts/easypanel/print-env.sh
#
# Or pre-fill the user-provided values:
#   ./scripts/easypanel/print-env.sh \
#       --domain oc.example.com \
#       --email you@example.com \
#       --openai-key sk-... \
#       --admin-password 'StrongPass!'
# =============================================================================

set -euo pipefail

DOMAIN="${DOMAIN:-<REPLACE-ME>}"
EMAIL="${ADMIN_EMAIL:-<REPLACE-ME>}"
OPENAI_KEY="${OPENAI_API_KEY:-<REPLACE-ME>}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-<REPLACE-ME>}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email) EMAIL="$2"; shift 2 ;;
        --openai-key) OPENAI_KEY="$2"; shift 2 ;;
        --admin-password) ADMIN_PASSWORD="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^# =\{20,\}$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

gen() { python3 -c "import secrets;print(secrets.token_urlsafe($1))"; }
gen_slug() { python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range($1)))"; }

cat <<EOF
# --- paste into EasyPanel → App → Environment ---
DOMAIN=$DOMAIN
ADMIN_EMAIL=$EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
OPENAI_API_KEY=$OPENAI_KEY
OPENAI_MODEL=gpt-4o

DJANGO_SECRET_KEY=$(gen 64)
DJANGO_ADMIN_URL_SLUG=$(gen_slug 30)
POSTGRES_PASSWORD=$(gen 32)
CELERY_FLOWER_USER=$(gen_slug 16)
CELERY_FLOWER_PASSWORD=$(gen 32)
VECTOR_EMBEDDER_API_KEY=$(gen 24)

# Optional (safe defaults apply if omitted):
BOLIVIAN_LAWS_SCRAPER_USER_AGENT=OpenContractsBolivianLawsBot/1.0 (+contact:$EMAIL)
# BOLIVIAN_LAWS_SCRAPE_LOOKBACK_DAYS=30
# BOLIVIAN_LAWS_REQUEST_DELAY_SECONDS=1.0
# STORAGE_BACKEND=LOCAL
# USE_AUTH0=false
EOF
