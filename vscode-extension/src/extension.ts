import * as fs from 'node:fs';
import * as path from 'node:path';
import * as vscode from 'vscode';
import { createChatHandler } from './chatHandler';
import { BackendClient } from './api/backendClient';
import { registerAnalyzeFileCommand } from './commands/analyzeFile';
import { LmProxyServer } from './api/lmProxyServer';
import { BackendProcessManager } from './services/backendProcessManager';
import { getBackendUrl, getAutoStartBackend, getBackendPath, getProcessingMode } from './utils/config';
import { PrerequisiteManager } from './services/prerequisiteManager';
import { validateSettings } from './utils/settingsValidation';

let lmProxyServer: LmProxyServer | undefined;
let backendManager: BackendProcessManager | undefined;
let prerequisiteManager: PrerequisiteManager | undefined;

async function waitForBackendHealth(baseUrl: string, timeoutMs: number = 30000): Promise<boolean> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        try {
            const res = await fetch(`${baseUrl}/api/v1/health`, {
                signal: AbortSignal.timeout(2000),
            });
            if (res.ok) { return true; }
        } catch {
            // not ready yet
        }
        await new Promise(r => setTimeout(r, 500));
    }
    return false;
}

/**
 * Start the backend silently in the background so activation completes instantly.
 * Handles prerequisites, process spawn, health check, and LM proxy handshake.
 */
async function startBackendInBackground(
    resolvedPath: string, port: number, host: string, backendUrl: string, client: BackendClient,
): Promise<void> {
    try {
        const prereqStatus = await prerequisiteManager!.ensurePrerequisites(resolvedPath);

        if (!prereqStatus.python.available) {
            void vscode.window.showErrorMessage(
                'Video Documenter: Python is required but could not be found or installed. The backend will not start.',
                'Open Output',
            ).then(action => {
                if (action === 'Open Output') { prerequisiteManager?.getOutputChannel().show(); }
            });
            return;
        }

        if (!prereqStatus.backendDeps.installed) {
            void vscode.window.showErrorMessage(
                'Video Documenter: Backend dependencies could not be installed. The backend will not start.',
                'Open Output',
            ).then(action => {
                if (action === 'Open Output') { prerequisiteManager?.getOutputChannel().show(); }
            });
            return;
        }

        await backendManager!.start(resolvedPath, port, host);

        // Pass bootstrap token to client for session-secret authentication
        const token = backendManager!.bootstrapToken;
        if (token) {
            client.setBootstrapToken(token);
        }

        const healthy = await waitForBackendHealth(backendUrl);

        if (!healthy) {
            void vscode.window.showErrorMessage(
                'Video Documenter: Backend failed to start within 30s.',
                'Open Output',
            ).then(action => {
                if (action === 'Open Output') { backendManager?.getOutputChannel().show(); }
            });
            return;
        }

        console.log('[video-documenter] Backend is ready');

        // Perform LM proxy handshake now that backend is healthy
        if (lmProxyServer) {
            try {
                const proxyPort = lmProxyServer.getPort();
                const handshakeRes = await fetch(`${backendUrl}/api/v1/config/lm-proxy`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        proxy_url: `http://localhost:${proxyPort}`,
                        proxy_secret: lmProxyServer.getSecret(),
                    }),
                });
                if (!handshakeRes.ok) {
                    console.warn(`[video-documenter] LM proxy handshake returned HTTP ${handshakeRes.status}`);
                }
            } catch (err) {
                console.warn('[video-documenter] Failed to notify backend of LM Proxy:', err);
            }
        }
    } catch (err) {
        console.error('[video-documenter] Background backend startup failed:', err);
    }
}

export async function activate(context: vscode.ExtensionContext) {
    try {
        const { handler, client } = createChatHandler(context);

        const participant = vscode.chat.createChatParticipant(
            'video-documenter.agent',
            handler
        );
        participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'icon.png');

        registerAnalyzeFileCommand(context);

        // Validate settings (non-blocking warning if cloud mode settings are missing)
        validateSettings();

        const backendUrl = getBackendUrl();

        // Auto-start backend if enabled
        if (getAutoStartBackend()) {
            const parsed = new URL(backendUrl);
            const port = parsed.port ? parseInt(parsed.port, 10) : 8000;
            const host = parsed.hostname;

            const configuredPath = getBackendPath();
            let resolvedPath: string;
            if (configuredPath) {
                resolvedPath = configuredPath;
            } else {
                // Prefer bundled backend (VSIX install) over monorepo sibling layout (dev)
                const bundledPath = path.join(context.extensionUri.fsPath, 'backend');
                const monorepoPath = path.join(context.extensionUri.fsPath, '..', 'backend');
                // Detect bundled backend: PyInstaller exe or source layout
                const hasBundledExe = fs.existsSync(path.join(bundledPath, 'backend.exe'));
                const hasBundledSource = fs.existsSync(path.join(bundledPath, 'pyproject.toml'));
                resolvedPath = (hasBundledExe || hasBundledSource)
                    ? bundledPath
                    : monorepoPath;
            }

            backendManager = new BackendProcessManager();
            prerequisiteManager = new PrerequisiteManager();

            // Start LM Proxy BEFORE backend so it's available for the handshake
            // inside startBackendInBackground (which checks `if (lmProxyServer)`).
            const config = vscode.workspace.getConfiguration('video-documenter');
            if (config.get<boolean>('useCopilotModels', true) && getProcessingMode() === 'local') {
                const preferredPort = config.get<number>('lmProxyPort', 0);
                lmProxyServer = new LmProxyServer();
                try {
                    const proxyPort = await lmProxyServer.start(preferredPort);
                    console.log(`[video-documenter] LM Proxy started on port ${proxyPort}`);
                } catch (err) {
                    console.warn('[video-documenter] LM Proxy failed to start:', err);
                    lmProxyServer = undefined;
                }
            }

            // Start backend in the background so activation completes instantly.
            void startBackendInBackground(resolvedPath, port, host, backendUrl, client);
        }

        context.subscriptions.push(participant);
        context.subscriptions.push({ dispose: () => lmProxyServer?.stop() });
        if (prerequisiteManager) {
            context.subscriptions.push({ dispose: () => prerequisiteManager?.dispose() });
        }
        if (backendManager) {
            context.subscriptions.push(backendManager);
        }
        console.log('[video-documenter] Extension activated successfully');
    } catch (error) {
        console.error('[video-documenter] Activation failed:', error);
        // Clean up stray backend process if activation fails after startup
        if (backendManager) {
            await backendManager.stop();
            backendManager = undefined;
        }
        if (prerequisiteManager) {
            prerequisiteManager.dispose();
            prerequisiteManager = undefined;
        }
        throw error;
    }
}

export async function deactivate() {
    if (lmProxyServer) {
        await lmProxyServer.stop();
        lmProxyServer = undefined;
    }
    if (backendManager) {
        await backendManager.stop();
        backendManager = undefined;
    }
    if (prerequisiteManager) {
        prerequisiteManager.dispose();
        prerequisiteManager = undefined;
    }
}
