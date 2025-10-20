/**
 * Health Checker Module
 * Polls Django health endpoint with exponential backoff
 */

import * as http from 'http';
import { HealthCheckResult } from '../types';

export interface HealthCheckerOptions {
  healthUrl: string;
  maxRetries?: number;
  initialDelayMs?: number;
  maxDelayMs?: number;
  timeoutMs?: number;
}

export class HealthChecker {
  private healthUrl: string;
  private maxRetries: number;
  private initialDelayMs: number;
  private maxDelayMs: number;
  private timeoutMs: number;

  constructor(options: HealthCheckerOptions) {
    this.healthUrl = options.healthUrl;
    this.maxRetries = options.maxRetries ?? 30;
    this.initialDelayMs = options.initialDelayMs ?? 1000;
    this.maxDelayMs = options.maxDelayMs ?? 8000;
    this.timeoutMs = options.timeoutMs ?? 5000;
  }

  /**
   * Wait for service to become healthy with exponential backoff
   */
  async waitForHealthy(
    onProgress?: (attempt: number, maxRetries: number, nextDelay: number) => void
  ): Promise<HealthCheckResult> {
    let attempt = 0;
    let delay = this.initialDelayMs;

    while (attempt < this.maxRetries) {
      attempt++;

      // Report progress
      if (onProgress) {
        onProgress(attempt, this.maxRetries, delay);
      }

      // Check health
      const result = await this.checkHealth();
      if (result.healthy) {
        return result;
      }

      // Don't delay on last attempt
      if (attempt < this.maxRetries) {
        await this.sleep(delay);

        // Exponential backoff with cap
        delay = Math.min(delay * 2, this.maxDelayMs);
      }
    }

    return {
      healthy: false,
      message: `Health check failed after ${this.maxRetries} attempts`,
      timestamp: Date.now()
    };
  }

  /**
   * Perform a single health check
   */
  async checkHealth(): Promise<HealthCheckResult> {
    return new Promise((resolve) => {
      const url = new URL(this.healthUrl);

      const options = {
        hostname: url.hostname,
        port: url.port || 80,
        path: url.pathname,
        method: 'GET',
        timeout: this.timeoutMs
      };

      const req = http.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          if (res.statusCode === 200) {
            resolve({
              healthy: true,
              message: 'Service is healthy',
              timestamp: Date.now()
            });
          } else {
            resolve({
              healthy: false,
              message: `Health check returned status ${res.statusCode}`,
              timestamp: Date.now()
            });
          }
        });
      });

      req.on('error', (error) => {
        resolve({
          healthy: false,
          message: `Health check failed: ${error.message}`,
          timestamp: Date.now()
        });
      });

      req.on('timeout', () => {
        req.destroy();
        resolve({
          healthy: false,
          message: 'Health check timed out',
          timestamp: Date.now()
        });
      });

      req.end();
    });
  }

  /**
   * Sleep for specified milliseconds
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * Create a health checker instance
 */
export function createHealthChecker(healthUrl: string, options?: Partial<HealthCheckerOptions>): HealthChecker {
  return new HealthChecker({
    healthUrl,
    ...options
  });
}
