import * as vscode from 'vscode';
import { BackendClient } from './api/backendClient';
import { createStateManager } from './utils/conversationState';
import { createOutputManager } from './utils/outputManager';
import { handleAnalyze } from './handlers/analyzeHandler';
import { handleGenerate } from './handlers/generateHandler';
import { handlePlan } from './handlers/planHandler';
import { handleEdit } from './handlers/editHandler';
import { handleSave } from './handlers/saveHandler';
import { handleStatus } from './handlers/statusHandler';
import { handleConversation } from './handlers/conversationHandler';
import { handlePolish } from './handlers/polishHandler';

export interface ChatHandlerResult {
    handler: vscode.ChatRequestHandler;
    client: BackendClient;
}

export function createChatHandler(
    extensionContext: vscode.ExtensionContext
): ChatHandlerResult {
    const client = new BackendClient();
    const stateManager = createStateManager(extensionContext);
    const outputManager = createOutputManager();

    const handler: vscode.ChatRequestHandler = async (
        request: vscode.ChatRequest,
        _context: vscode.ChatContext,
        stream: vscode.ChatResponseStream,
        token: vscode.CancellationToken
    ): Promise<vscode.ChatResult> => {
        const command = request.command;

        if (command === 'plan') {
            return handlePlan(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'analyze') {
            return handleAnalyze(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'generate') {
            return handleGenerate(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'edit' || command === 'refine') {
            return handleEdit(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'save') {
            return handleSave(request, stream, token, client, stateManager, outputManager);
        } else if (command === 'status') {
            return handleStatus(stream, client, stateManager);
        } else if (command === 'polish') {
            return handlePolish(request, stream, token, client, stateManager, outputManager);
        }

        return handleConversation(request, stream, token, client, stateManager, outputManager);
    };

    return { handler, client };
}
