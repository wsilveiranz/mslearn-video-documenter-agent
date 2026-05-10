import * as vscode from 'vscode';
import { createChatHandler } from './chatHandler';
import { registerAnalyzeFileCommand } from './commands/analyzeFile';
import { LmProxyServer } from './api/lmProxyServer';
import { getBackendUrl } from './utils/config';

let lmProxyServer: LmProxyServer | undefined;

export function activate(context: vscode.ExtensionContext) {
    try {
        const handler = createChatHandler(context);

        const participant = vscode.chat.createChatParticipant(
            'video-documenter.agent',
            handler
        );
        participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'icon.png');

        registerAnalyzeFileCommand(context);

        // Start LM Proxy if enabled
        const config = vscode.workspace.getConfiguration('video-documenter');
        if (config.get<boolean>('useCopilotModels', true)) {
            const preferredPort = config.get<number>('lmProxyPort', 0);
            lmProxyServer = new LmProxyServer();
            lmProxyServer.start(preferredPort).then(port => {
                console.log(`[video-documenter] LM Proxy started on port ${port}`);

                // Notify backend of the proxy URL (fire-and-forget)
                const backendUrl = getBackendUrl();
                fetch(`${backendUrl}/api/v1/config/lm-proxy`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proxy_url: `http://localhost:${port}` }),
                }).catch(err => {
                    console.warn('[video-documenter] Failed to notify backend of LM Proxy:', err);
                });
            }).catch(err => {
                console.warn('[video-documenter] LM Proxy failed to start:', err);
                lmProxyServer = undefined;
            });
        }

        context.subscriptions.push(participant);
        context.subscriptions.push({ dispose: () => lmProxyServer?.stop() });
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
}
