import * as vscode from 'vscode';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';

const STAGE_EMOJI: Record<string, string> = {
    queued: '⏳',
    ingesting: '📥',
    ingestion: '📥',
    ingestion_complete: '✅',
    extracting: '🔍',
    structuring: '📋',
    writing: '✍️',
    editing: '✏️',
    evaluating: '🔬',
    completed: '✅',
    failed: '❌',
    pipeline: '⚙️',
    refined: '✨',
};

export async function handleStatus(
    stream: vscode.ChatResponseStream,
    client: BackendClient,
    stateManager: ConversationStateManager
): Promise<vscode.ChatResult> {
    const state = stateManager.getState();

    if (!state.currentVideoId) {
        stream.markdown(
            '📊 **Status:** No active processing jobs.\n\n' +
            'Use `/analyze` to start processing a video.'
        );
        return { metadata: { command: 'status' } };
    }

    try {
        const status = await client.getVideoStatus(state.currentVideoId);
        const emoji = STAGE_EMOJI[status.current_stage] ?? '⏳';

        stream.markdown(
            `📊 **Processing Status**\n\n` +
            `| Field | Value |\n` +
            `|-------|-------|\n` +
            `| Video ID | \`${status.video_id}\` |\n` +
            `| Stage | ${emoji} ${status.current_stage} |\n` +
            `| Progress | Step ${status.step} of ${status.total_steps} |\n` +
            `| Status | ${status.status} |\n` +
            (status.document_id ? `| Document | \`${status.document_id}\` |\n` : '')
        );

        if (status.status === 'failed') {
            stream.markdown('\n⚠️ Processing failed. Try analyzing the video again with `/analyze`.');
        }
    } catch (error) {
        const message = error instanceof BackendError
            ? `Backend error: ${error.detail}`
            : `Error: ${error instanceof Error ? error.message : String(error)}`;
        stream.markdown(`❌ Could not fetch status: ${message}`);
    }

    return { metadata: { command: 'status' } };
}
