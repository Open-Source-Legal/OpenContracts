# OpenContracts Security Assessment

**Date**: 2026-02-28
**Scope**: Full-stack security review covering Django backend, GraphQL API, React frontend auth flow, Celery tasks, REST/WebSocket endpoints, file upload/processing, and infrastructure configuration.

---

## Executive Summary

OpenContracts demonstrates a **mature security architecture** with well-designed permission models, comprehensive rate limiting, and strong file handling. The 7 critical GraphQL mutation vulnerabilities identified in the December 2025 REMEDIATION_GUIDE have all been **verified as fixed**. However, this assessment identifies **3 new vulnerabilities** (1 critical, 2 medium), **several defense-in-depth gaps** in Celery tasks, and **hardening opportunities** in settings and GraphQL configuration.

### Risk Summary

| Severity | Count | Category |
|----------|-------|----------|
| CRITICAL | 1 | Missing `raise` on PermissionError (silent bypass) |
| MEDIUM | 4 | IDOR info-leakage, inconsistent permission patterns |
| LOW | 5 | Hardening opportunities, defense-in-depth |
| INFO | 6 | Best-practice recommendations |

---

## Part 1: Verified Fixed (Previously Critical)

All 7 vulnerabilities from `docs/permissioning/REMEDIATION_GUIDE.md` (2025-12-27) have been confirmed remediated:

| # | Vulnerability | Current Status | Location |
|---|--------------|----------------|----------|
| 1 | `RemoveRelationships` - no permission check | **FIXED** | `annotation_mutations.py:476-492` |
| 2 | `UpdateRelations` - no permission check | **FIXED** | `annotation_mutations.py:680-690` |
| 3 | `StartCorpusFork` - no visibility check | **FIXED** | `corpus_mutations.py:460-479` |
| 4 | `StartQueryForCorpus` - no corpus access check | **FIXED** (mutation removed) | N/A |
| 5 | `StartCorpusExport` - no corpus permission check | **FIXED** | `document_mutations.py:1068-1086` |
| 6 | `StartDocumentExtract` - no document/fieldset check | **FIXED** | `extract_mutations.py:1039-1062` |
| 7 | `DeleteMultipleLabelMutation` - no permission check | **FIXED** | `label_mutations.py:172-191` |

---

## Part 2: New Findings

### 2.1 CRITICAL: DeleteAnalysisMutation - Missing `raise` on PermissionError

**File**: `config/graphql/analysis_mutations.py:198`
**Severity**: CRITICAL
**Impact**: Any authenticated user can delete ANY analysis by ID

The permission check creates a `PermissionError` exception but **does not raise it**:

```python
# Line 192-198 (VULNERABLE):
if not user_has_permission_for_obj(
    user_val=info.context.user,
    instance=analysis,
    permission=PermissionTypes.DELETE,
    include_group_permissions=True,
):
    PermissionError("You don't have permission to delete this analysis.")
    # ^^^ Missing `raise` - execution continues to line 201
```

Line 201 proceeds to delete the analysis via Celery task regardless of the permission check result.

**Fix**: Change line 198 to `raise PermissionError(...)`.

---

### 2.2 MEDIUM: UpdateDocumentSummary - Missing `visible_to_user()` Filter

**File**: `config/graphql/document_mutations.py:307-308`
**Severity**: MEDIUM (IDOR information leakage)

```python
# Lines 307-308 (NO VISIBILITY FILTER):
document = Document.objects.get(pk=doc_pk)
corpus = Corpus.objects.get(pk=corpus_pk)
```

Objects are fetched without `visible_to_user()`. While subsequent permission logic (lines 320-343) does check author/corpus ownership, the initial unfiltered fetch:
- Confirms object existence to unauthorized users via distinct error responses
- May leak information through error timing differences

**Fix**: Use `Document.objects.visible_to_user(user).get(pk=doc_pk)` and `Corpus.objects.visible_to_user(user).get(pk=corpus_pk)` with unified "not found" error handling.

---

### 2.3 MEDIUM: StartDocumentAnalysisMutation - Inconsistent Permission Pattern

**File**: `config/graphql/analysis_mutations.py:113-128`
**Severity**: MEDIUM

Permission check uses a crude creator/public comparison instead of the unified permission system:

```python
# Lines 114-118:
document = Document.objects.get(pk=document_pk)  # No visible_to_user()
if not (document.creator == user or document.is_public):
    raise PermissionError(...)
```

This bypasses django-guardian object-level permissions. A user who has been granted explicit READ permission (but is not the creator) on a private document will be incorrectly denied. Similarly for corpus at lines 124-128.

**Fix**: Use `Document.objects.visible_to_user(user).get(pk=document_pk)` and `user_has_permission_for_obj(user, document, PermissionTypes.READ, include_group_permissions=True)`.

---

### 2.4 MEDIUM: RestoreDeletedDocument / PermanentlyDeleteDocument - Missing Visibility Pre-filter

**Files**:
- `config/graphql/document_mutations.py:1256-1257` (RestoreDeletedDocument)
- `config/graphql/document_mutations.py:1347-1348` (PermanentlyDeleteDocument)

Both mutations fetch objects with `Document.objects.get(pk=doc_pk)` without `visible_to_user()`. While both delegate permission enforcement to `DocumentFolderService` (which does check), the unfiltered initial fetch enables object-existence enumeration through distinct `DoesNotExist` vs permission-denied error paths.

**Fix**: Replace with `visible_to_user()` filter and use unified "Resource not found" errors.

---

### 2.5 MEDIUM: Separate Error Messages Enable IDOR Enumeration

**File**: `config/graphql/document_mutations.py:1363-1366`

```python
except Document.DoesNotExist:
    return PermanentlyDeleteDocument(ok=False, message="Document not found")
except Corpus.DoesNotExist:
    return PermanentlyDeleteDocument(ok=False, message="Corpus not found")
```

Returning distinct messages for "Document not found" vs "Corpus not found" vs permission-denied allows an attacker to enumerate valid document and corpus IDs. Per CLAUDE.md security patterns, these should return an identical message regardless of the failure reason.

---

## Part 3: Defense-in-Depth Gaps

### 3.1 Celery Tasks Lack Permission Validation

Celery tasks accept `user_id` and object IDs but perform no permission checks at the task level. While GraphQL mutations (the entry points) do check permissions before dispatching tasks, this creates a single-layer defense:

| Task | File | Risk |
|------|------|------|
| `ingest_doc` | `tasks/doc_tasks.py:293` | Accepts `user_id` + `doc_id`, no permission check |
| `fork_corpus` | `tasks/fork_tasks.py:30` | Accepts `user_id` + IDs, no permission check |
| `make_corpus_public_task` | `tasks/permissioning_tasks.py:11` | No `user_id` parameter at all |
| `import_analysis` | `tasks/analyzer_tasks.py:28` | No creator ownership validation |

**Risk Level**: LOW in production (tasks are not directly callable by users), but becomes HIGH if:
- An attacker gains access to the Redis/Celery broker
- A future code path dispatches these tasks without GraphQL-layer permission checks
- Internal service-to-service calls bypass the GraphQL layer

**Recommendation**: Add lightweight permission validation at the task entry point as defense-in-depth. This was acknowledged in the REMEDIATION_GUIDE as P2 work.

### 3.2 Analyzer Callback Tokens Stored as Plaintext

**File**: `opencontractserver/analyzer/views.py:101`

Analysis callback tokens are stored in plaintext in the database. While `hmac.compare_digest()` is correctly used for timing-safe comparison, a database breach would expose all tokens.

**Recommendation**: Store hashed callback tokens using Django's password hashing infrastructure. Implement token rotation after successful callback.

---

## Part 4: Configuration & Infrastructure Security

### 4.1 Settings Security Assessment

#### Well-Configured (Production)

| Setting | Value | Status |
|---------|-------|--------|
| `DEBUG` | `False` (env-controlled) | GOOD |
| `SECRET_KEY` | Required from env, no default | GOOD |
| `CSRF_COOKIE_HTTPONLY` | `True` | GOOD |
| `CSRF_COOKIE_SECURE` | `True` (production) | GOOD |
| `CSRF_COOKIE_NAME` | `__Secure-csrftoken` | GOOD |
| `SESSION_COOKIE_HTTPONLY` | `True` | GOOD |
| `SESSION_COOKIE_SECURE` | `True` (production) | GOOD |
| `SESSION_COOKIE_NAME` | `__Secure-sessionid` | GOOD |
| `SECURE_SSL_REDIRECT` | `True` | GOOD |
| `SECURE_HSTS_PRELOAD` | `True` | GOOD |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | GOOD |
| `X_FRAME_OPTIONS` | `DENY` | GOOD |
| `CORS_ALLOW_ALL_ORIGINS` | `False` | GOOD |
| `CORS_ALLOWED_ORIGINS` | Explicit whitelist | GOOD |
| `DATABASE_SSL_MODE` | `require` (default) | GOOD |
| `PASSWORD_HASHERS[0]` | `Argon2PasswordHasher` | GOOD |
| `CELERY_TASK_SERIALIZER` | `json` (not pickle) | GOOD |
| `RATELIMIT_FAIL_OPEN` | `False` | GOOD |

#### Hardening Opportunities

| Setting | Current | Recommended | Severity |
|---------|---------|-------------|----------|
| `SECURE_HSTS_SECONDS` | `518400` (6 days) | `31536000` (1 year) | LOW |
| `SESSION_COOKIE_SAMESITE` | Django default `Lax` | Explicitly set `Lax` or `Strict` | LOW |
| Content-Security-Policy | Not set | Add CSP headers | LOW |
| Referrer-Policy | Not set | `strict-origin-when-cross-origin` | LOW |
| Permissions-Policy | Not set | Restrict camera, microphone, etc. | INFO |

### 4.2 GraphQL Configuration Gaps

| Issue | Details | Severity |
|-------|---------|----------|
| No query depth limiting | Schema has no depth analysis middleware; deeply nested queries could cause DoS | LOW |
| No query complexity analysis | No cost-based query limiting; expensive field resolution unchecked | LOW |
| Introspection enabled in production | Schema exposes full type system to unauthenticated users | LOW |

**Note**: Rate limiting is well-implemented across all mutations (via `@graphql_ratelimit` decorator with user-tier support), which partially mitigates the query complexity concern.

---

## Part 5: Authentication & Authorization Architecture

### 5.1 Strengths

- **Universal `@login_required`** on all mutations (except auth endpoints)
- **Comprehensive rate limiting** with user-tier support (superuser 10x, authenticated 2x, usage-capped 0.5x)
- **Centralized permission utility** (`user_has_permission_for_obj`) as single source of truth
- **`visible_to_user()` manager pattern** across all major models
- **IDOR prevention** with unified error messages in most mutations
- **Guardian object-level permissions** for fine-grained access control
- **MIN(document, corpus) formula** prevents permission escalation through annotation inheritance
- **Structural annotation read-only protection** enforced in `permissioning.py:365-371`
- **WebSocket authentication** with proper JWT validation and error codes
- **Worker token auth** with hashed storage and rate limiting

### 5.2 Frontend Auth Security

- **AuthGate pattern** prevents race conditions on initial page load
- **Auth0 integration** with proper token handling
- **Apollo auth link** injects tokens from reactive variables

**Concerns**:
- Token refresh strategy not documented; long-lived sessions could use expired tokens
- No explicit guidance on token storage mechanism (localStorage is XSS-vulnerable if used)
- JWT access token expiration is 7 days (`JWT_EXPIRATION_DELTA`), which is quite long

---

## Part 6: File Upload & Processing Security

### 6.1 Strengths

- **Magic-byte MIME detection** via `filetype` library (not extension-based)
- **Strict whitelist**: Only `application/pdf`, `.docx`, and `text/plain` allowed
- **Comprehensive zip security** (`opencontractserver/utils/zip_security.py`):
  - Path traversal prevention (rejects `..`, absolute paths, null bytes)
  - Zip bomb protection (100MB/file, 500MB total, 1000 files max, compression ratio monitoring)
  - Symlink attack prevention
  - Folder depth limit (20 levels)
  - 619 lines of dedicated test coverage
- **5GB upload size limit** via `MAX_FILE_UPLOAD_SIZE_BYTES`
- **Permission-checked file serving** for annotation images with rate limiting
- **Hardcoded parser service URLs** (prevents SSRF via user input)

### 6.2 Minor Concerns

- Plaintext detection (`is_plaintext_content()`) samples only 1KB by default - could accept binary if first 1KB is mostly printable (LOW risk - would fail at parsing)
- XXE protection in DOCX processing depends on Docling parser's built-in protections (OUT OF SCOPE - external dependency)

---

## Part 7: Remediation Roadmap

### Immediate (Critical)

| # | Issue | File:Line | Effort |
|---|-------|-----------|--------|
| 1 | Add `raise` to DeleteAnalysisMutation PermissionError | `analysis_mutations.py:198` | 5 min |

### Short-term (Medium - Within 1 Sprint)

| # | Issue | File:Line | Effort |
|---|-------|-----------|--------|
| 2 | Add `visible_to_user()` to UpdateDocumentSummary | `document_mutations.py:307-308` | 30 min |
| 3 | Fix StartDocumentAnalysisMutation permission pattern | `analysis_mutations.py:113-128` | 30 min |
| 4 | Add `visible_to_user()` to RestoreDeletedDocument | `document_mutations.py:1256-1257` | 20 min |
| 5 | Add `visible_to_user()` to PermanentlyDeleteDocument | `document_mutations.py:1347-1348` | 20 min |
| 6 | Unify error messages across document mutations | Multiple locations | 30 min |

### Medium-term (Low - Backlog)

| # | Issue | Effort |
|---|-------|--------|
| 7 | Add Celery task-level permission validation | 4-8 hours |
| 8 | Hash analyzer callback tokens | 2 hours |
| 9 | Increase HSTS to 1 year | 5 min |
| 10 | Add CSP/Referrer-Policy/Permissions-Policy headers | 2 hours |
| 11 | Add GraphQL query depth/complexity limiting | 4 hours |
| 12 | Disable GraphQL introspection in production | 1 hour |

---

## Part 8: Areas Warranting Further Analysis

1. **Auth0 token storage mechanism** - Verify tokens are stored in memory (not localStorage) to mitigate XSS risk
2. **JWT 7-day expiration** - Consider reducing to 1-24 hours with refresh token rotation
3. **Redis broker security** - Verify AUTH is configured and TLS is used in production
4. **Celery result backend TTL** - Configure explicit expiration for task results containing sensitive data
5. **Post-processor path validation in exports** - `StartCorpusExport` accepts `post_processors` as Python paths; verify these are validated against an allowlist
6. **GraphQL subscription security** - If subscriptions are added in future, ensure permission checks on subscription events
7. **`REMEDIATION_GUIDE.md` should be updated** - Reflects pre-fix state from December 2025; should be archived or updated to reflect current status

---

## Methodology

This assessment was conducted through static analysis of:
- Django settings files (`config/settings/base.py`, `local.py`, `production.py`, `test.py`)
- All 19 GraphQL mutation files in `config/graphql/`
- Permission utilities (`opencontractserver/utils/permissioning.py`)
- Model managers (`opencontractserver/shared/Managers.py`)
- Celery task definitions across `opencontractserver/tasks/`
- REST API views and WebSocket consumers
- File upload/processing code and zip security utilities
- Authentication backends and middleware
- Security documentation in `docs/permissioning/` and `docs/frontend/`
- Rate limiting configuration (`config/graphql/ratelimits.py`, `config/settings/ratelimit.py`)
