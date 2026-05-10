import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';

/**
 * Extract a file-system path from the user's save request.
 * Handles prompts like "save to c:\temp\", "export to /home/user/docs", etc.
 */
function extractTargetPath(prompt: string): string | undefined {
    // Remove common save/export verbs to isolate the path
    const cleaned = prompt
        .replace(/^(please\s+)?/i, '')
        .replace(/^(save|export|copy|write|output)\s+(it\s+|the\s+(document|doc|file|markdown|md)\s+)?/i, '')
        .replace(/^(to|at|in|into|as)\s+/i, '')
        .trim();

    if (!cleaned) {
        return undefined;
    }

    // Remove surrounding quotes if present
    const unquoted = cleaned.replace(/^["']|["']$/g, '').trim();

    // Validate it looks like a filesystem path
    const isWindowsPath = /^[a-zA-Z]:[/\\]/.test(unquoted);
    const isUnixPath = unquoted.startsWith('/');
    const isRelativePath = unquoted.startsWith('.') || unquoted.includes(path.sep);

    if (isWindowsPath || isUnixPath || isRelativePath) {
        return unquoted;
    }

    // Could be just a filename like "output.md"
    if (/\.\w+$/.test(unquoted) || unquoted.endsWith(path.sep) || unquoted.endsWith('/')) {
        return unquoted;
    }

    return undefined;
}

/**
 * Resolve the target path, adding a filename if only a directory was given.
 */
function resolveTargetPath(targetPath: string, documentId: string): string {
    let resolved = targetPath;

    // Resolve relative paths against workspace
    if (!path.isAbsolute(resolved)) {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (workspaceFolder) {
            resolved = path.join(workspaceFolder.uri.fsPath, resolved);
        }
    }

    // If target is a directory (ends with separator or exists as directory), append filename
    if (resolved.endsWith(path.sep) || resolved.endsWith('/') || 
        (fs.existsSync(resolved) && fs.statSync(resolved).isDirectory())) {
        resolved = path.join(resolved, `${documentId}.md`);
    }

    // Ensure .md extension if no extension provided
    if (!path.extname(resolved)) {
        resolved += '.md';
    }

    return resolved;
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
