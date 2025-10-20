/**
 * Tests for DockerComposeManager
 */

import { DockerComposeManager, createComposeManager } from '../main/docker-compose-manager';
import { ComposeState } from '../types';
import { exec } from 'child_process';

jest.mock('child_process');

describe('DockerComposeManager', () => {
  let manager: DockerComposeManager;

  beforeEach(() => {
    manager = new DockerComposeManager({
      composeFile: '/path/to/desktop.compose.yml',
      projectName: 'opencontracts-test'
    });
    jest.clearAllMocks();
  });

  afterEach(async () => {
    await manager.cleanup();
  });

  describe('start', () => {
    it('should start services successfully', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: 'Started', stderr: '' }));

      await manager.start();

      expect(manager.getState()).toBe(ComposeState.RUNNING);
    });

    it('should not start if already running', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: 'Started', stderr: '' }));

      await manager.start();
      await manager.start();

      expect(mockExec).toHaveBeenCalledTimes(1);
    });

    it('should throw error on failure', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(new Error('Failed to start')));

      await expect(manager.start()).rejects.toThrow('Failed to start services');
      expect(manager.getState()).toBe(ComposeState.ERROR);
    });
  });

  describe('stop', () => {
    it('should stop services successfully', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec
        .mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: 'Started', stderr: '' }))
        .mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: 'Stopped', stderr: '' }));

      await manager.start();
      await manager.stop();

      expect(manager.getState()).toBe(ComposeState.STOPPED);
    });

    it('should not stop if already stopped', async () => {
      const mockExec = exec as unknown as jest.Mock;

      await manager.stop();

      expect(mockExec).not.toHaveBeenCalled();
    });
  });

  describe('getStatus', () => {
    it('should return status of running services', async () => {
      const mockOutput = JSON.stringify({ Service: 'django', State: 'running', Health: 'healthy' }) + '\n' +
                        JSON.stringify({ Service: 'postgres', State: 'running', Health: 'healthy' });

      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: mockOutput, stderr: '' }));

      const status = await manager.getStatus();

      expect(status.allRunning).toBe(true);
      expect(status.services).toHaveLength(2);
      expect(status.services[0].name).toBe('django');
      expect(status.services[0].running).toBe(true);
      expect(status.services[0].healthy).toBe(true);
    });

    it('should handle no running services', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: '', stderr: '' }));

      const status = await manager.getStatus();

      expect(status.allRunning).toBe(false);
      expect(status.services).toHaveLength(0);
    });

    it('should handle errors gracefully', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(new Error('Docker error')));

      const status = await manager.getStatus();

      expect(status.allRunning).toBe(false);
      expect(status.services).toHaveLength(0);
    });
  });

  describe('getLogs', () => {
    it('should fetch logs for a service', async () => {
      const mockLogs = 'Service log line 1\nService log line 2';

      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(null, { stdout: mockLogs, stderr: '' }));

      const logs = await manager.getLogs('django', 50);

      expect(logs).toBe(mockLogs);
    });

    it('should throw error on failure', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, opts, cb: any) => cb(new Error('Service not found')));

      await expect(manager.getLogs('nonexistent')).rejects.toThrow('Failed to get logs');
    });
  });

  describe('createComposeManager', () => {
    it('should create a manager instance', () => {
      const manager = createComposeManager('/path/to/compose.yml', 'test-project');

      expect(manager).toBeInstanceOf(DockerComposeManager);
    });
  });
});
