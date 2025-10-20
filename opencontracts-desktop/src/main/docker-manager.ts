/**
 * Docker Runtime Detection Module
 * Detects and validates Docker/Podman/Rancher installations
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { DockerInfo, DockerRuntime } from '../types';

const execAsync = promisify(exec);

export class DockerManager {
  private cachedInfo?: DockerInfo;
  private cacheTime: number = 0;
  private readonly CACHE_TTL = 5000; // 5 seconds

  /**
   * Check if Docker is installed and running
   */
  async checkDockerInstalled(): Promise<DockerInfo> {
    // Return cached result if still valid
    if (this.cachedInfo && Date.now() - this.cacheTime < this.CACHE_TTL) {
      return this.cachedInfo;
    }

    const info: DockerInfo = {
      installed: false,
      running: false,
      runtime: DockerRuntime.UNKNOWN,
      composeAvailable: false
    };

    try {
      // Check if docker command exists
      const { stdout: versionOutput } = await execAsync('docker --version');
      info.installed = true;
      info.version = this.parseVersion(versionOutput);

      // Check if daemon is running
      try {
        await execAsync('docker info');
        info.running = true;
      } catch {
        info.running = false;
      }

      // Detect runtime type
      info.runtime = await this.detectRuntime();

      // Check docker compose availability
      info.composeAvailable = await this.checkComposeAvailable();
      if (info.composeAvailable) {
        const { stdout: composeVersion } = await execAsync('docker compose version');
        info.composeVersion = this.parseVersion(composeVersion);
      }
    } catch (error) {
      // Docker not installed or not in PATH
      info.installed = false;
      info.running = false;
    }

    this.cachedInfo = info;
    this.cacheTime = Date.now();
    return info;
  }

  /**
   * Detect which Docker runtime is being used
   */
  private async detectRuntime(): Promise<DockerRuntime> {
    try {
      const { stdout } = await execAsync('docker info --format "{{.ServerVersion}}"');
      const info = stdout.toLowerCase();

      // Check for Podman
      if (info.includes('podman')) {
        return DockerRuntime.PODMAN;
      }

      // Check for Rancher Desktop
      try {
        const { stdout: contextOutput } = await execAsync('docker context show');
        if (contextOutput.toLowerCase().includes('rancher')) {
          return DockerRuntime.RANCHER_DESKTOP;
        }
      } catch {
        // Continue to other checks
      }

      // Check for Docker Desktop (has desktop-specific features)
      try {
        const { stdout: infoJson } = await execAsync('docker info --format json');
        const dockerInfo = JSON.parse(infoJson);

        if (dockerInfo.Name?.toLowerCase().includes('desktop') ||
            dockerInfo.OperatingSystem?.toLowerCase().includes('docker desktop')) {
          return DockerRuntime.DOCKER_DESKTOP;
        }
      } catch {
        // Fall through to Docker Engine
      }

      // Default to Docker Engine
      return DockerRuntime.DOCKER_ENGINE;
    } catch {
      return DockerRuntime.UNKNOWN;
    }
  }

  /**
   * Check if docker compose is available
   */
  private async checkComposeAvailable(): Promise<boolean> {
    try {
      await execAsync('docker compose version');
      return true;
    } catch {
      // Try legacy docker-compose
      try {
        await execAsync('docker-compose --version');
        return true;
      } catch {
        return false;
      }
    }
  }

  /**
   * Parse version string from command output
   */
  private parseVersion(output: string): string {
    const match = output.match(/version\s+v?(\d+\.\d+\.\d+)/i);
    return match ? match[1] : output.trim();
  }

  /**
   * Get error message for user based on Docker status
   */
  getErrorMessage(info: DockerInfo): string | null {
    if (!info.installed) {
      return 'Docker is not installed. Please install Docker Desktop, Rancher Desktop, or Podman to use OpenContracts Desktop.';
    }

    if (!info.running) {
      return `Docker daemon is not running. Please start ${this.getRuntimeName(info.runtime)} and try again.`;
    }

    if (!info.composeAvailable) {
      return 'Docker Compose is not available. Please ensure you have a recent version of Docker installed.';
    }

    return null;
  }

  /**
   * Get friendly name for Docker runtime
   */
  private getRuntimeName(runtime: DockerRuntime): string {
    switch (runtime) {
      case DockerRuntime.DOCKER_DESKTOP:
        return 'Docker Desktop';
      case DockerRuntime.RANCHER_DESKTOP:
        return 'Rancher Desktop';
      case DockerRuntime.PODMAN:
        return 'Podman';
      case DockerRuntime.DOCKER_ENGINE:
        return 'Docker';
      default:
        return 'your Docker runtime';
    }
  }

  /**
   * Clear cached Docker info (useful for testing or after errors)
   */
  clearCache(): void {
    this.cachedInfo = undefined;
    this.cacheTime = 0;
  }
}

// Export singleton instance
export const dockerManager = new DockerManager();
