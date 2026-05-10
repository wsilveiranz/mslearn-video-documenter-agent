import * as vscode from 'vscode';
import { BackendClient } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { handleRefine } from './refineHandler';

export async function handleConversation(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager
): Promise<vscode.ChatResult> {
    const state = stateManager.getState();

    // If a document is already generated, treat free-form text as refinement feedback
    if (state.currentStage === 'generated' && state.currentDocumentId) {
        stream.markdown('*Treating your message as refinement feedback...*\n\n');
        return handleRefine(request, stream, token, client, stateManager);
    }

    // Otherwise, use the LLM for general conversation
    const messages = [
        vscode.LanguageModelChatMessage.User(
            'You are the MS Learn Video Documenter agent. You help users create ' +
            'Microsoft Learn-style documentation from screen recording videos. ' +
            'You can analyze videos, generate documentation in various MS Learn formats ' +
            '(Quickstart, Tutorial, How-to, Concept, Overview), and refine generated content. ' +
            'Available commands: /analyze, /generate, /refine, /status. ' +
            'Keep responses concise and helpful.'
        ),
        vscode.LanguageModelChatMessage.User(request.prompt),
    ];

    const chatResponse = await request.model.sendRequest(messages, {}, token);

    for await (const fragment of chatResponse.text) {
        stream.markdown(fragment);
    }

    return { metadata: { command: '' } };
}
