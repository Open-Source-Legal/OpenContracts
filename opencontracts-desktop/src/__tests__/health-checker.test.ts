/**
 * Tests for HealthChecker
 */

import { HealthChecker, createHealthChecker } from '../main/health-checker';
import * as http from 'http';

jest.mock('http');

describe('HealthChecker', () => {
  let checker: HealthChecker;

  beforeEach(() => {
    checker = new HealthChecker({
      healthUrl: 'http://localhost:8000/api/health/',
      maxRetries: 3,
      initialDelayMs: 100,
      maxDelayMs: 400,
      timeoutMs: 1000
    });
    jest.clearAllMocks();
  });

  describe('checkHealth', () => {
    it('should return healthy when service responds with 200', async () => {
      const mockResponse = {
        statusCode: 200,
        on: jest.fn((event, callback) => {
          if (event === 'data') {
            callback('{"status":"ok"}');
          } else if (event === 'end') {
            callback();
          }
          return mockResponse;
        })
      };

      const mockRequest = {
        on: jest.fn().mockReturnThis(),
        end: jest.fn()
      };

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockImplementationOnce((options: any, callback?: any) => {
          if (typeof callback === 'function') {
            setImmediate(() => callback(mockResponse));
          }
          return mockRequest as any;
        });

      const result = await checker.checkHealth();

      expect(result.healthy).toBe(true);
      expect(result.message).toContain('healthy');
    });

    it('should return unhealthy on non-200 status', async () => {
      const mockResponse = {
        statusCode: 500,
        on: jest.fn((event, callback) => {
          if (event === 'end') {
            callback();
          }
          return mockResponse;
        })
      };

      const mockRequest = {
        on: jest.fn().mockReturnThis(),
        end: jest.fn()
      };

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockImplementationOnce((options: any, callback?: any) => {
          if (typeof callback === 'function') {
            setImmediate(() => callback(mockResponse));
          }
          return mockRequest as any;
        });

      const result = await checker.checkHealth();

      expect(result.healthy).toBe(false);
      expect(result.message).toContain('500');
    });

    it('should handle connection errors', async () => {
      const mockRequest = {
        on: jest.fn((event, callback) => {
          if (event === 'error') {
            setImmediate(() => callback(new Error('Connection refused')));
          }
          return mockRequest;
        }),
        end: jest.fn()
      };

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockReturnValueOnce(mockRequest as any);

      const result = await checker.checkHealth();

      expect(result.healthy).toBe(false);
      expect(result.message).toContain('Connection refused');
    });

    it('should handle timeout', async () => {
      const mockRequest = {
        on: jest.fn((event, callback) => {
          if (event === 'timeout') {
            setImmediate(() => callback());
          }
          return mockRequest;
        }),
        end: jest.fn(),
        destroy: jest.fn()
      };

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockReturnValueOnce(mockRequest as any);

      const result = await checker.checkHealth();

      expect(result.healthy).toBe(false);
      expect(result.message).toContain('timed out');
      expect(mockRequest.destroy).toHaveBeenCalled();
    });
  });

  describe('waitForHealthy', () => {
    it('should return immediately when service is healthy', async () => {
      const mockResponse = {
        statusCode: 200,
        on: jest.fn((event, callback) => {
          if (event === 'data') callback('{"status":"ok"}');
          if (event === 'end') callback();
          return mockResponse;
        })
      };

      const mockRequest = {
        on: jest.fn().mockReturnThis(),
        end: jest.fn()
      };

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockImplementation((options: any, callback?: any) => {
          if (typeof callback === 'function') {
            setImmediate(() => callback(mockResponse));
          }
          return mockRequest as any;
        });

      const result = await checker.waitForHealthy();

      expect(result.healthy).toBe(true);
    });

    it('should retry with exponential backoff', async () => {
      let callCount = 0;

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockImplementation((options: any, callback?: any) => {
          callCount++;

          if (callCount === 3) {
            // Third attempt succeeds
            const mockResponse = {
              statusCode: 200,
              on: jest.fn((event, cb) => {
                if (event === 'data') cb('{"status":"ok"}');
                if (event === 'end') cb();
                return mockResponse;
              })
            };
            const mockRequest = {
              on: jest.fn().mockReturnThis(),
              end: jest.fn()
            };
            if (typeof callback === 'function') {
              setImmediate(() => callback(mockResponse));
            }
            return mockRequest as any;
          }

          // First two attempts fail
          const mockRequest = {
            on: jest.fn((event, cb) => {
              if (event === 'error') {
                setImmediate(() => cb(new Error('Not ready')));
              }
              return mockRequest;
            }),
            end: jest.fn()
          };
          return mockRequest as any;
        });

      const progressCalls: number[] = [];
      const result = await checker.waitForHealthy((attempt) => {
        progressCalls.push(attempt);
      });

      expect(result.healthy).toBe(true);
      expect(progressCalls.length).toBeGreaterThan(0);
    });

    it('should fail after max retries', async () => {
      const mockRequest = {
        on: jest.fn((event, callback) => {
          if (event === 'error') {
            setImmediate(() => callback(new Error('Service not available')));
          }
          return mockRequest;
        }),
        end: jest.fn()
      };

      (http.request as jest.MockedFunction<typeof http.request>)
        .mockReturnValue(mockRequest as any);

      const result = await checker.waitForHealthy();

      expect(result.healthy).toBe(false);
      expect(result.message).toContain('failed after 3 attempts');
    });
  });

  describe('createHealthChecker', () => {
    it('should create a health checker instance', () => {
      const checker = createHealthChecker('http://localhost:8000/health/', {
        maxRetries: 5
      });

      expect(checker).toBeInstanceOf(HealthChecker);
    });
  });
});
