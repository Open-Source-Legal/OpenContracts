/**
 * Docker Compose Lifecycle Manager
 * Manages docker compose up/down/status operations
 */

import { exec, spawn, ChildProcess } from 'child_process';
import { promisify } from 'util';
import * as path from 'path';
import { ComposeStatus, ServiceStatus, ComposeState } from '../types';

const execAsync = promisify(exec);

export interface ComposeManagerOptions {
  composeFile: string;
  projectName?: string;
  workingDirectory?: string;
}

export class DockerComposeManager {
  private composeFile: string;
  private projectName: string;
  private workingDirectory: string;
  private currentState: ComposeState = ComposeState.STOPPED;
  private logProcess?: ChildProcess;

  constructor(options: ComposeManagerOptions) {
    this.composeFile = options.composeFile;
    this.projectName = options.projectName || 'opencontracts';
    this.workingDirectory = options.workingDirectory || process.cwd();
  }

  /**
   * Start all services using docker compose up
   */
  async start(): Promise<void> {
    if (this.currentState === ComposeState.RUNNING) {
      return;
    }

    this.currentState = ComposeState.STARTING;

    try {
      const command = this.buildCommand('up', ['-d', '--wait']);

      // Execute with timeout
      await this.execWithTimeout(command, 120000); // 2 minute timeout

      this.currentState = ComposeState.RUNNING;
    } catch (error) {
      this.currentState = ComposeState.ERROR;
      throw new Error(`Failed to start services: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Stop all services using docker compose down
   */
  async stop(): Promise<void> {
    if (this.currentState === ComposeState.STOPPED) {
      return;
    }

    this.currentState = ComposeState.STOPPING;

    try {
      const command = this.buildCommand('down', []);

      await this.execWithTimeout(command, 60000); // 1 minute timeout

      this.currentState = ComposeState.STOPPED;
    } catch (error) {
      this.currentState = ComposeState.ERROR;
      throw new Error(`Failed to stop services: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Get status of all services
   */
  async getStatus(): Promise<ComposeStatus> {
    try {
      const command = this.buildCommand('ps', ['--format', 'json']);

      const { stdout } = await execAsync(command, {
        cwd: this.workingDirectory
      });

      if (!stdout.trim()) {
        return { allRunning: false, services: [] };
      }

      // Parse JSON output (one object per line for compose v2)
      const services: ServiceStatus[] = [];
      const lines = stdout.trim().split('\n');

      for (const line of lines) {
        try {
          const container = JSON.parse(line);
          services.push({
            name: container.Service || container.Name,
            running: container.State === 'running',
            healthy: container.Health === 'healthy' || container.State === 'running'
          });
        } catch {
          // Skip malformed lines
          continue;
        }
      }

      const allRunning = services.length > 0 && services.every(s => s.running);

      return { allRunning, services };
    } catch (error) {
      return { allRunning: false, services: [] };
    }
  }

  /**
   * Get logs for a specific service
   */
  async getLogs(service: string, tail: number = 100): Promise<string> {
    try {
      const command = this.buildCommand('logs', [service, '--tail', tail.toString()]);

      const { stdout } = await execAsync(command, {
        cwd: this.workingDirectory
      });

      return stdout;
    } catch (error) {
      throw new Error(`Failed to get logs for ${service}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Stream logs from all services
   */
  streamLogs(callback: (data: string) => void): void {
    if (this.logProcess) {
      this.stopLogStream();
    }

    const args = ['compose', '-f', this.composeFile, '-p', this.projectName, 'logs', '-f'];

    this.logProcess = spawn('docker', args, {
      cwd: this.workingDirectory
    });

    this.logProcess.stdout?.on('data', (data: Buffer) => {
      callback(data.toString());
    });

    this.logProcess.stderr?.on('data', (data: Buffer) => {
      callback(data.toString());
    });

    this.logProcess.on('error', (error) => {
      callback(`Log stream error: ${error.message}\n`);
    });
  }

  /**
   * Stop log streaming
   */
  stopLogStream(): void {
    if (this.logProcess) {
      this.logProcess.kill();
      this.logProcess = undefined;
    }
  }

  /**
   * Get current state
   */
  getState(): ComposeState {
    return this.currentState;
  }

  /**
   * Build docker compose command
   */
  private buildCommand(subcommand: string, args: string[]): string {
    const baseArgs = ['compose', '-f', this.composeFile, '-p', this.projectName, subcommand];
    return `docker ${[...baseArgs, ...args].join(' ')}`;
  }

  /**
   * Execute command with timeout
   */
  private async execWithTimeout(command: string, timeout: number): Promise<{ stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Command timed out after ${timeout}ms`));
      }, timeout);

      execAsync(command, {
        cwd: this.workingDirectory,
        maxBuffer: 10 * 1024 * 1024 // 10MB buffer for large outputs
      })
        .then((result) => {
          clearTimeout(timer);
          resolve(result);
        })
        .catch((error) => {
          clearTimeout(timer);
          reject(error);
        });
    });
  }

  /**
   * Cleanup resources
   */
  async cleanup(): Promise<void> {
    this.stopLogStream();
  }
}

/**
 * Create a compose manager instance
 */
export function createComposeManager(composeFile: string, projectName?: string): DockerComposeManager {
  return new DockerComposeManager({
    composeFile,
    projectName,
    workingDirectory: path.dirname(composeFile)
  });
}
