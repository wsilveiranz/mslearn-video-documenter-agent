import * as vscode from 'vscode';
import { BackendClient } from './api/backendClient';
import { ConversationStateManager, createStateManager } from './utils/conversationState';
import { OutputManager, createOutputManager } from './utils/outputManager';
import { handleAnalyze } from './handlers/analyzeHandler';
import { handleGenerate } from './handlers/generateHandler';
import { handleRefine } from './handlers/refineHandler';
import { handleSave } from './handlers/saveHandler';
import { handleStatus } from './handlers/statusHandler';
import { handleConversation } from './handlers/conversationHandler';

export function createChatHandler(
    extensionContext: vscode.ExtensionContext
): vscode.ChatRequestHandler {
    const client = new BackendClient();
    const stateManager = createStateManager(extensionContext);
    const outputManager = createOutputManager();

    return async (
        request: vscode.ChatRequest,
        _context: vscode.ChatContext,
        stream: vscode.ChatResponseStream,
        token: vscode.CancellationToken
    ): Promise<vscode.ChatResult> => {
        const command = request.command;

        if (command === 'analyze') {
            return handleAnalyze(request, stream, token, client, stateManager);
        } else if (command === 'generate') {
            return handleGenerate(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'refine') {
            return handleRefine(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'save') {
            return handleSave(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'status') {
            return handleStatus(stream, client, stateManager);
        }

        return handleConversation(request, stream, token, client, stateManager, outputManager);
    };
}
