import * as vscode from 'vscode';
import { getOutputDirectory, getAutoOpenPreview } from './config';

export interface MediaFile {
    filename: string;
    sourcePath: string;
}

export class OutputManager {
    /**
     * Save a generated document and its media files to the workspace.
     * Uses vscode.workspace.fs for remote workspace compatibility.
     * Returns the path of the saved markdown file.
     */
    async saveDocument(
        documentId: string,
        markdownContent: string,
        mediaFiles: MediaFile[] = []
    ): Promise<string> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open. Please open a folder first.');
        }

        const outputDir = getOutputDirectory();
        const baseDirUri = vscode.Uri.joinPath(workspaceFolder.uri, outputDir);

        // Create output directory (createDirectory is recursive and no-ops if exists)
        await vscode.workspace.fs.createDirectory(baseDirUri);

        // Save markdown file
        const mdFileName = `${documentId}.md`;
        const mdFileUri = vscode.Uri.joinPath(baseDirUri, mdFileName);
        await vscode.workspace.fs.writeFile(mdFileUri, Buffer.from(markdownContent, 'utf-8'));

        // Save media files
        if (mediaFiles.length > 0) {
            const mediaDirUri = vscode.Uri.joinPath(baseDirUri, 'media');
            await vscode.workspace.fs.createDirectory(mediaDirUri);

            for (const media of mediaFiles) {
                const destUri = vscode.Uri.joinPath(mediaDirUri, media.filename);
                try {
                    const sourceUri = vscode.Uri.file(media.sourcePath);
                    await vscode.workspace.fs.copy(sourceUri, destUri, { overwrite: true });
                } catch {
                    // Log but don't fail if a media file can't be copied
                    console.warn(`Failed to copy media file: ${media.sourcePath}`);
                }
            }
        }

        return mdFileUri.fsPath;
    }

    /**
     * Open a markdown file in the VS Code editor.
     */
    async openDocument(filePath: string): Promise<vscode.TextEditor> {
        const uri = vscode.Uri.file(filePath);
        const doc = await vscode.workspace.openTextDocument(uri);
        return vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
    }

    /**
     * Open VS Code's built-in markdown preview side-by-side.
     * Phase 3 will upgrade this to Learn Preview when Learn Authoring Pack is a dependency.
     */
    async openPreview(filePath: string): Promise<void> {
        if (!getAutoOpenPreview()) {
            return;
        }

        const uri = vscode.Uri.file(filePath);

        // First ensure the document is open
        await vscode.workspace.openTextDocument(uri);

        // Open the built-in markdown preview to the side
        await vscode.commands.executeCommand('markdown.showPreviewToSide', uri);
    }

    /**
     * Save document, open in editor, and optionally show preview.
     * Convenience method combining all output steps.
     */
    async saveAndOpen(
        documentId: string,
        markdownContent: string,
        mediaFiles: MediaFile[] = []
    ): Promise<string> {
        const filePath = await this.saveDocument(documentId, markdownContent, mediaFiles);
        await this.openDocument(filePath);
        await this.openPreview(filePath);
        return filePath;
    }

    /**
     * Update an existing document in the workspace (for refinements).
     */
    async updateDocument(documentId: string, markdownContent: string): Promise<string> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open.');
        }

        const outputDir = getOutputDirectory();
        const mdFileUri = vscode.Uri.joinPath(workspaceFolder.uri, outputDir, `${documentId}.md`);

        await vscode.workspace.fs.writeFile(mdFileUri, Buffer.from(markdownContent, 'utf-8'));
        return mdFileUri.fsPath;
    }
}

export function createOutputManager(): OutputManager {
    return new OutputManager();
}
