import * as vscode from 'vscode';
import { BackendClient, BackendError, DocumentResponse } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';

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

export async function handleRefine(
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

        await client.refineDocument(state.currentDocumentId, feedback);

        stream.progress('Applying changes...');

        // Poll until revision advances (refinement is async on the backend)
        let retries = 0;
        const maxRetries = 30; // 60 seconds max at 2s intervals
        let doc: DocumentResponse | null = null;

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
            retries++;
        }

        if (doc) {
            stateManager.setStage('generated');

            // Update the workspace file with refined content
            let savedPath: string | undefined;
            try {
                const savedUri = await outputManager.updateDocument(state.currentDocumentId!, doc.markdown_content);
                savedPath = savedUri.fsPath;
            } catch {
                // Non-fatal — file may not exist yet if user skipped /generate
            }

            const changeSummary = originalContent
                ? summarizeChanges(originalContent, doc.markdown_content)
                : 'Document updated';

            const summary =
                `✅ **Document refined** (revision ${doc.revision_number})\n\n` +
                `${changeSummary}\n\n` +
                `| Field | Value |\n` +
                `|-------|-------|\n` +
                `| Word count | ${doc.word_count} |\n` +
                `| Revision | ${doc.revision_number} |\n` +
                (savedPath ? `| Saved to | \`${savedPath}\` |\n` : '') +
                '\n💡 Check the updated document in the editor. Use `/refine` again for further changes.\n';

            stream.markdown(summary);
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
