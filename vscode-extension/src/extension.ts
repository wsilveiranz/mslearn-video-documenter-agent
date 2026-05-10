import * as vscode from 'vscode';
import { createChatHandler } from './chatHandler';
import { registerAnalyzeFileCommand } from './commands/analyzeFile';

export function activate(context: vscode.ExtensionContext) {
    try {
        const handler = createChatHandler(context);

        const participant = vscode.chat.createChatParticipant(
            'video-documenter.agent',
            handler
        );
        participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'icon.png');

        registerAnalyzeFileCommand(context);

        context.subscriptions.push(participant);
        console.log('[video-documenter] Extension activated successfully');
    } catch (error) {
        console.error('[video-documenter] Activation failed:', error);
        throw error;
    }
}

export function deactivate() {}
