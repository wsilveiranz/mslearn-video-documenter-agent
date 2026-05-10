import * as vscode from 'vscode';
import { BackendClient, BackendError, DocumentResponse } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';

export async function handleRefine(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    _token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager
): Promise<vscode.ChatResult> {
    const state = stateManager.getState();

    if (!state.currentDocumentId) {
        stream.markdown(
            '✏️ No document to refine. Please generate a document first:\n\n' +
            '```\n@video-documenter /generate\n```'
        );
        return { metadata: { command: 'refine' } };
    }

    const feedback = request.prompt.trim();
    if (!feedback) {
        stream.markdown(
            '✏️ Please provide feedback for refinement:\n\n' +
            '```\n@video-documenter /refine Make the introduction more concise\n```'
        );
        return { metadata: { command: 'refine' } };
    }

    try {
        stateManager.setStage('refining');
        stream.progress('Refining document...');

        await client.refineDocument(state.currentDocumentId, feedback);

        stream.progress('Applying changes...');

        // Poll for the updated document (refinement is async)
        let retries = 0;
        const maxRetries = 30; // 60 seconds max at 2s intervals
        let doc: DocumentResponse | null = null;

        while (retries < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            try {
                doc = await client.getDocument(state.currentDocumentId!);
                break;
            } catch {
                retries++;
            }
        }

        if (doc) {
            stateManager.setStage('generated');
            stream.markdown(
                `✅ **Document refined** (revision ${doc.revision_number})\n\n` +
                `**Word count:** ${doc.word_count}\n\n` +
                '---\n\n' +
                doc.markdown_content.substring(0, 2000) +
                (doc.markdown_content.length > 2000
                    ? '\n\n*... (truncated in chat — full document saved to workspace)*'
                    : '')
            );
        } else {
            stateManager.setStage('generated');
            stream.markdown(
                '⚠️ Refinement was submitted but could not verify completion. ' +
                'Use `/status` to check progress.'
            );
        }
    } catch (error) {
        stateManager.setStage('generated'); // Revert to generated state
        const message = error instanceof BackendError
            ? `Backend error: ${error.detail}`
            : `Error: ${error instanceof Error ? error.message : String(error)}`;
        stream.markdown(`❌ Refinement failed: ${message}`);
    }

    return { metadata: { command: 'refine' } };
}
