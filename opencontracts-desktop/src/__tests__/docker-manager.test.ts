/**
 * Tests for DockerManager
 */

import { DockerManager } from '../main/docker-manager';
import { DockerRuntime } from '../types';
import { exec } from 'child_process';

jest.mock('child_process');

describe('DockerManager', () => {
  let manager: DockerManager;

  beforeEach(() => {
    manager = new DockerManager();
    manager.clearCache();
    jest.clearAllMocks();
  });

  describe('checkDockerInstalled', () => {
    it('should detect Docker is installed and running', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec
        .mockImplementationOnce((cmd, cb: any) => cb(null, { stdout: 'Docker version 24.0.0', stderr: '' }))
        .mockImplementationOnce((cmd, cb: any) => cb(null, { stdout: 'Docker info output', stderr: '' }))
        .mockImplementationOnce((cmd, cb: any) => cb(null, { stdout: '{"ServerVersion": "24.0.0"}', stderr: '' }))
        .mockImplementationOnce((cmd, cb: any) => cb(null, { stdout: 'docker-desktop', stderr: '' }))
        .mockImplementationOnce((cmd, cb: any) => cb(null, { stdout: 'Docker Compose version v2.20.0', stderr: '' }));

      const info = await manager.checkDockerInstalled();

      expect(info.installed).toBe(true);
      expect(info.running).toBe(true);
      expect(info.version).toBe('24.0.0');
      expect(info.composeAvailable).toBe(true);
    });

    it('should detect Docker is installed but not running', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec
        .mockImplementationOnce((cmd, cb: any) => cb(null, { stdout: 'Docker version 24.0.0', stderr: '' }))
        .mockImplementationOnce((cmd, cb: any) => cb(new Error('Cannot connect to the Docker daemon')));

      const info = await manager.checkDockerInstalled();

      expect(info.installed).toBe(true);
      expect(info.running).toBe(false);
    });

    it('should detect Docker is not installed', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementationOnce((cmd, cb: any) => cb(new Error('docker: command not found')));

      const info = await manager.checkDockerInstalled();

      expect(info.installed).toBe(false);
      expect(info.running).toBe(false);
      expect(info.runtime).toBe(DockerRuntime.UNKNOWN);
    });

    it('should cache results for performance', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementation((cmd, cb: any) => cb(null, { stdout: 'Docker version 24.0.0', stderr: '' }));

      await manager.checkDockerInstalled();
      await manager.checkDockerInstalled();

      // Should only call once due to caching
      expect(mockExec).toHaveBeenCalledTimes(1);
    });
  });

  describe('getErrorMessage', () => {
    it('should return error when Docker is not installed', () => {
      const info = {
        installed: false,
        running: false,
        runtime: DockerRuntime.UNKNOWN,
        composeAvailable: false
      };

      const message = manager.getErrorMessage(info);
      expect(message).toContain('not installed');
    });

    it('should return error when Docker daemon is not running', () => {
      const info = {
        installed: true,
        running: false,
        runtime: DockerRuntime.DOCKER_DESKTOP,
        composeAvailable: false
      };

      const message = manager.getErrorMessage(info);
      expect(message).toContain('not running');
      expect(message).toContain('Docker Desktop');
    });

    it('should return null when Docker is ready', () => {
      const info = {
        installed: true,
        running: true,
        runtime: DockerRuntime.DOCKER_DESKTOP,
        composeAvailable: true
      };

      const message = manager.getErrorMessage(info);
      expect(message).toBeNull();
    });
  });

  describe('clearCache', () => {
    it('should clear cached Docker info', async () => {
      const mockExec = exec as unknown as jest.Mock;
      mockExec.mockImplementation((cmd, cb: any) => cb(null, { stdout: 'Docker version 24.0.0', stderr: '' }));

      await manager.checkDockerInstalled();
      manager.clearCache();
      await manager.checkDockerInstalled();

      // Should call twice after clearing cache
      expect(mockExec).toHaveBeenCalledTimes(2);
    });
  });
});
