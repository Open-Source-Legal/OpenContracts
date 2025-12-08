# E2E Integration Tests

Full-stack end-to-end integration tests that exercise the complete OpenContracts application - frontend UI, GraphQL API, and Django backend working together.

## Overview

These tests differ from component tests (`*.ct.tsx`) in that they:

1. **Run against a live backend** - Real Django + PostgreSQL, not mocked GraphQL
2. **Test complete user flows** - Login, create corpus, upload documents, etc.
3. **Verify real data persistence** - Documents actually upload and appear in folders
4. **Test cross-system integration** - Frontend ↔ GraphQL ↔ Django ↔ Database

## Prerequisites

1. **Backend running**:

   ```bash
   docker compose -f local.yml up
   ```

2. **Test user exists** with known credentials:

   - Default: `admin@example.com` / `admin`
   - Or set via environment variables (see below)

3. **Sample PDF** (optional, for upload tests):
   - Place a `sample.pdf` in `tests/e2e/fixtures/`
   - Upload tests will skip if not present

## Running Tests

```bash
cd frontend

# Run all E2E integration tests
yarn test:e2e:integration

# Run specific test file
yarn test:e2e:integration tests/e2e/folder-upload.e2e.ts

# Run with headed browser (for debugging)
yarn test:e2e:integration --headed

# Run with slow motion (easier to follow)
E2E_SLOW_MO=500 yarn test:e2e:integration --headed

# Run only chromium (faster)
yarn test:e2e:integration --project=chromium
```

## Environment Variables

| Variable            | Default                 | Description                          |
| ------------------- | ----------------------- | ------------------------------------ |
| `E2E_BASE_URL`      | `http://localhost:3000` | Frontend URL                         |
| `E2E_API_URL`       | `http://localhost:8000` | Backend API URL                      |
| `E2E_TEST_USER`     | `admin@example.com`     | Test user email/username             |
| `E2E_TEST_PASSWORD` | `admin`                 | Test user password                   |
| `E2E_SLOW_MO`       | `0`                     | Slow down actions (ms) for debugging |

## Test Structure

```
tests/e2e/
├── .auth/                    # Stored auth state (gitignored)
├── fixtures/
│   ├── api-client.ts         # GraphQL API client for setup/teardown
│   ├── sample.pdf            # Sample PDF for upload tests
│   └── .gitkeep
├── pages/
│   ├── login.page.ts         # Login page object
│   └── corpus.page.ts        # Corpus page object
├── auth.setup.ts             # Authentication setup (runs first)
├── folder-upload.e2e.ts      # Folder and upload tests
├── global-setup.ts           # Global test setup
├── global-teardown.ts        # Global test cleanup
└── README.md                 # This file
```

## Writing New Tests

### 1. Use Page Objects

Page objects encapsulate page-specific selectors and actions:

```typescript
import { CorpusPage } from "./pages/corpus.page";

test("my test", async ({ page }) => {
  const corpusPage = new CorpusPage(page);
  await corpusPage.gotoCorpus(corpusId);
  await corpusPage.expectDocumentCount(3);
});
```

### 2. Use API Client for Setup

Don't use UI for test setup - use the API directly:

```typescript
import { ApiClient } from "./fixtures/api-client";

test.beforeAll(async () => {
  const api = new ApiClient();
  await api.login("admin@example.com", "admin");
  const corpus = await api.createCorpus("Test Corpus");
  testCorpusId = corpus.id;
});
```

### 3. Clean Up After Tests

```typescript
test.afterAll(async () => {
  await api.deleteCorpus(testCorpusId);
});
```

### 4. Name Test Files with `.e2e.ts` Extension

The Playwright config only matches `*.e2e.ts` files for these tests.

## Authentication

Authentication is handled via a setup project that runs before all tests:

1. `auth.setup.ts` logs in via the UI
2. Saves auth state (cookies, localStorage) to `.auth/user.json`
3. All other tests reuse this stored state

This means:

- Login only happens once per test run
- Tests run faster
- Each test starts already authenticated

## Debugging

### View Test Report

```bash
npx playwright show-report playwright-report-e2e
```

### Debug Mode

```bash
yarn test:e2e:integration --debug
```

### Trace Viewer (for failed tests)

```bash
npx playwright show-trace test-results/*/trace.zip
```

## CI Integration

These tests require a running backend, so they're typically run:

1. **Locally** during development
2. **In CI** with a docker-compose service setup

For CI, ensure:

- Backend services are started before tests
- Use `CI=true` for proper reporter/retry settings
- Consider using `--project=chromium` for speed

## Common Issues

### Backend not running

```
❌ Backend is not running!
   Please start the backend with: docker compose -f local.yml up
```

### No test user

Create a superuser:

```bash
docker compose -f local.yml run django python manage.py createsuperuser
```

### Upload tests skipped

Add a `sample.pdf` to `tests/e2e/fixtures/`:

```bash
cp /path/to/any.pdf frontend/tests/e2e/fixtures/sample.pdf
```
