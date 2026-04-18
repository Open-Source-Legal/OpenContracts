#!/usr/bin/env bash
# =============================================================================
# scripts/easypanel/configure-traefik.sh
#
# Patch compose/production/traefik/traefik.yml in-place to use your domain
# and Let's Encrypt contact email. The bundled Traefik config ships with
# the OpenContracts upstream domain — you must replace it before the
# first production deploy.
#
# Usage:
#   ./scripts/easypanel/configure-traefik.sh \
#       --domain oc.example.com \
#       --email you@example.com
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TRAEFIK="${REPO_ROOT}/compose/production/traefik/traefik.yml"

DOMAIN=""
EMAIL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email) EMAIL="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^# =\{20,\}$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$DOMAIN" ]]; then read -r -p "Public domain: " DOMAIN; fi
if [[ -z "$EMAIL" ]]; then read -r -p "ACME email:   " EMAIL; fi

if [[ ! -f "$TRAEFIK" ]]; then
    echo "Traefik config not found at $TRAEFIK" >&2; exit 1
fi

cp "$TRAEFIK" "$TRAEFIK.bak"
echo "Backup written to $TRAEFIK.bak"

python3 - "$TRAEFIK" "$DOMAIN" "$EMAIL" <<'PY'
import sys, pathlib, re
path, domain, email = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()

# ACME email
text = re.sub(
    r'email:\s*"[^"]*"',
    f'email: "{email}"',
    text,
    count=1,
)

# Replace both legacy hostnames everywhere (router rules, etc.)
text = text.replace("contracts.opensource.legal", domain)
text = text.replace(f"www.{domain}", f"www.{domain}")  # no-op safety

p.write_text(text)
PY

echo "Updated $TRAEFIK with:"
echo "  domain: $DOMAIN"
echo "  email:  $EMAIL"
echo
echo "Re-deploy the traefik service for the changes to take effect:"
echo "  docker compose -f production.yml build traefik && docker compose -f production.yml up -d traefik"
