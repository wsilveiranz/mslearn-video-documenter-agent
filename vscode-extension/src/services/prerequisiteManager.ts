import { execSync, exec } from 'child_process';
import * as path from 'node:path';
import * as fs from 'node:fs';
import * as vscode from 'vscode';

// ── Types ────────────────────────────────────────────────────────────────────

export interface PrerequisiteStatus {
    python: { available: boolean; version?: string; path?: string };
    ffmpeg: { available: boolean; version?: string };
    backendDeps: { installed: boolean };
}

// ── Constants ────────────────────────────────────────────────────────────────

const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 10;
const PYTHON_INSTALL_URL = 'https://www.python.org/downloads/';
const FFMPEG_INSTALL_URL = 'https://ffmpeg.org/download.html';

// ── PrerequisiteManager ──────────────────────────────────────────────────────

export class PrerequisiteManager implements vscode.Disposable {
    private _outputChannel: vscode.OutputChannel;

    constructor() {
        this._outputChannel = vscode.window.createOutputChannel('Video Documenter Prerequisites');
    }

    /**
     * Check all prerequisites and offer to install missing ones.
     * Returns the final status after any installation attempts.
     */
    async ensurePrerequisites(backendPath: string): Promise<PrerequisiteStatus> {
        return vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'Video Documenter: Checking prerequisites…',
                cancellable: false,
            },
            async (progress) => {
                // 1. Python
                progress.report({ message: 'Checking Python…' });
                let pythonStatus = await this.checkPython();

                if (!pythonStatus.available) {
                    const installed = await this.installPython();
                    if (installed) {
                        pythonStatus = await this.checkPython();
                    }
                }

                // 2. FFmpeg
                progress.report({ message: 'Checking FFmpeg…' });
                let ffmpegStatus = await this.checkFfmpeg();

                if (!ffmpegStatus.available) {
                    const installed = await this.installFfmpeg();
                    if (installed) {
                        ffmpegStatus = await this.checkFfmpeg();
                    }
                }

                // 3. Backend dependencies
                progress.report({ message: 'Checking backend dependencies…' });
                let depsInstalled = false;

                if (pythonStatus.available && pythonStatus.path) {
                    depsInstalled = await this.ensureBackendDeps(backendPath, pythonStatus.path);
                } else {
                    this._log('Skipping backend dependency install — Python is not available.');
                }

                return {
                    python: pythonStatus,
                    ffmpeg: ffmpegStatus,
                    backendDeps: { installed: depsInstalled },
                };
            },
        );
    }

    /** Check if Python 3.10+ is available. */
    async checkPython(): Promise<{ available: boolean; version?: string; path?: string }> {
        // 1. Try VS Code Python extension API
        const pyExt = vscode.extensions.getExtension('ms-python.python');
        if (pyExt) {
            if (!pyExt.isActive) {
                try {
                    await pyExt.activate();
                } catch {
                    // activation may fail — continue with fallbacks
                }
            }
            const execDetails: { execCommand?: string[] } | undefined =
                pyExt.exports?.settings?.getExecutionDetails?.();
            const extPython = execDetails?.execCommand?.[0];
            if (extPython) {
                const result = this._tryParsePythonVersion(extPython);
                if (result) {
                    return result;
                }
            }
        }

        // 2. Try python3
        const py3 = this._tryParsePythonVersion('python3');
        if (py3) {
            return py3;
        }

        // 3. Try python
        const py = this._tryParsePythonVersion('python');
        if (py) {
            return py;
        }

        this._log('Python 3.10+ was not found on the system.');
        return { available: false };
    }

    /** Check if FFmpeg is available on PATH. */
    async checkFfmpeg(): Promise<{ available: boolean; version?: string }> {
        try {
            const output = execSync('ffmpeg -version', {
                encoding: 'utf-8',
                timeout: 10_000,
                stdio: ['ignore', 'pipe', 'pipe'],
            });
            // First line is typically: ffmpeg version N.N.N ...
            const firstLine = output.split('\n')[0]?.trim() ?? '';
            const versionMatch = /ffmpeg version (\S+)/i.exec(firstLine);
            const version = versionMatch?.[1] ?? 'unknown';
            this._log(`FFmpeg found: ${version}`);
            return { available: true, version };
        } catch {
            this._log('FFmpeg was not found on PATH.');
            return { available: false };
        }
    }

    /**
     * Ensure backend venv exists and dependencies are installed.
     * Returns `true` when deps are ready.
     */
    async ensureBackendDeps(backendPath: string, pythonPath: string): Promise<boolean> {
        const venvDir = path.join(backendPath, '.venv');
        const isWin = process.platform === 'win32';
        const pipPath = isWin
            ? path.join(venvDir, 'Scripts', 'pip.exe')
            : path.join(venvDir, 'bin', 'pip');

        try {
            // Create venv if it doesn't exist
            if (!fs.existsSync(venvDir)) {
                this._log(`Creating virtual environment at ${venvDir}…`);
                await this._execAsync(`"${pythonPath}" -m venv "${venvDir}"`);
                this._log('Virtual environment created.');
            } else {
                this._log(`Virtual environment already exists at ${venvDir}.`);
            }

            // Verify pip exists in the venv
            if (!fs.existsSync(pipPath)) {
                this._log(`pip not found at ${pipPath} — venv may be corrupted.`);
                void vscode.window.showWarningMessage(
                    `Video Documenter: pip not found in the virtual environment. ` +
                        `Try deleting "${venvDir}" and reloading VS Code.`,
                );
                return false;
            }

            // Install backend dependencies if not already present
            const venvPythonPath = isWin
                ? path.join(venvDir, 'Scripts', 'python.exe')
                : path.join(venvDir, 'bin', 'python');

            // Check if the backend package is already installed
            let alreadyInstalled = false;
            try {
                execSync(`"${venvPythonPath}" -c "import src"`, {
                    cwd: backendPath,
                    timeout: 10_000,
                    stdio: ['ignore', 'pipe', 'pipe'],
                });
                alreadyInstalled = true;
            } catch {
                // not installed yet
            }

            if (alreadyInstalled) {
                this._log('Backend dependencies already installed.');
                return true;
            }

            this._log(`Installing backend dependencies from ${backendPath}…`);
            await this._execAsync(`"${pipPath}" install -e "${backendPath}"`);
            this._log('Backend dependencies installed successfully.');
            return true;
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._log(`Failed to set up backend dependencies: ${message}`);
            void vscode.window.showWarningMessage(
                'Video Documenter: Failed to install backend dependencies. See the output channel for details.',
                'Open Output',
            ).then((action) => {
                if (action === 'Open Output') {
                    this._outputChannel.show();
                }
            });
            return false;
        }
    }

    /** Get the output channel for external consumers. */
    getOutputChannel(): vscode.OutputChannel {
        return this._outputChannel;
    }

    dispose(): void {
        this._outputChannel.dispose();
    }

    // ── Private: installation helpers ────────────────────────────────────────

    /** Offer to install Python via winget if missing. */
    private async installPython(): Promise<boolean> {
        if (process.platform !== 'win32') {
            void vscode.window.showWarningMessage(
                `Video Documenter: Python 3.10+ is required but was not found. ` +
                    `Install it from ${PYTHON_INSTALL_URL} and reload VS Code.`,
            );
            return false;
        }

        const action = await vscode.window.showInformationMessage(
            'Video Documenter: Python 3.11+ is required but was not found. Install via winget?',
            'Install',
            'Skip',
        );

        if (action !== 'Install') {
            this._log('User skipped Python installation.');
            return false;
        }

        try {
            this._log('Installing Python 3.11 via winget…');
            await this._execAsync(
                'winget install Python.Python.3.11 --accept-source-agreements --accept-package-agreements',
            );
            this._log('Python installation completed.');

            // Re-check availability — the user may need to restart VS Code
            const recheck = this._tryParsePythonVersion('python');
            if (!recheck) {
                void vscode.window.showInformationMessage(
                    'Video Documenter: Python was installed, but a VS Code restart may be required for PATH changes to take effect.',
                    'Restart VS Code',
                ).then((restartAction) => {
                    if (restartAction === 'Restart VS Code') {
                        void vscode.commands.executeCommand('workbench.action.reloadWindow');
                    }
                });
            }
            return true;
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._log(`Python installation failed: ${message}`);
            void vscode.window.showErrorMessage(
                `Video Documenter: Failed to install Python via winget. ` +
                    `Install manually from ${PYTHON_INSTALL_URL} and reload VS Code.`,
            );
            return false;
        }
    }

    /** Offer to install FFmpeg via winget if missing. */
    private async installFfmpeg(): Promise<boolean> {
        if (process.platform !== 'win32') {
            void vscode.window.showWarningMessage(
                `Video Documenter: FFmpeg is required but was not found. ` +
                    `Install it from ${FFMPEG_INSTALL_URL} and reload VS Code.`,
            );
            return false;
        }

        const action = await vscode.window.showInformationMessage(
            'Video Documenter: FFmpeg is required but was not found. Install via winget?',
            'Install',
            'Skip',
        );

        if (action !== 'Install') {
            this._log('User skipped FFmpeg installation.');
            return false;
        }

        try {
            this._log('Installing FFmpeg via winget…');
            await this._execAsync(
                'winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements',
            );
            this._log('FFmpeg installation completed.');

            // Attempt to discover the newly installed ffmpeg and add to PATH
            this._discoverFfmpegPath();

            return true;
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._log(`FFmpeg installation failed: ${message}`);
            void vscode.window.showErrorMessage(
                `Video Documenter: Failed to install FFmpeg via winget. ` +
                    `Install manually from ${FFMPEG_INSTALL_URL} and reload VS Code.`,
            );
            return false;
        }
    }

    // ── Private: utility methods ─────────────────────────────────────────────

    /**
     * Try to run `<cmd> --version`, parse the version, and verify it meets the
     * minimum requirement (3.10+). Returns status on success, `null` on failure.
     */
    private _tryParsePythonVersion(
        cmd: string,
    ): { available: boolean; version: string; path: string } | null {
        try {
            const output = execSync(`"${cmd}" --version`, {
                encoding: 'utf-8',
                timeout: 10_000,
                stdio: ['ignore', 'pipe', 'pipe'],
            });
            // Expected format: "Python 3.11.5"
            const match = /Python (\d+)\.(\d+)(?:\.(\d+))?/.exec(output);
            if (!match) {
                return null;
            }
            const major = parseInt(match[1], 10);
            const minor = parseInt(match[2], 10);
            const patch = match[3] ? parseInt(match[3], 10) : 0;
            const version = `${major}.${minor}.${patch}`;

            if (major < MIN_PYTHON_MAJOR || (major === MIN_PYTHON_MAJOR && minor < MIN_PYTHON_MINOR)) {
                this._log(`Python ${version} found at "${cmd}" but >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} is required.`);
                return null;
            }

            this._log(`Python ${version} found at "${cmd}".`);
            return { available: true, version, path: cmd };
        } catch {
            return null;
        }
    }

    /**
     * After winget installs FFmpeg, it may not be on PATH. Search the winget
     * packages directory for `ffmpeg.exe` and add the containing bin directory
     * to `process.env.PATH` for the current session.
     */
    private _discoverFfmpegPath(): void {
        const localAppData = process.env['LOCALAPPDATA'];
        if (!localAppData) {
            this._log('Cannot discover FFmpeg — %LOCALAPPDATA% is not set.');
            return;
        }

        const wingetPkgDir = path.join(localAppData, 'Microsoft', 'WinGet', 'Packages');
        if (!fs.existsSync(wingetPkgDir)) {
            this._log(`WinGet packages directory not found: ${wingetPkgDir}`);
            return;
        }

        // Find Gyan.FFmpeg* directories
        let entries: fs.Dirent[];
        try {
            entries = fs.readdirSync(wingetPkgDir, { withFileTypes: true });
        } catch {
            this._log(`Failed to read WinGet packages directory: ${wingetPkgDir}`);
            return;
        }

        const ffmpegDirs = entries
            .filter((e) => e.isDirectory() && e.name.startsWith('Gyan.FFmpeg'))
            .map((e) => path.join(wingetPkgDir, e.name));

        for (const dir of ffmpegDirs) {
            const found = this._findFileRecursive(dir, 'ffmpeg.exe', 5);
            if (found) {
                const binDir = path.dirname(found);
                const currentPath = process.env['PATH'] ?? '';
                if (!currentPath.toLowerCase().includes(binDir.toLowerCase())) {
                    process.env['PATH'] = `${binDir};${currentPath}`;
                    this._log(`Added FFmpeg to session PATH: ${binDir}`);
                }
                void vscode.window.showInformationMessage(
                    `Video Documenter: FFmpeg installed. You may need to restart VS Code for PATH changes to persist.`,
                );
                return;
            }
        }

        this._log('Could not locate ffmpeg.exe in WinGet packages directory after installation.');
        void vscode.window.showInformationMessage(
            'Video Documenter: FFmpeg was installed but could not be located on PATH. ' +
                'You may need to restart VS Code or add FFmpeg to your PATH manually.',
        );
    }

    /**
     * Recursively search for a file by name under `dir`, up to `maxDepth` levels.
     * Returns the full path to the first match, or `null` if not found.
     */
    private _findFileRecursive(dir: string, filename: string, maxDepth: number): string | null {
        if (maxDepth <= 0) {
            return null;
        }

        let entries: fs.Dirent[];
        try {
            entries = fs.readdirSync(dir, { withFileTypes: true });
        } catch {
            return null;
        }

        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.isFile() && entry.name.toLowerCase() === filename.toLowerCase()) {
                return fullPath;
            }
            if (entry.isDirectory()) {
                const found = this._findFileRecursive(fullPath, filename, maxDepth - 1);
                if (found) {
                    return found;
                }
            }
        }
        return null;
    }

    /**
     * Run a shell command asynchronously, streaming output to the output channel.
     * Rejects on non-zero exit code.
     */
    private _execAsync(command: string): Promise<string> {
        return new Promise((resolve, reject) => {
            const child = exec(command, { timeout: 300_000 }, (error, stdout, stderr) => {
                if (error) {
                    reject(error);
                    return;
                }
                resolve(stdout);
            });

            child.stdout?.on('data', (data: Buffer | string) => {
                this._outputChannel.append(data.toString());
            });

            child.stderr?.on('data', (data: Buffer | string) => {
                this._outputChannel.append(data.toString());
            });
        });
    }

    /** Write a timestamped message to the output channel. */
    private _log(message: string): void {
        this._outputChannel.appendLine(`[PrerequisiteManager] ${message}`);
    }
}
