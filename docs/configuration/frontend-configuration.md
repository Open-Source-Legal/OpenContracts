# Frontend Configuration

*Last Updated: 2026-01-09*

## Overview

The frontend configuration variables should not be secrets as there is no way to keep them secure on the frontend. That said, being able to specify certain configurations via environment variables makes configuration and deployment much easier.

**Reference**: See sample env files in [docs/sample_env_files/frontend/](../sample_env_files/frontend/) for complete examples.

## Environment Variable Naming by Context

The frontend uses different environment variable prefixes depending on the deployment context:

| Context | Prefix | Example |
|---------|--------|---------|
| Local development (Vite) | `VITE_` | `VITE_USE_AUTH0=true` |
| Production (Docker/K8s) | `OPEN_CONTRACTS_` | `OPEN_CONTRACTS_REACT_APP_USE_AUTH0=true` |

**How it works**: In production, the container entrypoint script writes a runtime-loaded file at `frontend/public/env-config.js` that populates `window._env_` with the `REACT_APP_*` variables converted from `OPEN_CONTRACTS_REACT_APP_*`. For example, `OPEN_CONTRACTS_REACT_APP_USE_AUTH0` becomes `window._env_.REACT_APP_USE_AUTH0` in the frontend code. The browser fetches `env-config.js` on every page load, so configuration changes do **not** require a frontend rebuild — only a container restart (or `env-config.js` regeneration) is needed.

See [`frontend/public/env-config.js`](https://github.com/Open-Source-Legal/OpenContracts/blob/main/frontend/public/env-config.js) for the file structure and the [Frontend Telemetry doc](../telemetry/Frontend.md) for how the same mechanism is used to inject PostHog keys.

## Available Configuration Options

| Setting | Local (VITE_) | Production (OPEN_CONTRACTS_REACT_APP_) | Description |
|---------|---------------|----------------------------------------|-------------|
| Auth0 toggle | `VITE_USE_AUTH0` | `OPEN_CONTRACTS_REACT_APP_USE_AUTH0` | Enable Auth0 authentication (default: false) |
| Auth0 domain | `VITE_APPLICATION_DOMAIN` | `OPEN_CONTRACTS_REACT_APP_APPLICATION_DOMAIN` | Auth0 domain (required if Auth0 enabled) |
| Auth0 client ID | `VITE_APPLICATION_CLIENT_ID` | `OPEN_CONTRACTS_REACT_APP_APPLICATION_CLIENT_ID` | Auth0 client ID (required if Auth0 enabled) |
| Auth0 audience | `VITE_AUDIENCE` | `OPEN_CONTRACTS_REACT_APP_AUDIENCE` | Auth0 API audience |
| API root URL | `VITE_API_ROOT_URL` | `OPEN_CONTRACTS_REACT_APP_API_ROOT_URL` | Backend API URL |
| Analyzers | `VITE_USE_ANALYZERS` | `OPEN_CONTRACTS_REACT_APP_USE_ANALYZERS` | Enable analyzer functionality |
| Imports | `VITE_ALLOW_IMPORTS` | `OPEN_CONTRACTS_REACT_APP_ALLOW_IMPORTS` | Enable corpus import from ZIP files |
| WebSocket URL | `VITE_WS_URL` | N/A (auto-proxied in dev) | WebSocket connection URL |

## Local Development (Vite)

For local development, create a file at `.envs/.local/.frontend` with `VITE_*` prefixed variables:

**Reference**: See [docs/sample_env_files/frontend/local/django.auth.env](../sample_env_files/frontend/local/django.auth.env) for Django auth or [docs/sample_env_files/frontend/local/with.auth0.env](../sample_env_files/frontend/local/with.auth0.env) for Auth0.

The Vite dev server runs on port **5173** and automatically proxies `/graphql`, `/api`, and `/ws` to the Django backend on port 8000.

## Production Deployment (Docker/Kubernetes)

For production, use `OPEN_CONTRACTS_*` prefixed variables. The container entrypoint converts these to runtime `REACT_APP_*` config.

**Reference**: See [docs/sample_env_files/frontend/production/frontend.env](../sample_env_files/frontend/production/frontend.env) for a complete example.

## Key Configuration Details

### 1. Authentication Mode (`USE_AUTH0`)

Set to `true` to switch from Django password auth to Auth0 OAuth2. When enabled, you must also provide:
- `APPLICATION_DOMAIN` - Your Auth0 domain
- `APPLICATION_CLIENT_ID` - Your Auth0 application client ID
- `AUDIENCE` - Your Auth0 API audience

### 2. Analyzer Access (`USE_ANALYZERS`)

Controls whether users can see and use document analyzers. Set to `false` on demo deployments where analyzer access should be restricted.

### 3. Import Functionality (`ALLOW_IMPORTS`)

Controls whether users can upload ZIP files for corpus imports. Not recommended for public installations due to security considerations. Internal organizational deployments should still use caution.

## Configuration Methods for Docker Compose

### Method 1: Using an `.env` File

Docker Compose automatically picks up a `.env` file in the same directory as your `docker-compose.yml`.

**Pros**: Simple setup, easy to version control
**Cons**: All services share the same variables

### Method 2: Using `env_file` in Docker Compose

Specify a custom env file for each service:

```yaml
services:
  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    env_file:
      - ./.envs/.local/.frontend
```

**Pros**: Different env files per service, explicit configuration
**Cons**: Requires specifying in compose file

### Method 3: Direct Environment Variables

Define variables directly in `docker-compose.yml`:

```yaml
services:
  frontend:
    environment:
      - OPEN_CONTRACTS_REACT_APP_USE_AUTH0=false
      - OPEN_CONTRACTS_REACT_APP_USE_ANALYZERS=true
```

**Pros**: All configuration visible in one file
**Cons**: Can make compose file long, sensitive info exposed

### Method 4: Combined Approach

Use `env_file` for most variables and `environment` for overrides:

```yaml
services:
  frontend:
    env_file:
      - ./.envs/.local/.frontend
    environment:
      - OPEN_CONTRACTS_REACT_APP_USE_ANALYZERS=true
```

**Note**: Docker Compose `environment` values override `env_file` values.
