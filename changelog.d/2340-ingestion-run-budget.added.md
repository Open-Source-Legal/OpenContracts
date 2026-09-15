- Remote ingestion supports immutable run policies, conservative monetary
  reservations, provider usage accounting, and resumable budget pauses. Worker
  API and CLI controls expose queued and uncertain costs. Prepared-only runs
  suppress server providers; server embedding runs require an explicitly priced
  OpenAI adapter and reject configuration drift or fallback. Budgeted vectors
  retain the shared embedding identity for readiness checks. Cross-corpus copies
  preserve the source run, and an explicit adapter version allows resume after
  cosmetic deployments (#2340).
