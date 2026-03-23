Our test suite provides comprehensive coverage of the backend. Frontend tests use Playwright for component testing. All tests are integrated in our GitHub Actions CI pipeline.

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

## Testing Async and Agentic Code

Django's async ORM has a critical limitation when combined with `asyncio.run()` that causes database connection corruption. Understanding this is essential for writing reliable tests for agent tasks.

### The Core Problem

When `asyncio.run()` is called (as in Celery task wrappers that invoke async functions):

1. `asyncio.run()` creates its own event loop in a **different thread context**
2. Django's database connections are **thread-bound**
3. When `asyncio.run()` closes its event loop, connections get corrupted
4. Subsequent tests fail with "connection already closed" or "terminating connection due to administrator command" errors

Reference: [Django Ticket #32409](https://code.djangoproject.com/ticket/32409)

### Pattern 1: Testing Agent Implementations Directly

Use this pattern when testing the actual async agent code (chat methods, streaming, vector search).

**Example from `test_pydantic_ai_agents.py`:**

```python
import pytest
from django.test import TransactionTestCase, override_settings

@pytest.mark.serial
@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})
class TestPydanticAIAgents(TransactionTestCase):
    """Tests for PydanticAI agent implementations.

    Uses TransactionTestCase because async test methods with Django ORM calls
    don't work well with TestCase's transaction-based isolation. The async code
    runs in a different thread context that can't share the test transaction.

    Marked as serial because PydanticAI's run_sync() requires an active event loop,
    which pytest-xdist workers may close between test batches.
    """

    def setUp(self):
        # Use setUp, not setUpTestData - TransactionTestCase doesn't support it
        self.user = User.objects.create_user(username="testuser", password="testpass")
        # ... create test fixtures

    @patch("opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent")
    async def test_agent_chat(self, mock_agent_cls):
        """Test agent chat functionality."""
        mock_llm = MagicMock()
        mock_llm.run = AsyncMock(return_value=MockResult("Response"))
        mock_agent_cls.return_value = mock_llm

        # Test async code directly
        response = await agent.chat("Hello")
        self.assertIn("Response", response.content)
```

**Key characteristics:**
- `TransactionTestCase` — async code can't share `TestCase`'s transaction
- `@pytest.mark.serial` — runs sequentially, avoids xdist worker conflicts
- `@override_settings(DATABASES={"default": {"CONN_MAX_AGE": 0}})` — prevents connection pooling issues
- Mock at the **agent class level** (e.g., `PydanticAIAgent`) or use `TestModel()` for in-memory tests
- Use `AsyncMock` for async methods
- Run async tests natively (pytest-asyncio)

### Pattern 2: Testing Celery Task Wrappers

Use this pattern when testing Celery tasks that call `asyncio.run()` internally.

**Example from `test_agent_corpus_action_task.py`:**

```python
from unittest.mock import patch
from django.test import TestCase

# Path to patch the async function - mock the ENTIRE async function
ASYNC_FUNC_PATH = "opencontractserver.tasks.agent_tasks._run_agent_corpus_action_async"

class TestRunAgentCorpusActionTask(TestCase):
    """Tests for run_agent_corpus_action Celery task.

    These tests mock _run_agent_corpus_action_async to avoid async ORM connection
    issues, and verify the task wrapper correctly handles various scenarios.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        # ... create test fixtures

    @patch(ASYNC_FUNC_PATH)
    def test_successful_execution(self, mock_async_func):
        """Test that successful execution creates expected result."""
        # Create the result that the async function would create
        action_result = AgentActionResult.objects.create(
            corpus_action=self.corpus_action,
            document=self.document,
            status=AgentActionResult.Status.COMPLETED,
            agent_response="Test response",
            creator=self.user,
        )

        # Mock returns what the real async function would return
        mock_async_func.return_value = {
            "status": "completed",
            "result_id": action_result.id,
            "conversation_id": None,
        }

        result = run_agent_corpus_action.apply(
            args=[self.corpus_action.id, self.document.id, self.user.id]
        )

        self.assertEqual(result.result["status"], "completed")
        mock_async_func.assert_called_once()
```

**Key characteristics:**
- Regular `TestCase` (faster, no serial marker needed)
- **Mock the entire async function** — `asyncio.run()` never runs real Django async ORM
- Tests task wrapper behavior (error handling, argument passing, status tracking)
- If a test needs to update DB in the mock, use `sync_to_async`:

```python
from asgiref.sync import sync_to_async

@patch(ASYNC_FUNC_PATH)
def test_retry_failed_result(self, mock_async_func):
    """Test that failed results can be retried."""
    existing_result = AgentActionResult.objects.create(
        status=AgentActionResult.Status.FAILED,
        # ...
    )

    # Simulate the async function updating the result
    async def update_and_return(*args, **kwargs):
        existing_result.status = AgentActionResult.Status.COMPLETED
        existing_result.agent_response = "Retry successful"
        await sync_to_async(existing_result.save)()
        return {
            "status": "completed",
            "result_id": existing_result.id,
            "conversation_id": None,
        }

    mock_async_func.side_effect = update_and_return

    result = run_agent_corpus_action.apply(args=[...])
    self.assertEqual(result.result["status"], "completed")
```

### Decision Tree: Which Pattern to Use

| What you're testing | Pattern | Base Class | Markers |
|---------------------|---------|------------|---------|
| Celery task that calls `asyncio.run()` | Mock entire async function | `TestCase` | None |
| Agent implementation (async methods) | Mock agent internals | `TransactionTestCase` | `@pytest.mark.serial` |
| PydanticAI with `run_sync()` | Mock or use `TestModel()` | `TransactionTestCase` | `@pytest.mark.serial` |
| WebSocket consumers | Test async consumers | `TransactionTestCase` | `@pytest.mark.serial` |

### Common Mistakes

**Wrong: Mocking at the wrong level**
```python
# BROKEN - still runs real async ORM inside _run_agent_corpus_action_async
@patch("opencontractserver.llms.agents")
def test_task(self, mock_agents_module):
    mock_agents_module.for_document = AsyncMock(return_value=mock_agent)
    # The Celery task still calls asyncio.run() with real Django async ORM
```

**Right: Mock the entire async function**
```python
# WORKING - asyncio.run() calls mock, no real async ORM executes
@patch("opencontractserver.tasks.agent_tasks._run_agent_corpus_action_async")
def test_task(self, mock_async_func):
    mock_async_func.return_value = {"status": "completed", ...}
```

### Infrastructure Support

The `conftest.py` provides infrastructure to help with async tests:

1. **Fresh event loops** — Creates new event loop for each test if the current one is closed
2. **Connection cleanup** — Closes all database connections after `@pytest.mark.serial` tests to prevent corruption from leaking

## Production Stack Testing

We have a dedicated test setup for validating the production Docker Compose stack, including Traefik rate limiting configuration with proper 429 response handling.

### Prerequisites

Before running production tests, you need to generate self-signed certificates for local TLS testing:

```bash
# Generate certificates (only needed once)
./contrib/generate-certs.sh
```

This creates certificates for `localhost`, `contracts.opensource.legal`, and other testing domains.

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
