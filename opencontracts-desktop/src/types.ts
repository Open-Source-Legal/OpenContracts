/**
 * Shared types for OpenContracts Desktop
 */

export enum DockerRuntime {
  DOCKER_DESKTOP = 'docker-desktop',
  RANCHER_DESKTOP = 'rancher-desktop',
  PODMAN = 'podman',
  DOCKER_ENGINE = 'docker-engine',
  UNKNOWN = 'unknown'
}

export interface DockerInfo {
  installed: boolean;
  running: boolean;
  version?: string;
  runtime: DockerRuntime;
  composeAvailable: boolean;
  composeVersion?: string;
}

export interface ServiceStatus {
  name: string;
  running: boolean;
  healthy: boolean;
  error?: string;
}

export interface ComposeStatus {
  allRunning: boolean;
  services: ServiceStatus[];
}

export interface HealthCheckResult {
  healthy: boolean;
  message: string;
  timestamp: number;
}

export enum ComposeState {
  STOPPED = 'stopped',
  STARTING = 'starting',
  RUNNING = 'running',
  STOPPING = 'stopping',
  ERROR = 'error'
}
