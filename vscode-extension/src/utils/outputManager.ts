import * as vscode from 'vscode';
import * as path from 'path';
import { getOutputDirectory, getAutoOpenPreview } from './config';

/** Strip unsafe characters from a user-provided markdown filename. */
export function sanitizeFilename(filename: string): string {
    let name = filename
        .trim()
        .replace(/^["']+|["']+$/g, '')   // strip surrounding quotes
        .replace(/\.\./g, '')             // strip .. segments
        .replace(/[/\\]/g, '')            // strip path separators
        .trim();

    if (!name.endsWith('.md')) {
        name = name ? `${name}.md` : 'document.md';
    }

    // Fallback if name is empty or reduced to just ".md"
    if (!name || name === '.md') {
        name = 'document.md';
    }

    return name;
}

/** Validate outputDirectory is relative and doesn't escape workspace. */
function sanitizeOutputDir(dir: string): string {
    if (path.isAbsolute(dir)) {
        throw new Error(`outputDirectory must be a relative path (got "${dir}")`);
    }
    const normalized = path.normalize(dir);
    if (normalized.startsWith('..') || normalized.includes(`${path.sep}..`)) {
        throw new Error(`outputDirectory must not traverse outside the workspace (got "${dir}")`);
    }
    return normalized;
}

export interface MediaFile {
    filename: string;
    sourcePath: string;
}

export class OutputManager {
    /**
     * Save a generated document and its media files to the workspace.
     * Uses vscode.workspace.fs for remote workspace compatibility.
     * Returns the URI of the saved markdown file.
     */
    async saveDocument(
        documentId: string,
        markdownContent: string,
        mediaFiles: MediaFile[] = [],
        filename?: string,
    ): Promise<vscode.Uri> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open. Please open a folder first.');
        }

        const outputDir = sanitizeOutputDir(getOutputDirectory());
        const baseDirUri = vscode.Uri.joinPath(workspaceFolder.uri, outputDir);

        // Create output directory (createDirectory is recursive and no-ops if exists)
        await vscode.workspace.fs.createDirectory(baseDirUri);

        // Save markdown file (use provided filename or fall back to documentId)
        const mdFileName = filename ? sanitizeFilename(filename) : `${documentId}.md`;
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

        return mdFileUri;
    }

    /**
     * Open a document in the VS Code editor.
     */
    async openDocument(uri: vscode.Uri): Promise<vscode.TextEditor> {
        const doc = await vscode.workspace.openTextDocument(uri);
        return vscode.window.showTextDocument(doc, vscode.ViewColumn.One);
    }

    /**
     * Open VS Code's built-in markdown preview side-by-side.
     * Phase 3 will upgrade this to Learn Preview when Learn Authoring Pack is a dependency.
     */
    async openPreview(uri: vscode.Uri): Promise<void> {
        if (!getAutoOpenPreview()) {
            return;
        }

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
        mediaFiles: MediaFile[] = [],
        filename?: string,
    ): Promise<vscode.Uri> {
        const fileUri = await this.saveDocument(documentId, markdownContent, mediaFiles, filename);
        await this.openDocument(fileUri);
        await this.openPreview(fileUri);
        return fileUri;
    }

    /**
     * Update an existing document in the workspace (for refinements).
     */
    async updateDocument(documentId: string, markdownContent: string, filename?: string): Promise<vscode.Uri> {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            throw new Error('No workspace folder open.');
        }

        const outputDir = sanitizeOutputDir(getOutputDirectory());
        const baseDirUri = vscode.Uri.joinPath(workspaceFolder.uri, outputDir);

        // Ensure output directory exists (may have been removed since initial save)
        await vscode.workspace.fs.createDirectory(baseDirUri);

        const mdFileName = filename ? sanitizeFilename(filename) : `${documentId}.md`;
        const mdFileUri = vscode.Uri.joinPath(baseDirUri, mdFileName);
        await vscode.workspace.fs.writeFile(mdFileUri, Buffer.from(markdownContent, 'utf-8'));
        return mdFileUri;
    }
}

export function createOutputManager(): OutputManager {
    return new OutputManager();
}
