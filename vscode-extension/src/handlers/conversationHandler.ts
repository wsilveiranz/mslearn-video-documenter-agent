import * as vscode from 'vscode';
import { BackendClient } from '../api/backendClient';
import { ConversationStateManager, ConversationState } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';
import { classifyIntentFast, parseLlmClassification, ConversationIntent } from '../utils/intentClassification';
import { handleEdit } from './editHandler';
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
            'IMPORTANT: "rename", "move", "reorganize", and "reformat" are NOT save or refine operations — always classify them as "general".\n\n' +
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

function buildStateContext(state: Readonly<ConversationState>): string {
    const parts: string[] = [];

    if (state.currentVideoId) {
        parts.push(`Video loaded: ID ${state.currentVideoId}`);
        if (state.currentVideoPath) {
            // Show just the filename, not the full path (privacy)
            const filename = state.currentVideoPath.split(/[\\/]/).pop() || state.currentVideoPath;
            parts.push(`Video file: ${filename}`);
        }
    }

    parts.push(`Current stage: ${state.currentStage}`);

    if (state.lastDocType) {
        parts.push(`Document type: ${state.lastDocType}`);
    }

    if (state.currentDocumentId) {
        parts.push(`Generated document: ID ${state.currentDocumentId}`);
    }

    if (state.metadata) {
        const meta: string[] = [];
        if (state.metadata.author) meta.push(`author: ${state.metadata.author}`);
        if (state.metadata.msService) meta.push(`ms.service: ${state.metadata.msService}`);
        if (meta.length > 0) {
            parts.push(`Metadata: ${meta.join(', ')}`);
        }
    }

    if (state.savedFilename) {
        parts.push(`Saved as: ${state.savedFilename}`);
    }

    return parts.join('\n');
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
                stream.markdown('*Treating your message as edit feedback...*\n\n');
                return handleEdit(request, stream, token, client, stateManager, outputManager);
            case 'general':
                // Fall through to general conversation below
                break;
        }
    }

    // General conversation — use the LLM
    const stateContext = buildStateContext(state);

    const systemPrompt =
        'You are the MS Learn Video Documenter agent. You help users create ' +
        'Microsoft Learn-style documentation from screen recording videos. ' +
        'You can analyze videos, generate documentation in various MS Learn formats ' +
        '(Quickstart, Tutorial, How-to, Concept, Overview), and refine generated content. ' +
        'Available commands: /plan, /analyze, /generate, /edit, /save, /status. ' +
        'Keep responses concise and helpful.\n\n' +
        '## Current Session State\n' +
        stateContext + '\n\n' +
        'Use the session state above to answer questions about what has been done in this session. ' +
        'If a video has been loaded and analyzed, acknowledge that. ' +
        'If a document has been generated, you can reference it. ' +
        'Do not deny actions that the session state shows have been completed.';

    const messages = [
        vscode.LanguageModelChatMessage.User(systemPrompt),
        vscode.LanguageModelChatMessage.User(request.prompt),
    ];

    const chatResponse = await request.model.sendRequest(messages, {}, token);

    for await (const fragment of chatResponse.text) {
        stream.markdown(fragment);
    }

    return { metadata: { command: '' } };
}
