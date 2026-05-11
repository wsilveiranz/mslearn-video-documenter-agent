import { execSync, spawn, exec, type ChildProcess } from 'child_process';
import * as vscode from 'vscode';
import {
    getProcessingMode,
    getFoundryProjectEndpoint,
    getFoundryModel,
    getFoundryModelMini,
    getBlobAccountUrl,
    getBlobContainerName,
    getSpeechServiceEndpoint,
    getSpeechServiceRegion,
    getVideoIndexerAccountId,
    getVideoIndexerResourceId,
    getVideoIndexerLocation,
    getWhisperModel,
    getFfmpegPath,
} from '../utils/config';

// ── Python interpreter discovery ───────────────────────────────────────────

/**
 * Locate a usable Python interpreter, preferring the VS Code Python extension's
 * configured interpreter, then `python3`, then `python` on PATH.
 */
async function findPythonInterpreter(): Promise<string> {
    // 1. Try VS Code Python extension
    const pyExt = vscode.extensions.getExtension('ms-python.python');
    if (pyExt) {
        if (!pyExt.isActive) {
            await pyExt.activate();
        }
        const execDetails: { execCommand?: string[] } | undefined =
            pyExt.exports?.settings?.getExecutionDetails?.();
        if (execDetails?.execCommand?.[0]) {
            return execDetails.execCommand[0];
        }
    }

    // Fallback: check the user setting
    const configuredPath = vscode.workspace
        .getConfiguration('python')
        .get<string>('defaultInterpreterPath');
    if (configuredPath && configuredPath !== 'python') {
        try {
            execSync(`"${configuredPath}" --version`, { stdio: 'ignore' });
            return configuredPath;
        } catch {
            // configured path is not valid — continue
        }
    }

    // 2. Try python3
    try {
        execSync('python3 --version', { stdio: 'ignore' });
        return 'python3';
    } catch {
        // not found
    }

    // 3. Try python
    try {
        execSync('python --version', { stdio: 'ignore' });
        return 'python';
    } catch {
        // not found
    }

    throw new Error(
        'No Python interpreter found. Install Python 3.10+ and ensure it is on your PATH, ' +
            'or configure the Python extension in VS Code.',
    );
}

// ── BackendProcessManager ──────────────────────────────────────────────────

export class BackendProcessManager implements vscode.Disposable {
    private _process: ChildProcess | undefined;
    private _externalProcess = false;
    private _stopping = false;
    private _outputChannel: vscode.OutputChannel;
    private _exitHandler: (() => void) | undefined;

    constructor() {
        this._outputChannel = vscode.window.createOutputChannel('Video Documenter Backend');

        // Safety net: synchronously kill child process on extension host exit
        this._exitHandler = () => this._killSync();
        process.on('exit', this._exitHandler);
    }

    /**
     * Start the Python backend process. If a backend is already responding on
     * the target host/port, the existing instance is reused.
     */
    async start(backendPath: string, port: number, host?: string): Promise<void> {
        const resolvedHost = host ?? '127.0.0.1';

        this._stopping = false;

        if (this._process || this._externalProcess) {
            this._outputChannel.appendLine('[BackendProcessManager] Backend is already running.');
            return;
        }

        // Check whether an external backend is already listening
        if (await this.isHealthy(resolvedHost, port)) {
            this._externalProcess = true;
            this._outputChannel.appendLine(
                `[BackendProcessManager] External backend detected at ${resolvedHost}:${port} — skipping spawn.`,
            );
            return;
        }

        // Discover Python
        let pythonPath: string;
        try {
            pythonPath = await findPythonInterpreter();
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._outputChannel.appendLine(`[BackendProcessManager] ${message}`);
            void vscode.window.showErrorMessage(
                `Video Documenter: ${message}\n\nInstall Python 3.10+ from https://www.python.org and reload VS Code.`,
            );
            return;
        }

        this._outputChannel.appendLine(
            `[BackendProcessManager] Starting backend: ${pythonPath} -m src.main (cwd: ${backendPath})`,
        );

        const envVars: Record<string, string> = {
            ...process.env as Record<string, string>,
            HOST: resolvedHost,
            PORT: String(port),
            PROCESSING_MODE: getProcessingMode(),
            PYTHONIOENCODING: 'utf-8',
        };

        // Add cloud-mode settings (only if non-empty to not override .env defaults)
        const conditionalVars: Record<string, string> = {
            FOUNDRY_PROJECT_ENDPOINT: getFoundryProjectEndpoint(),
            FOUNDRY_MODEL: getFoundryModel(),
            FOUNDRY_MODEL_MINI: getFoundryModelMini(),
            BLOB_ACCOUNT_URL: getBlobAccountUrl(),
            BLOB_CONTAINER_NAME: getBlobContainerName(),
            SPEECH_SERVICE_ENDPOINT: getSpeechServiceEndpoint(),
            SPEECH_SERVICE_REGION: getSpeechServiceRegion(),
            VIDEO_INDEXER_ACCOUNT_ID: getVideoIndexerAccountId(),
            VIDEO_INDEXER_RESOURCE_ID: getVideoIndexerResourceId(),
            VIDEO_INDEXER_LOCATION: getVideoIndexerLocation(),
            WHISPER_MODEL: getWhisperModel(),
            FFMPEG_PATH: getFfmpegPath(),
        };

        for (const [key, value] of Object.entries(conditionalVars)) {
            if (value) {
                envVars[key] = value;
            }
        }

        const child = spawn(pythonPath, ['-m', 'src.main'], {
            cwd: backendPath,
            env: envVars,
            stdio: ['ignore', 'pipe', 'pipe'],
        });

        child.stdout?.on('data', (data: Buffer) => {
            this._outputChannel.append(data.toString());
        });

        child.stderr?.on('data', (data: Buffer) => {
            this._outputChannel.append(data.toString());
        });

        child.on('error', (err) => {
            this._outputChannel.appendLine(`[BackendProcessManager] Spawn error: ${err.message}`);
            void vscode.window
                .showErrorMessage('Video Documenter: Failed to start the Python backend.', 'Open Output')
                .then((action) => {
                    if (action === 'Open Output') {
                        this._outputChannel.show();
                    }
                });
            this._process = undefined;
        });

        child.on('exit', (code, signal) => {
            const reason = signal ? `signal ${signal}` : `exit code ${code ?? 'unknown'}`;
            this._process = undefined;

            if (this._stopping) {
                this._outputChannel.appendLine('[BackendProcessManager] Backend stopped.');
                return;
            }

            this._outputChannel.appendLine(`[BackendProcessManager] Backend process exited (${reason}).`);

            // Notify user on unexpected exit (non-zero code, not killed by us)
            if (code !== null && code !== 0) {
                void vscode.window
                    .showWarningMessage(
                        `Video Documenter: Backend exited unexpectedly (${reason}).`,
                        'Open Output',
                        'Restart',
                    )
                    .then((action) => {
                        if (action === 'Open Output') {
                            this._outputChannel.show();
                        } else if (action === 'Restart') {
                            void this.start(backendPath, port, host);
                        }
                    });
            }
        });

        this._process = child;
    }

    /** Stop the backend process if we started it. */
    async stop(): Promise<void> {
        if (this._externalProcess) {
            this._outputChannel.appendLine(
                '[BackendProcessManager] Skipping stop — backend is externally managed.',
            );
            this._externalProcess = false;
            return;
        }

        const child = this._process;
        if (!child || child.killed) {
            this._process = undefined;
            return;
        }

        this._stopping = true;

        const pid = child.pid;
        this._outputChannel.appendLine(`[BackendProcessManager] Stopping backend (PID ${pid ?? '?'})…`);

        if (process.platform === 'win32') {
            // On Windows, kill the entire process tree BEFORE the parent.
            // taskkill /T /F walks the tree from the root PID downward; if
            // child.kill() runs first, the root PID dies and taskkill can no
            // longer find the grandchildren (e.g., uvicorn reload workers).
            if (pid !== undefined) {
                await new Promise<void>((resolve) => {
                    exec(`taskkill /T /F /PID ${pid}`, () => {
                        resolve();
                    });
                });
                // Update child.killed state (idempotent if process is already dead)
                child.kill();
            } else {
                child.kill();
            }
        } else {
            // On Unix, send SIGTERM first, then SIGKILL after 5 s
            child.kill('SIGTERM');
            const killed = await this.waitForExit(child, 5000);
            if (!killed) {
                child.kill('SIGKILL');
            }
        }

        this._process = undefined;
    }

    /** Returns `true` when a managed or external backend process is alive. */
    isRunning(): boolean {
        if (this._externalProcess) {
            return true;
        }
        return this._process !== undefined && !this._process.killed;
    }

    /** Expose the output channel for external consumers. */
    getOutputChannel(): vscode.OutputChannel {
        return this._outputChannel;
    }

    /** Dispose the manager — stops the backend and cleans up the output channel. */
    dispose(): void {
        // Remove the process.exit safety-net listener
        if (this._exitHandler) {
            process.removeListener('exit', this._exitHandler);
            this._exitHandler = undefined;
        }

        this._stopping = true;
        // Synchronously kill child to guarantee cleanup during VS Code shutdown
        this._killSync();
        this._outputChannel.dispose();
    }

    // ── Private helpers ────────────────────────────────────────────────────

    /**
     * Synchronously kill the managed child process and its tree.
     * Used in `dispose()` and `process.on('exit')` where async work is unreliable.
     */
    private _killSync(): void {
        const child = this._process;
        if (!child || child.killed) {
            this._process = undefined;
            return;
        }

        const pid = child.pid;
        const isWin = process.platform === 'win32';
        this._outputChannel.appendLine(
            `[BackendProcessManager] Killing backend ${isWin ? 'process tree' : 'process'} (PID ${pid ?? '?'})…`,
        );

        if (pid !== undefined && isWin) {
            // Kill the entire process tree BEFORE the parent. taskkill /T /F
            // walks from the root PID downward; if child.kill() runs first,
            // the root dies and grandchildren (uvicorn reload workers) orphan.
            try {
                execSync(`taskkill /T /F /PID ${pid}`, { stdio: 'ignore' });
            } catch {
                // Process may have already exited — fall back to direct kill
                child.kill();
            }
        } else {
            child.kill();
        }
        this._process = undefined;
    }

    /** Probe the health endpoint. Returns `true` when the backend responds 200. */
    private async isHealthy(host: string, port: number): Promise<boolean> {
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 2000);
            const res = await fetch(`http://${host}:${port}/api/v1/health`, {
                signal: controller.signal,
            });
            clearTimeout(timeout);
            return res.ok;
        } catch {
            return false;
        }
    }

    /** Wait up to `ms` milliseconds for the process to exit. */
    private waitForExit(child: ChildProcess, ms: number): Promise<boolean> {
        return new Promise((resolve) => {
            const timer = setTimeout(() => {
                resolve(false);
            }, ms);

            child.once('exit', () => {
                clearTimeout(timer);
                resolve(true);
            });
        });
    }
}
