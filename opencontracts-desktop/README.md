# OpenContracts Desktop

Docker management modules for the OpenContracts Electron desktop application.

## Overview

This package provides core infrastructure for managing Docker-based services in the OpenContracts desktop app:

- **Docker Detection** - Detects and validates Docker Desktop, Rancher Desktop, or Podman installations
- **Compose Lifecycle** - Manages docker-compose up/down/status operations
- **Health Checking** - Polls service health endpoints with exponential backoff retry

## Modules

### DockerManager (`src/main/docker-manager.ts`)

Detects Docker installations across different runtimes and platforms.

```typescript
import { dockerManager } from './main/docker-manager';

const info = await dockerManager.checkDockerInstalled();

if (!info.installed) {
  console.error('Docker is not installed');
} else if (!info.running) {
  console.error('Docker daemon is not running');
} else {
  console.log(`Docker ${info.version} is ready (${info.runtime})`);
}
```

**Features:**
- Detects Docker Desktop, Rancher Desktop, Podman, and Docker Engine
- Checks if daemon is running
- Validates docker compose availability
- Caches results for performance
- Platform-specific detection (macOS, Windows, Linux)

### DockerComposeManager (`src/main/docker-compose-manager.ts`)

Manages docker-compose lifecycle operations.

```typescript
import { createComposeManager } from './main/docker-compose-manager';

const manager = createComposeManager(
  '/path/to/desktop.compose.yml',
  'opencontracts'
);

// Start all services
await manager.start();

// Check status
const status = await manager.getStatus();
console.log(`All running: ${status.allRunning}`);

// Get logs
const logs = await manager.getLogs('django', 100);

// Stream logs
manager.streamLogs((data) => console.log(data));

// Stop all services
await manager.stop();
```

**Features:**
- Execute `docker compose up -d` with timeout
- Execute `docker compose down` with graceful shutdown
- Get service status with health information
- Fetch logs for specific services
- Stream logs in real-time
- Error handling and recovery

### HealthChecker (`src/main/health-checker.ts`)

Polls health endpoints with exponential backoff.

```typescript
import { createHealthChecker } from './main/health-checker';

const checker = createHealthChecker('http://localhost:8000/api/health/', {
  maxRetries: 30,
  initialDelayMs: 1000,
  maxDelayMs: 8000
});

const result = await checker.waitForHealthy((attempt, maxRetries, delay) => {
  console.log(`Health check attempt ${attempt}/${maxRetries}, next delay: ${delay}ms`);
});

if (result.healthy) {
  console.log('Service is ready!');
} else {
  console.error(`Health check failed: ${result.message}`);
}
```

**Features:**
- Exponential backoff retry (1s → 2s → 4s → 8s)
- Configurable max retries and timeouts
- Progress reporting callbacks
- Single-shot health checks
- Graceful timeout handling

## Development

### Install dependencies

```bash
npm install
```

### Build

```bash
npm run build
```

### Run tests

```bash
npm test

# Watch mode
npm run test:watch
```

### Lint

```bash
npm run lint
```

## Requirements

- Node.js 16+
- TypeScript 5+
- Docker Desktop, Rancher Desktop, or Podman

## Architecture

The modules are designed to be:

- **Standalone** - No Electron dependencies, can be used in Node.js CLI tools
- **Testable** - Full unit test coverage with mocked child_process
- **Type-safe** - Written in TypeScript with strict mode
- **Cross-platform** - Works on macOS, Windows, and Linux

## Testing with Different Docker Runtimes

The modules have been designed to work with:

- **Docker Desktop** (macOS, Windows, Linux)
- **Rancher Desktop** (macOS, Windows, Linux)
- **Podman Desktop** (Linux, macOS with podman-compose)
- **Docker Engine** (Linux)

Each runtime is detected automatically and appropriate commands are used.

## License

Apache-2.0
