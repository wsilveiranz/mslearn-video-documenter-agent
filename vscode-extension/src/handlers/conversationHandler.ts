import * as vscode from 'vscode';
import { BackendClient } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';
import { classifyIntentFast, parseLlmClassification, ConversationIntent } from '../utils/intentClassification';
import { handleRefine } from './refineHandler';
import { handleSave } from './saveHandler';

/**
 * Classify the user's intent using fast pattern matching.
 * Falls back to LLM classification only for ambiguous messages.
 */
async function classifyIntent(
    prompt: string,
    model: vscode.LanguageModelChat,
    token: vscode.CancellationToken
): Promise<ConversationIntent> {
    // Fast path: check save patterns
    const fast = classifyIntentFast(prompt);
    if (fast) {
        return fast;
    }

    // For ambiguous messages, use the LLM to classify
    const messages = [
        vscode.LanguageModelChatMessage.User(
            'Classify the following user message into exactly one category. ' +
            'The user has a generated document open.\n\n' +
            'Categories:\n' +
            '- "save": The user wants to save, export, or download the document to a specific file or directory path\n' +
            '- "refine": The user is providing feedback to improve, edit, or change the document content\n' +
            '- "general": The user is asking a question, requesting help, or making a request that is NOT about saving or refining the document (e.g., rename, explain, summarize, compare)\n\n' +
            'IMPORTANT: "rename", "move", "reorganize", and "reformat" are NOT save operations — classify them as "general" or "refine".\n\n' +
            'Respond with ONLY the category name (save, refine, or general). No explanation.\n\n' +
            `User message: "${prompt.trim()}"`
        ),
    ];

    try {
        const response = await model.sendRequest(messages, {}, token);
        let result = '';
        for await (const fragment of response.text) {
            result += fragment;
        }

        return parseLlmClassification(result);
    } catch {
        // If LLM classification fails, fall back to refinement (preserves original behavior)
        return 'refine';
    }
}

export async function handleConversation(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager,
    outputManager: OutputManager
): Promise<vscode.ChatResult> {
    const state = stateManager.getState();

    // If a document is generated, classify intent before routing
    if (state.currentStage === 'generated' && state.currentDocumentId) {
        const intent = await classifyIntent(request.prompt, request.model, token);

        switch (intent) {
            case 'save':
                return handleSave(request, stream, token, client, stateManager, outputManager);
            case 'refine':
                stream.markdown('*Treating your message as refinement feedback...*\n\n');
                return handleRefine(request, stream, token, client, stateManager, outputManager);
            case 'general':
                // Fall through to general conversation below
                break;
        }
    }

    // General conversation — use the LLM
    const messages = [
        vscode.LanguageModelChatMessage.User(
            'You are the MS Learn Video Documenter agent. You help users create ' +
            'Microsoft Learn-style documentation from screen recording videos. ' +
            'You can analyze videos, generate documentation in various MS Learn formats ' +
            '(Quickstart, Tutorial, How-to, Concept, Overview), and refine generated content. ' +
            'Available commands: /analyze, /generate, /refine, /save, /status. ' +
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
