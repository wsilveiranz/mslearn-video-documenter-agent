import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';
import { extractTargetPath, resolveTargetPathPure } from '../utils/intentClassification';

/**
 * Resolve the target path using the pure resolver + runtime checks.
 */
function resolveTargetPath(targetPath: string, documentId: string): string {
    const isAbs = path.isAbsolute(targetPath);
    const isDir = targetPath.endsWith(path.sep) || targetPath.endsWith('/') ||
        (fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory());
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

    return resolveTargetPathPure(targetPath, documentId, isAbs, isDir, workspaceRoot);
}

export async function handleSave(
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
            '💾 No document to save. Please generate a document first:\n\n' +
            '```\n@video-documenter /generate\n```'
        );
        return { metadata: { command: 'save' } };
    }

    const prompt = request.prompt.trim();

    // Determine target path
    let targetPath = extractTargetPath(prompt);

    if (!targetPath) {
        // No path found in prompt — offer a file dialog
        const uri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file(`${state.currentDocumentId}.md`),
            filters: { 'Markdown': ['md'], 'All Files': ['*'] },
            title: 'Save generated document',
        });

        if (!uri) {
            stream.markdown('💾 Save cancelled.');
            return { metadata: { command: 'save' } };
        }

        targetPath = uri.fsPath;
    }

    const resolvedPath = resolveTargetPath(targetPath, state.currentDocumentId);

    try {
        // Fetch the latest document content
        stream.progress('Fetching document...');
        const doc = await client.getDocument(state.currentDocumentId);

        // Ensure parent directory exists
        const parentDir = path.dirname(resolvedPath);
        if (!fs.existsSync(parentDir)) {
            fs.mkdirSync(parentDir, { recursive: true });
        }

        // Write the file
        fs.writeFileSync(resolvedPath, doc.markdown_content, 'utf-8');

        stream.markdown(
            `✅ **Document saved**\n\n` +
            `| Field | Value |\n` +
            `|-------|-------|\n` +
            `| Path | \`${resolvedPath}\` |\n` +
            `| Word count | ${doc.word_count} |\n` +
            `| Revision | ${doc.revision_number} |\n`
        );

        // Offer to open the file
        const openAction = 'Open in editor';
        const choice = await vscode.window.showInformationMessage(
            `Document saved to ${resolvedPath}`,
            openAction
        );
        if (choice === openAction) {
            await outputManager.openDocument(resolvedPath);
        }
    } catch (error) {
        if (error instanceof BackendError) {
            stream.markdown(`❌ Could not fetch document: ${error.detail}`);
        } else {
            stream.markdown(
                `❌ Save failed: ${error instanceof Error ? error.message : String(error)}`
            );
        }
    }

    return { metadata: { command: 'save' } };
}
