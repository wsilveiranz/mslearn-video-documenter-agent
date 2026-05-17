import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';
import { extractTargetPath, resolveTargetPathPure } from '../utils/intentClassification';
import { getCompanionTips } from '../utils/companions';

/**
 * Resolve the target path using the pure resolver + runtime checks.
 * Note: /save targets user-specified local paths (e.g., C:\temp\),
 * so it uses file:// URIs. For remote workspace outputs, use /generate instead.
 */
function resolveTargetPath(targetPath: string, documentId: string): string {
    const isAbs = path.isAbsolute(targetPath);
    // Check if path is a directory: trailing separator OR existing directory on disk
    const isDir = targetPath.endsWith(path.sep) || targetPath.endsWith('/')
        || (fs.existsSync(targetPath) && fs.statSync(targetPath).isDirectory());
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
    let targetUri: vscode.Uri | undefined;

    const extracted = extractTargetPath(prompt);
    if (extracted) {
        const resolvedPath = resolveTargetPath(extracted, state.currentDocumentId);
        targetUri = vscode.Uri.file(resolvedPath);
    } else {
        // No path found in prompt — offer a file dialog
        const defaultDir = vscode.workspace.workspaceFolders?.[0]?.uri;
        const defaultName = `${state.currentDocumentId}.md`;
        const defaultUri = defaultDir
            ? vscode.Uri.joinPath(defaultDir, defaultName)
            : vscode.Uri.file(defaultName);
        targetUri = await vscode.window.showSaveDialog({
            defaultUri,
            filters: { 'Markdown': ['md'], 'All Files': ['*'] },
            title: 'Save generated document',
        });
    }

    if (!targetUri) {
        stream.markdown('💾 Save cancelled.');
        return { metadata: { command: 'save' } };
    }

    try {
        // Fetch the latest document content
        stream.progress('Fetching document...');
        const doc = await client.getDocument(state.currentDocumentId);

        // Ensure parent directory exists and write the file
        const parentDirUri = vscode.Uri.file(path.dirname(targetUri.fsPath));
        await vscode.workspace.fs.createDirectory(parentDirUri);
        await vscode.workspace.fs.writeFile(targetUri, Buffer.from(doc.markdown_content, 'utf-8'));

        // Download and save media files to a media subdirectory
        const docMediaFiles = doc.media_files ?? [];
        let mediaCopyFailures: string[] = [];
        if (docMediaFiles.length > 0) {
            const mediaDirUri = vscode.Uri.joinPath(
                vscode.Uri.file(path.dirname(targetUri.fsPath)),
                'media'
            );
            await vscode.workspace.fs.createDirectory(mediaDirUri);

            for (const mf of docMediaFiles) {
                const destUri = vscode.Uri.joinPath(mediaDirUri, mf.filename);
                try {
                    const data = await client.downloadMedia(state.currentDocumentId, mf.filename);
                    await vscode.workspace.fs.writeFile(destUri, data);
                } catch {
                    mediaCopyFailures.push(mf.filename);
                }
            }
        }

        const warnings = mediaCopyFailures.length > 0
            ? `\n\n⚠️ **${mediaCopyFailures.length} media file(s) could not be copied:** ${mediaCopyFailures.join(', ')}. ` +
              `Image references in the document may be broken.`
            : '';

        stream.markdown(
            `✅ **Document saved**\n\n` +
            `| Field | Value |\n` +
            `|-------|-------|\n` +
            `| Path | \`${targetUri.fsPath}\` |\n` +
            `| Word count | ${doc.word_count} |\n` +
            `| Revision | ${doc.revision_number} |\n` +
            warnings
        );
        const companionTips = getCompanionTips();
        if (companionTips) {
            stream.markdown(companionTips);
        }

        // Non-blocking notification — don't await to avoid freezing the chat
        void vscode.window.showInformationMessage(
            `Document saved to ${targetUri.fsPath}`,
            'Open in editor'
        ).then(choice => {
            if (choice === 'Open in editor') {
                outputManager.openDocument(targetUri!);
            }
        });
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
