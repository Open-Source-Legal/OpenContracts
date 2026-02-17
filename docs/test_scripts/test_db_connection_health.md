# Test: Database Connection Health After Deployment

## Purpose
Verify that production database connection settings (CONN_HEALTH_CHECKS, TCP keepalives, Celery worker_process_init cleanup) are working correctly and reducing connection churn.

## Prerequisites
- Access to the production or staging Kubernetes cluster
- `kubectl` configured for the target namespace
- PostgreSQL superuser access (for `pg_stat_activity` queries)

## Steps

### 1. Verify Django connection settings are active

```bash
kubectl exec -it $DJANGO_POD -n opencontracts-prod -- python manage.py shell -c "
from django.conf import settings
db = settings.DATABASES['default']
print(f\"CONN_MAX_AGE: {db.get('CONN_MAX_AGE')}\")
print(f\"CONN_HEALTH_CHECKS: {db.get('CONN_HEALTH_CHECKS')}\")
print(f\"OPTIONS: {db.get('OPTIONS')}\")
"
```

**Expected**: `CONN_MAX_AGE=60`, `CONN_HEALTH_CHECKS=True`, OPTIONS includes `keepalives=1`, `keepalives_idle=30`, `keepalives_interval=5`, `keepalives_count=5`.

### 2. Check current connection count from PostgreSQL

```sql
-- Total connections by application
SELECT application_name, state, count(*)
FROM pg_stat_activity
WHERE datname = 'opencontracts'
GROUP BY application_name, state
ORDER BY count DESC;
```

### 3. Monitor TIME_WAIT connections on a Django pod

```bash
kubectl exec -it $DJANGO_POD -n opencontracts-prod -- \
  bash -c "ss -tn state time-wait | grep ':5432' | wc -l"
```

**Expected**: Significantly fewer TIME_WAIT connections than before deployment (was ~74).

### 4. Verify Celery worker connection cleanup after fork

```bash
kubectl exec -it $CELERY_POD -n opencontracts-prod -- \
  bash -c "ss -tn state established | grep ':5432' | wc -l"
```

**Expected**: Connection count roughly matches number of active Celery worker child processes (not accumulated from previous forks).

### 5. Monitor connection stability over 5 minutes

```bash
# Run on the Django pod every 30 seconds for 5 minutes
for i in $(seq 1 10); do
  echo "=== $(date) ==="
  ss -tn state established | grep ':5432' | wc -l
  ss -tn state time-wait | grep ':5432' | wc -l
  sleep 30
done
```

**Expected**: ESTABLISHED count is stable (not climbing). TIME_WAIT count stays low.

## Expected Results
- ESTABLISHED connection count per pod is stable and proportional to concurrency
- TIME_WAIT count is significantly reduced (target: <10, was ~74)
- No `connection already closed` errors in Django or Celery logs
- `pg_stat_activity` total across all pods stays well under Cloud SQL `max_connections`

## Cleanup
No cleanup needed. These are observational tests.
