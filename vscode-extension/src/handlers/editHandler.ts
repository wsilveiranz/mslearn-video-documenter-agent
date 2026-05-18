import * as vscode from 'vscode';
import { BackendClient, BackendError, DocumentResponse } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';
import { formatElapsed } from '../utils/progress';
import { getProgressUpdateIntervalMs } from '../utils/config';

/**
 * Produce a human-readable summary of what changed between two Markdown documents.
 * Compares at the heading level (H1–H4) and reports added, removed, and modified sections.
 */
function summarizeChanges(before: string, after: string): string {
    const extractHeadings = (md: string): string[] =>
        md.split('\n').filter(l => /^#{1,4}\s/.test(l)).map(l => l.trim());

    const oldHeadings = extractHeadings(before);
    const newHeadings = extractHeadings(after);

    const added = newHeadings.filter(h => !oldHeadings.includes(h));
    const removed = oldHeadings.filter(h => !newHeadings.includes(h));

    // Split by headings and compare section content
    const sectionContent = (md: string): Map<string, string> => {
        const map = new Map<string, string>();
        const parts = md.split(/^(#{1,4}\s.+)$/m);
        for (let i = 1; i < parts.length; i += 2) {
            map.set(parts[i].trim(), (parts[i + 1] ?? '').trim());
        }
        return map;
    };

    const oldSections = sectionContent(before);
    const newSections = sectionContent(after);
    const modified: string[] = [];
    for (const [heading, content] of newSections) {
        const old = oldSections.get(heading);
        if (old !== undefined && old !== content) {
            modified.push(heading);
        }
    }

    const lines: string[] = [];
    if (added.length) {
        lines.push('**Added sections:**');
        added.forEach(h => lines.push(`- ${h}`));
    }
    if (removed.length) {
        lines.push('**Removed sections:**');
        removed.forEach(h => lines.push(`- ${h}`));
    }
    if (modified.length) {
        lines.push('**Modified sections:**');
        modified.forEach(h => lines.push(`- ${h}`));
    }

    if (!lines.length) {
        // No structural changes — compare word counts for a basic signal
        const wc = (s: string) => s.split(/\s+/).filter(Boolean).length;
        const diff = wc(after) - wc(before);
        if (diff !== 0) {
            lines.push(`Content updated (${diff > 0 ? '+' : ''}${diff} words)`);
        } else {
            lines.push('Minor formatting or wording changes applied');
        }
    }

    return lines.join('\n');
}

export async function handleEdit(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    _token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager,
    outputManager: OutputManager
): Promise<vscode.ChatResult> {
    const state = stateManager.getState();

    if (!state.currentDocumentId) {
        stream.markdown(
            '✏️ No document to edit. Please generate a document first:\n\n' +
            '```\n@video-documenter /generate\n```'
        );
        return { metadata: { command: 'edit' } };
    }

    const feedback = request.prompt.trim();
    if (!feedback) {
        stream.markdown(
            '✏️ Please provide feedback for editing:\n\n' +
            '```\n@video-documenter /edit Make the introduction more concise\n```'
        );
        return { metadata: { command: 'edit' } };
    }

    try {
        stateManager.setStage('refining');
        stream.progress('Editing document...');

        // Capture current revision so we can detect when the backend update lands
        let currentRevision = 0;
        let originalContent = '';
        try {
            const current = await client.getDocument(state.currentDocumentId);
            currentRevision = current.revision_number;
            originalContent = current.markdown_content;
        } catch {
            // If we can't fetch the current revision, we'll accept the first result
        }

        const selectedModel = request.model?.id;

        await client.refineDocument(state.currentDocumentId, feedback, selectedModel);

        stream.progress('Applying changes...');

        // Poll until revision advances (refinement is async on the backend)
        let retries = 0;
        const maxRetries = 30; // 60 seconds max at 2s intervals
        let doc: DocumentResponse | null = null;
        const refineStartTime = Date.now();
        const refineProgressIntervalMs = getProgressUpdateIntervalMs();
        let lastRefineEmitTime = 0;

        while (retries < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            try {
                const fetched = await client.getDocument(state.currentDocumentId!);
                if (fetched.revision_number > currentRevision) {
                    doc = fetched;
                    break;
                }
            } catch {
                // Document not ready yet — keep polling
            }

            // Heartbeat with elapsed time
            const now = Date.now();
            if ((now - lastRefineEmitTime) >= refineProgressIntervalMs) {
                lastRefineEmitTime = now;
                stream.progress(`Editing document... (${formatElapsed(refineStartTime)})`);
            }

            retries++;
        }

        if (doc) {
            stateManager.setStage('generated');

            // Update the workspace file with edited content
            let savedPath: string | undefined;
            try {
                const savedUri = await outputManager.updateDocument(
                    state.currentDocumentId!,
                    doc.markdown_content,
                    state.savedFilename,
                );
                savedPath = savedUri.fsPath;
            } catch {
                // Non-fatal — file may not exist yet if user skipped /generate
            }

            const changeSummary = originalContent
                ? summarizeChanges(originalContent, doc.markdown_content)
                : 'Document updated';

            // Build eval score row if available
            let evalRow = '';
            if (doc.eval_scores) {
                const s = doc.eval_scores;
                const pct = (v: number) => `${Math.round(v * 100)}%`;
                const icon = s.passed ? '✅' : '⚠️';
                evalRow =
                    `| Quality score | ${icon} **${pct(s.overall)}** overall |\n` +
                    `| | Completeness ${pct(s.completeness)} · Accuracy ${pct(s.accuracy)} · Style ${pct(s.style_compliance)} · Readability ${pct(s.readability)} · Grounding ${pct(s.grounding)} |\n`;
            }

            const summary =
                `✅ **Document edited** (revision ${doc.revision_number})\n\n` +
                `${changeSummary}\n\n` +
                `| Field | Value |\n` +
                `|-------|-------|\n` +
                `| Word count | ${doc.word_count} |\n` +
                `| Revision | ${doc.revision_number} |\n` +
                (savedPath ? `| Saved to | \`${savedPath}\` |\n` : '') +
                evalRow +
                '\n💡 Check the updated document in the editor. Use `/edit` again for further changes.\n';

            stream.markdown(summary);
        } else {
            stateManager.setStage('generated');
            stream.markdown(
                '⚠️ Edit was submitted but could not verify completion. ' +
                'Use `/status` to check progress.'
            );
        }
    } catch (error) {
        stateManager.setStage('generated'); // Revert to generated state
        const message = error instanceof BackendError
            ? `Backend error: ${error.detail}`
            : `Error: ${error instanceof Error ? error.message : String(error)}`;
        stream.markdown(`❌ Edit failed: ${message}`);
    }

    return { metadata: { command: 'edit' } };
}
