// Configurable child_process mock for unit testing.
// Exported functions delegate to swappable implementations so each test can
// configure different behaviour without reloading the module under test.

import { EventEmitter } from 'events';

// ── Mock ChildProcess ──────────────────────────────────────────────────────

export class MockChildProcess extends EventEmitter {
    pid = 12345;
    killed = false;
    stdout = new EventEmitter();
    stderr = new EventEmitter();

    kill(_signal?: string): boolean {
        this.killed = true;
        // Emit exit asynchronously so waitForExit resolves quickly in tests.
        process.nextTick(() => this.emit('exit', 0, _signal ?? null));
        return true;
    }
}

// ── Swappable implementations ──────────────────────────────────────────────

type ExecSyncFn = (command: string, options?: object) => string | Buffer;
type SpawnFn = (command: string, args?: string[], options?: object) => MockChildProcess;
type ExecFn = (command: string, callback?: (...args: unknown[]) => void) => unknown;

let _execSync: ExecSyncFn = () => {
    throw new Error('command not found');
};
let _spawn: SpawnFn = () => new MockChildProcess();
let _exec: ExecFn = (_cmd, cb) => {
    cb?.();
};

// ── Exports consumed by production code ────────────────────────────────────

export function execSync(command: string, options?: object): string | Buffer {
    return _execSync(command, options);
}

export function spawn(command: string, args?: string[], options?: object): MockChildProcess {
    return _spawn(command, args, options);
}

export function exec(command: string, callback?: (...args: unknown[]) => void): unknown {
    return _exec(command, callback);
}

// ── Test helpers ───────────────────────────────────────────────────────────

export function __setExecSync(fn: ExecSyncFn): void {
    _execSync = fn;
}
export function __setSpawn(fn: SpawnFn): void {
    _spawn = fn;
}
export function __setExec(fn: ExecFn): void {
    _exec = fn;
}

export function __reset(): void {
    _execSync = () => {
        throw new Error('command not found');
    };
    _spawn = () => new MockChildProcess();
    _exec = (_cmd, cb) => {
        cb?.();
    };
}
