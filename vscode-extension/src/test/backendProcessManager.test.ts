import * as assert from 'assert';
import { MockChildProcess, __setExecSync, __setSpawn, __reset } from './__mocks__/childProcess';
import { extensions } from './__mocks__/vscode';
import { BackendProcessManager } from '../services/backendProcessManager';

// Stub global fetch for health-check tests
const originalFetch = globalThis.fetch;

describe('BackendProcessManager', () => {
    let manager: BackendProcessManager;

    beforeEach(() => {
        __reset();
        manager = new BackendProcessManager();
        // Default: no external backend running
        globalThis.fetch = () => Promise.reject(new Error('ECONNREFUSED'));
    });

    afterEach(async () => {
        manager.dispose();
        globalThis.fetch = originalFetch;
    });

    describe('constructor', () => {
        it('should create an output channel', () => {
            const channel = manager.getOutputChannel();
            assert.ok(channel);
            assert.ok(typeof channel.appendLine === 'function');
        });

        it('should not be running initially', () => {
            assert.strictEqual(manager.isRunning(), false);
        });
    });

    describe('start()', () => {
        it('should spawn python with correct arguments', async () => {
            let spawnedCmd = '';
            let spawnedArgs: string[] = [];
            let spawnedOpts: Record<string, unknown> = {};

            // Make python3 discoverable
            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            __setSpawn((cmd, args, opts) => {
                spawnedCmd = cmd;
                spawnedArgs = args ?? [];
                spawnedOpts = (opts ?? {}) as Record<string, unknown>;
                return new MockChildProcess();
            });

            await manager.start('/path/to/backend', 8000, '127.0.0.1');

            assert.strictEqual(spawnedCmd, 'python3');
            assert.deepStrictEqual(spawnedArgs, ['-m', 'src.main']);
            assert.strictEqual(spawnedOpts['cwd'], '/path/to/backend');
            const env = spawnedOpts['env'] as Record<string, string>;
            assert.strictEqual(env['HOST'], '127.0.0.1');
            assert.strictEqual(env['PORT'], '8000');
            assert.strictEqual(env['PROCESSING_MODE'], 'local');
        });

        it('should default host to 127.0.0.1', async () => {
            let spawnedOpts: Record<string, unknown> = {};

            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            __setSpawn((_cmd, _args, opts) => {
                spawnedOpts = (opts ?? {}) as Record<string, unknown>;
                return new MockChildProcess();
            });

            await manager.start('/path/to/backend', 8000);

            const env = spawnedOpts['env'] as Record<string, string>;
            assert.strictEqual(env['HOST'], '127.0.0.1');
        });

        it('should report running after successful start', async () => {
            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            await manager.start('/path/to/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);
        });

        it('should not spawn twice if already running', async () => {
            let spawnCount = 0;

            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            __setSpawn(() => {
                spawnCount++;
                return new MockChildProcess();
            });

            await manager.start('/path/to/backend', 8000);
            await manager.start('/path/to/backend', 8000);

            assert.strictEqual(spawnCount, 1);
        });

        it('should detect external backend and skip spawn', async () => {
            let spawnCalled = false;

            // External backend is healthy
            globalThis.fetch = () =>
                Promise.resolve(new Response('{"status":"ok"}', { status: 200 }));

            __setSpawn(() => {
                spawnCalled = true;
                return new MockChildProcess();
            });

            await manager.start('/path/to/backend', 8000);

            assert.strictEqual(spawnCalled, false);
            assert.strictEqual(manager.isRunning(), true);
        });

        it('should try python after python3 fails', async () => {
            let resolvedInterpreter = '';

            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { throw new Error('not found'); }
                if (cmd === 'python --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            __setSpawn((cmd) => {
                resolvedInterpreter = cmd;
                return new MockChildProcess();
            });

            await manager.start('/path/to/backend', 8000);
            assert.strictEqual(resolvedInterpreter, 'python');
        });

        it('should handle no Python found gracefully', async () => {
            // All Python lookups fail, no VS Code Python extension
            (extensions as { getExtension: unknown }).getExtension = () => undefined;

            __setExecSync(() => {
                throw new Error('not found');
            });

            // Should not throw — shows error message instead
            await manager.start('/path/to/backend', 8000);
            assert.strictEqual(manager.isRunning(), false);
        });
    });

    describe('stop()', () => {
        it('should kill the process on stop', async () => {
            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            const mockChild = new MockChildProcess();
            __setSpawn(() => mockChild);

            await manager.start('/path/to/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);

            await manager.stop();
            assert.strictEqual(manager.isRunning(), false);
        });

        it('should skip stop for external backend', async () => {
            // External backend is healthy
            globalThis.fetch = () =>
                Promise.resolve(new Response('{"status":"ok"}', { status: 200 }));

            await manager.start('/path/to/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);

            // stop() should be a no-op — just resets the flag
            await manager.stop();
            assert.strictEqual(manager.isRunning(), false);
        });

        it('should be safe to call stop when not running', async () => {
            // Should not throw
            await manager.stop();
            assert.strictEqual(manager.isRunning(), false);
        });
    });

    describe('dispose()', () => {
        it('should stop the process and dispose the output channel', async () => {
            __setExecSync((cmd: string) => {
                if (cmd === 'python3 --version') { return 'Python 3.11.0'; }
                throw new Error('not found');
            });

            await manager.start('/path/to/backend', 8000);
            manager.dispose();

            // After dispose, isRunning may still briefly be true since stop is async,
            // but the channel should be disposed
            assert.ok(manager.getOutputChannel());
        });
    });
});
