import * as path from 'node:path';
import * as vscode from 'vscode';
import { createChatHandler } from './chatHandler';
import { registerAnalyzeFileCommand } from './commands/analyzeFile';
import { LmProxyServer } from './api/lmProxyServer';
import { BackendProcessManager } from './services/backendProcessManager';
import { getBackendUrl, getAutoStartBackend, getBackendPath } from './utils/config';

let lmProxyServer: LmProxyServer | undefined;
let backendManager: BackendProcessManager | undefined;

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

export async function activate(context: vscode.ExtensionContext) {
    try {
        const handler = createChatHandler(context);

        const participant = vscode.chat.createChatParticipant(
            'video-documenter.agent',
            handler
        );
        participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'icon.png');

        registerAnalyzeFileCommand(context);

        const backendUrl = getBackendUrl();
        let backendHealthy = false;

        // Auto-start backend if enabled
        if (getAutoStartBackend()) {
            const parsed = new URL(backendUrl);
            const port = parsed.port ? parseInt(parsed.port, 10) : 8000;
            const host = parsed.hostname;

            const configuredPath = getBackendPath();
            const resolvedPath = configuredPath
                ? configuredPath
                : path.join(context.extensionUri.fsPath, '..', 'backend');

            backendManager = new BackendProcessManager();

            await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification, title: 'Video Documenter' },
                async (progress) => {
                    progress.report({ message: 'Starting backend...' });
                    await backendManager!.start(resolvedPath, port, host);

                    progress.report({ message: 'Waiting for backend to be ready...' });
                    backendHealthy = await waitForBackendHealth(backendUrl);

                    if (!backendHealthy) {
                        void vscode.window.showErrorMessage(
                            'Video Documenter: Backend failed to start within 30s.',
                            'Open Output'
                        ).then(action => {
                            if (action === 'Open Output') { backendManager?.getOutputChannel().show(); }
                        });
                    }
                }
            );
        }

        // Start LM Proxy if enabled
        const config = vscode.workspace.getConfiguration('video-documenter');
        if (config.get<boolean>('useCopilotModels', true)) {
            const preferredPort = config.get<number>('lmProxyPort', 0);
            lmProxyServer = new LmProxyServer();
            try {
                const proxyPort = await lmProxyServer.start(preferredPort);
                console.log(`[video-documenter] LM Proxy started on port ${proxyPort}`);

                // Notify backend of the proxy URL only after health is confirmed
                if (backendHealthy || !getAutoStartBackend()) {
                    fetch(`${backendUrl}/api/v1/config/lm-proxy`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ proxy_url: `http://localhost:${proxyPort}` }),
                    }).catch(err => {
                        console.warn('[video-documenter] Failed to notify backend of LM Proxy:', err);
                    });
                }
            } catch (err) {
                console.warn('[video-documenter] LM Proxy failed to start:', err);
                lmProxyServer = undefined;
            }
        }

        context.subscriptions.push(participant);
        context.subscriptions.push({ dispose: () => lmProxyServer?.stop() });
        if (backendManager) {
            context.subscriptions.push(backendManager);
        }
        console.log('[video-documenter] Extension activated successfully');
    } catch (error) {
        console.error('[video-documenter] Activation failed:', error);
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
}
