import * as assert from 'assert';
import {
    MockChildProcess,
    __setExecSync,
    __setSpawn,
    __setExec,
    __reset,
} from './__mocks__/childProcess';
import * as vscodeMock from './__mocks__/vscode';
import { BackendProcessManager } from '../services/backendProcessManager';

const originalFetch = globalThis.fetch;
const originalShowErrorMessage = vscodeMock.window.showErrorMessage;

/** Configure execSync so only the given python name succeeds. */
function pythonOnPath(name: 'python3' | 'python' = 'python3') {
    __setExecSync((cmd: string) => {
        if (cmd === `${name} --version`) return 'Python 3.12.0';
        throw new Error('not found');
    });
}

describe('BackendProcessManager', () => {
    let manager: BackendProcessManager;

    beforeEach(() => {
        __reset();
        globalThis.fetch = () => Promise.reject(new Error('ECONNREFUSED'));
        vscodeMock.window.showErrorMessage = originalShowErrorMessage;
        manager = new BackendProcessManager();
    });

    afterEach(async () => {
        manager.dispose();
        globalThis.fetch = originalFetch;
        vscodeMock.window.showErrorMessage = originalShowErrorMessage;
    });

    // ── isRunning ──────────────────────────────────────────────────────────

    describe('isRunning', () => {
        it('should return false when no process has been started', () => {
            assert.strictEqual(manager.isRunning(), false);
        });
    });

    // ── start ──────────────────────────────────────────────────────────────

    describe('start', () => {
        it('should detect an external backend via /api/v1/health and skip spawn', async () => {
            globalThis.fetch = () =>
                Promise.resolve(new Response('{"status":"ok"}', { status: 200 }));

            let spawnCalled = false;
            __setSpawn(() => {
                spawnCalled = true;
                return new MockChildProcess();
            });

            await manager.start('/backend', 8000);

            assert.strictEqual(manager.isRunning(), true);
            assert.strictEqual(spawnCalled, false);
        });

        it('should show an error when no Python interpreter is found', async () => {
            let errorMsg = '';
            vscodeMock.window.showErrorMessage = async (...args: unknown[]) => {
                errorMsg = String(args[0]);
                return undefined;
            };

            // Default mock: execSync always throws → no python found
            await manager.start('/backend', 8000);

            assert.strictEqual(manager.isRunning(), false);
            assert.ok(errorMsg.includes('Python'), 'error message should mention Python');
        });

        it('should spawn python with correct arguments and env', async () => {
            let capturedCmd = '';
            let capturedArgs: string[] = [];
            let capturedOpts: Record<string, unknown> = {};

            pythonOnPath('python3');
            __setSpawn((cmd, args, opts) => {
                capturedCmd = cmd;
                capturedArgs = args ?? [];
                capturedOpts = (opts ?? {}) as Record<string, unknown>;
                return new MockChildProcess();
            });

            await manager.start('C:\\my\\backend', 9000, '0.0.0.0');

            assert.strictEqual(capturedCmd, 'python3');
            assert.deepStrictEqual(capturedArgs, ['-m', 'src.main']);
            assert.strictEqual(capturedOpts['cwd'], 'C:\\my\\backend');

            const env = capturedOpts['env'] as Record<string, string>;
            assert.strictEqual(env['HOST'], '0.0.0.0');
            assert.strictEqual(env['PORT'], '9000');
            assert.strictEqual(env['PROCESSING_MODE'], 'local');
            assert.strictEqual(manager.isRunning(), true);
        });

        it('should use 127.0.0.1 as default host', async () => {
            let healthUrl = '';
            globalThis.fetch = ((url: string) => {
                healthUrl = url;
                return Promise.reject(new Error('ECONNREFUSED'));
            }) as typeof fetch;

            pythonOnPath();
            __setSpawn(() => new MockChildProcess());

            await manager.start('/backend', 8000);

            assert.strictEqual(healthUrl, 'http://127.0.0.1:8000/api/v1/health');
        });

        it('should not spawn a second process when already running', async () => {
            let spawnCount = 0;
            pythonOnPath();
            __setSpawn(() => {
                spawnCount++;
                return new MockChildProcess();
            });

            await manager.start('/backend', 8000);
            await manager.start('/backend', 8000);

            assert.strictEqual(spawnCount, 1);
        });

        it('should fall back to python when python3 is not available', async () => {
            let capturedCmd = '';
            __setExecSync((cmd: string) => {
                if (cmd === 'python --version') return 'Python 3.12.0';
                throw new Error('not found');
            });
            __setSpawn((cmd) => {
                capturedCmd = cmd;
                return new MockChildProcess();
            });

            await manager.start('/backend', 8000);

            assert.strictEqual(capturedCmd, 'python');
        });

        it('should not spawn when external backend already responds on health', async () => {
            globalThis.fetch = () =>
                Promise.resolve(new Response('{"status":"ok"}', { status: 200 }));

            await manager.start('/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);

            // Calling start again is a no-op (already-running guard)
            await manager.start('/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);
        });
    });

    // ── stop ───────────────────────────────────────────────────────────────

    describe('stop', () => {
        it('should skip kill when backend is externally managed', async () => {
            globalThis.fetch = () =>
                Promise.resolve(new Response('{"status":"ok"}', { status: 200 }));
            await manager.start('/backend', 8000);

            let execCalled = false;
            __setExec((_cmd: string, cb?: (...args: unknown[]) => void) => {
                execCalled = true;
                cb?.();
            });

            await manager.stop();

            assert.strictEqual(execCalled, false);
            assert.strictEqual(manager.isRunning(), false);
        });

        it('should kill a managed process', async () => {
            const mockChild = new MockChildProcess();
            pythonOnPath();
            __setSpawn(() => mockChild);

            await manager.start('/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);

            await manager.stop();

            assert.strictEqual(mockChild.killed, true);
            assert.strictEqual(manager.isRunning(), false);
        });

        it('should be a no-op when nothing is running', async () => {
            await manager.stop();
            assert.strictEqual(manager.isRunning(), false);
        });
    });

    // ── getOutputChannel ───────────────────────────────────────────────────

    describe('getOutputChannel', () => {
        it('should return an output channel with appendLine', () => {
            const ch = manager.getOutputChannel();
            assert.ok(ch);
            assert.strictEqual(typeof ch.appendLine, 'function');
        });
    });

    // ── dispose ────────────────────────────────────────────────────────────

    describe('dispose', () => {
        it('should dispose the output channel', () => {
            const fresh = new BackendProcessManager();
            let disposed = false;
            fresh.getOutputChannel().dispose = () => {
                disposed = true;
            };

            fresh.dispose();

            assert.strictEqual(disposed, true);
        });

        it('should kill managed process synchronously on dispose', async () => {
            const mockChild = new MockChildProcess();
            pythonOnPath();
            __setSpawn(() => mockChild);

            await manager.start('/backend', 8000);
            assert.strictEqual(manager.isRunning(), true);

            manager.dispose();

            assert.strictEqual(mockChild.killed, true);
            assert.strictEqual(manager.isRunning(), false);
        });
    });
});
