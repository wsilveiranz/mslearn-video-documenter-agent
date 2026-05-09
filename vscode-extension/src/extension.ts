import * as vscode from 'vscode';
import { createChatHandler } from './chatHandler';
import { registerAnalyzeFileCommand } from './commands/analyzeFile';

export function activate(context: vscode.ExtensionContext) {
    const handler = createChatHandler(context);

    const participant = vscode.chat.createChatParticipant(
        'video-documenter.agent',
        handler
    );
    participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'media', 'icon.png');

    registerAnalyzeFileCommand(context);

    context.subscriptions.push(participant);
}

export function deactivate() {}
