#!/bin/bash
#
# Integration test runner for CI.
#
# This script:
#   1. Boots the test stack (test.yml) with Django running as a live server
#   2. Runs migrations and creates a superuser
#   3. Executes the integration test suite against the live API
#   4. Tears everything down
#
# Usage:
#   ./scripts/test-integration.sh
#
# Environment variables (all optional):
#   COMPOSE_FILE         Override compose file (default: test.yml)
#   STARTUP_TIMEOUT      Seconds to wait for server health (default: 120)

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-test.yml}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-120}"

echo "============================================="
echo "  Integration Test Runner"
echo "============================================="
echo ""

# -----------------------------------------------------------------------
# 1. Build & start the stack
# -----------------------------------------------------------------------
echo "Building the test stack..."
docker compose -f "$COMPOSE_FILE" build

echo "Starting services in background..."
docker compose -f "$COMPOSE_FILE" up -d

# -----------------------------------------------------------------------
# 2. Wait for postgres to be healthy
# -----------------------------------------------------------------------
echo "Waiting for postgres to be healthy..."
for i in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U oc_user -d opencontractserver >/dev/null 2>&1; then
        echo "Postgres is ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Postgres did not become ready in time."
        docker compose -f "$COMPOSE_FILE" logs postgres
        exit 1
    fi
    sleep 2
done

# -----------------------------------------------------------------------
# 3. Run migrations
# -----------------------------------------------------------------------
echo "Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm django python manage.py migrate --noinput

# -----------------------------------------------------------------------
# 4. Create the superuser (idempotent)
# -----------------------------------------------------------------------
echo "Ensuring superuser exists..."
docker compose -f "$COMPOSE_FILE" run --rm django python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = 'admin'
password = 'Openc0ntracts_def@ult'
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, password=password, email='admin@test.local')
    print(f'Superuser {username!r} created.')
else:
    print(f'Superuser {username!r} already exists.')
"

# -----------------------------------------------------------------------
# 5. Start the Django dev server in the background
# -----------------------------------------------------------------------
echo "Starting Django dev server inside the container..."
docker compose -f "$COMPOSE_FILE" exec -d django python manage.py runserver 0.0.0.0:8000

# -----------------------------------------------------------------------
# 6. Wait for the server to be healthy
# -----------------------------------------------------------------------
echo "Waiting for Django to respond on /api/health/ (timeout: ${STARTUP_TIMEOUT}s)..."
elapsed=0
while [ "$elapsed" -lt "$STARTUP_TIMEOUT" ]; do
    status=$(docker compose -f "$COMPOSE_FILE" exec -T django \
        python -c "
import requests
try:
    r = requests.get('http://localhost:8000/api/health/', timeout=3)
    print(r.status_code)
except Exception:
    print('0')
" 2>/dev/null || echo "0")
    if [ "$status" = "200" ]; then
        echo "Django is healthy."
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ "$elapsed" -ge "$STARTUP_TIMEOUT" ]; then
    echo "ERROR: Django did not become healthy within ${STARTUP_TIMEOUT}s."
    docker compose -f "$COMPOSE_FILE" logs django
    exit 1
fi

# -----------------------------------------------------------------------
# 7. Run the integration tests
# -----------------------------------------------------------------------
echo ""
echo "Running integration tests..."
echo "---------------------------------------------"
docker compose -f "$COMPOSE_FILE" exec -T django \
    python -m pytest opencontractserver/tests/integration/test_api_flows.py \
        -v \
        --tb=short \
        --no-header
test_exit_code=$?

echo "---------------------------------------------"
if [ "$test_exit_code" -eq 0 ]; then
    echo "All integration tests passed."
else
    echo "Integration tests FAILED (exit code: $test_exit_code)."
fi

# -----------------------------------------------------------------------
# 8. Teardown
# -----------------------------------------------------------------------
echo ""
echo "Tearing down the stack..."
docker compose -f "$COMPOSE_FILE" down -v

exit "$test_exit_code"
