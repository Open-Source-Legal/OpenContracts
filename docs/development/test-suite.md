Our test suite provides comprehensive coverage across three levels:

1. **Backend Tests** - Django/pytest tests for models, GraphQL, and business logic
2. **Component Tests** - Playwright tests for isolated React components with mocked GraphQL
3. **E2E Integration Tests** - Full-stack Playwright tests against live backend

All tests are integrated in our GitHub Actions CI pipeline.

NOTE: **Use Python 3.10 or above** as pydantic and certain pre-3.10 type annotations do not play well.

## Running Tests

### Parallel Test Execution (Recommended)

We use pytest-xdist for parallel test execution, which reduces test time from ~65 minutes to ~15-20 minutes:

```bash
# Run tests in parallel with 4 workers
docker compose -f test.yml run --rm django pytest -n 4 --dist loadscope

# Auto-detect workers based on CPU cores
docker compose -f test.yml run --rm django pytest -n auto --dist loadscope

# First run or after schema changes (creates fresh database)
docker compose -f test.yml run --rm django pytest -n 4 --dist loadscope --create-db
```

### Running with Coverage

```bash
# Run parallel tests with coverage
docker compose -f test.yml run --rm django pytest --cov --cov-report=xml -n 4 --dist loadscope

# Generate HTML coverage report
docker compose -f test.yml run --rm django pytest --cov --cov-report=html -n 4 --dist loadscope
```

### Running Specific Tests

```bash
# Run a specific test file
docker compose -f test.yml run --rm django pytest opencontractserver/tests/test_analyzers.py -v

# Run a specific test class
docker compose -f test.yml run --rm django pytest opencontractserver/tests/test_analyzers.py::TestAnalyzerClass -v

# Run a specific test method
docker compose -f test.yml run --rm django pytest opencontractserver/tests/test_analyzers.py::TestAnalyzerClass::test_method -v

# Run tests matching a pattern
docker compose -f test.yml run --rm django pytest -k "analyzer" -v
```

### Serial Test Execution

Some tests cannot run in parallel (websocket tests, async event loop tests). These are marked with `@pytest.mark.serial`:

```bash
# Run only serial tests
docker compose -f test.yml run --rm django pytest -m serial -v

# Run only parallelizable tests
docker compose -f test.yml run --rm django pytest -m "not serial" -n 4 --dist loadscope
```

## Writing Tests for Parallel Execution

When writing new tests, keep these guidelines in mind:

### Tests That Need `@pytest.mark.serial`

Mark tests as serial if they:
- Use `channels.testing.WebsocketCommunicator` (websocket tests)
- Call `agent.run_sync()` or other PydanticAI sync wrappers
- Use Django Channels async consumers
- Have complex async event loop requirements

```python
import pytest

@pytest.mark.serial
class MyWebsocketTestCase(TestCase):
    """Tests that use websocket communicators must run serially."""
    pass
```

### Tests Safe for Parallel Execution

Most tests are safe for parallel execution by default:
- Standard Django TestCase and TransactionTestCase
- GraphQL query/mutation tests
- Model tests
- API tests

The `--dist loadscope` option keeps tests from the same class together, which is important for `setUpClass`/`setUpTestData` patterns.

## Frontend Tests

### Component Tests (Mocked GraphQL)

Component tests use Playwright's component testing feature with mocked GraphQL responses. They test React components in isolation without requiring a running backend.

```bash
cd frontend

# Run all component tests (MUST use --reporter=list to prevent hanging)
yarn test:ct --reporter=list

# Run specific component test
yarn test:ct --reporter=list -g "DocumentCards"

# Run with headed browser for debugging
yarn test:ct --reporter=list --headed
```

**Key patterns:**
- Tests use `MockedProvider` from Apollo Client with predefined GraphQL responses
- Components are mounted via test wrappers that provide Jotai state and Apollo cache
- Located in `frontend/tests/*.ct.tsx`

### E2E Integration Tests (Live Backend)

E2E integration tests run Playwright against the full application stack - real frontend talking to real Django backend with real PostgreSQL database. No mocking.

#### Prerequisites

1. **Backend running:**
   ```bash
   docker compose -f local.yml up
   ```

2. **Test user exists** with known credentials:
   - Default: `admin@example.com` / `admin`
   - Or set via environment variables

3. **Sample PDF** (optional, for upload tests):
   - Place a `sample.pdf` in `frontend/tests/e2e/fixtures/`

#### Running E2E Tests

```bash
cd frontend

# Run all E2E integration tests
yarn test:e2e:integration

# Run with visible browser for debugging
yarn test:e2e:integration --headed

# Run with slow motion (easier to follow)
E2E_SLOW_MO=500 yarn test:e2e:integration --headed

# Run only chromium (faster)
yarn test:e2e:integration --project=chromium
```

#### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_BASE_URL` | `http://localhost:3000` | Frontend URL |
| `E2E_API_URL` | `http://localhost:8000` | Backend API URL |
| `E2E_TEST_USER` | `admin@example.com` | Test user email/username |
| `E2E_TEST_PASSWORD` | `admin` | Test user password |
| `E2E_SLOW_MO` | `0` | Slow down actions (ms) for debugging |

#### Test Structure

```
frontend/tests/e2e/
├── .auth/                    # Stored auth state (gitignored)
├── fixtures/
│   ├── api-client.ts         # GraphQL client for test setup/teardown
│   └── sample.pdf            # Sample PDF for upload tests
├── pages/
│   ├── login.page.ts         # Login page object
│   └── corpus.page.ts        # Corpus page object
├── auth.setup.ts             # Authentication setup (runs first)
├── folder-upload.e2e.ts      # Folder and upload integration tests
├── global-setup.ts           # Verify backend is running
└── global-teardown.ts        # Cleanup
```

#### How It Works

1. **Global setup** verifies the backend is running and healthy
2. **Auth setup** logs in via the UI and saves auth state for reuse
3. **Test fixtures** use the real GraphQL API (not mocks) to create test data
4. **Tests** use Playwright to interact with the real UI
5. **All requests hit the live backend** - no mocking anywhere

The `api-client.ts` is used for efficient test setup/teardown (creating corpora, folders via GraphQL) rather than clicking through the UI for prerequisites.

#### Debugging

```bash
# View test report
npx playwright show-report playwright-report-e2e

# Debug mode
yarn test:e2e:integration --debug

# View trace for failed tests
npx playwright show-trace test-results/*/trace.zip
```

## Production Stack Testing

We have a dedicated test setup for validating the production Docker Compose stack, including Traefik rate limiting configuration with proper 429 response handling.

### Prerequisites

Before running production tests, you need to generate self-signed certificates for local TLS testing:

```bash
# Generate certificates (only needed once)
./contrib/generate-certs.sh
```

This creates certificates for `localhost`, `opencontracts.opensource.legal`, and other testing domains.

### Testing Rate Limiting with Production Stack

To test the production stack with rate limiting:

1. **Start the production test stack:**
   ```bash
   # Start all services (nlm-ingestor has been removed for faster startup)
   docker compose -f production.yml -f compose/test-production.yml up -d

   # Wait for services to be ready (Django takes 1-2 minutes)
   docker compose -f production.yml -f compose/test-production.yml ps
   ```

2. **Run the production rate limiting test:**
   ```bash
   # Run comprehensive rate limiting test with detailed logging
   ./scripts/test-production-rate-limiting.sh --compose-files "production.yml compose/test-production.yml"
   ```

3. **What the test validates:**
   - ✅ **TLS Configuration** - Self-signed certificates for HTTPS testing
   - ✅ **Service Connectivity** - Traefik properly routes to backend services
   - ✅ **Rate Limiting Enforcement** - Returns 429 responses when limits exceeded
   - ✅ **Frontend Limits** - 10 req/sec average, 20 burst limit
   - ✅ **API Limits** - 5 req/sec average, 10 burst limit (stricter)
   - ✅ **Detailed Logging** - Request-by-request response code logging
   - ✅ **GitHub Actions Ready** - External testing compatible with CI/CD

4. **Example test output:**
   ```
   🧪 Production Rate Limiting Test
   =============================================
   Environment: Production stack with local TLS

   === 1. Environment Check ===
   ✅ HTTPS endpoint accessible (HTTP 404)

   === 2. Frontend Rate Limiting Test ===
   Sending requests to frontend (https://localhost/):
   ✅ Request 1: 200 (Success)
   ✅ Request 2: 200 (Success)
   ...
   🚫 Request 9: 429 (RATE LIMITED)
   🚫 Request 10: 429 (RATE LIMITED)

   🎉 SUCCESS: Rate limiting is functional!
   ✅ Production environment successfully returns 429 responses
   ```

5. **Debugging and monitoring:**
   ```bash
   # Check container status
   docker compose -f production.yml -f compose/test-production.yml ps

   # View Traefik configuration logs
   docker compose -f production.yml -f compose/test-production.yml logs traefik | grep -i rate

   # Access Traefik dashboard (if available)
   curl -s http://localhost:8080/api/rawdata | jq '.middlewares'

   # Check certificate generation
   ls -la contrib/certs/
   ```

6. **Clean up:**
   ```bash
   # Stop and remove containers
   docker compose -f production.yml -f compose/test-production.yml down -v
   ```

### Configuration Details

The production test environment uses:

- **Self-signed TLS certificates** - Avoids Let's Encrypt in testing environments
- **File-based Traefik configuration** - `compose/production/traefik/working-rate-test.yml`
- **Local certificate generation** - `contrib/generate-certs.sh` for testing
- **External HTTP testing** - Compatible with GitHub Actions and CI environments
- **Removed nlm-ingestor** - Eliminated 1.21GB Docker image for faster testing
- **Detailed request logging** - Shows each HTTP response code for debugging

**Rate Limiting Configuration:**
- **Frontend**: 10 requests/second average, 20 request burst limit
- **API**: 5 requests/second average, 10 request burst limit
- **IP-based limiting**: Per-client source IP with depth=1 strategy
- **Period**: 1-second rate limiting windows
- **Response**: HTTP 429 "Too Many Requests" when exceeded

This test setup is used in GitHub Actions CI pipeline to validate that rate limiting properly returns 429 responses in production-like environments.
