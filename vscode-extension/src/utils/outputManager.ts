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
        .replace(/[:<>*?"|]/g, '')        // strip Windows-invalid characters
        .trim();

    if (!name.endsWith('.md')) {
        name = name ? `${name}.md` : 'document.md';
    }

    // Strip trailing dots and spaces from stem (Windows silently removes them, causing confusion)
    const strippedStem = name.slice(0, -3).replace(/[\s.]+$/, '');
    name = strippedStem ? `${strippedStem}.md` : 'document.md';

    // Fallback if name is empty or reduced to just ".md"
    if (!name || name === '.md') {
        name = 'document.md';
    }

    // Prefix reserved Windows device names to prevent filesystem conflicts
    const reserved = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;
    const stem = name.slice(0, -3);
    if (reserved.test(stem)) {
        name = `_${name}`;
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
    data: Uint8Array;
    outputPath?: string;  // e.g., "./media/article-slug/image-name.jpg"
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

        // Save media files, preserving subdirectory structure from outputPath
        if (mediaFiles.length > 0) {
            for (const media of mediaFiles) {
                // Determine relative path from outputPath, falling back to flat media/
                let relativePath: string;
                if (media.outputPath) {
                    // outputPath is like "./media/article-slug/image.jpg" — strip leading "./"
                    relativePath = media.outputPath.replace(/^\.\//, '');
                } else {
                    relativePath = `media/${media.filename}`;
                }

                // Security: reject path traversal and absolute paths
                if (relativePath.startsWith('/') || relativePath.startsWith('\\')
                    || relativePath.includes('..')
                    || /^[a-zA-Z]:/.test(relativePath)) {
                    relativePath = `media/${media.filename}`;
                }

                const destUri = vscode.Uri.joinPath(baseDirUri, relativePath);
                // Ensure parent directory exists (handles article-specific subfolders)
                const lastSlash = relativePath.lastIndexOf('/');
                if (lastSlash > 0) {
                    const parentDir = relativePath.substring(0, lastSlash);
                    await vscode.workspace.fs.createDirectory(vscode.Uri.joinPath(baseDirUri, parentDir));
                }

                try {
                    await vscode.workspace.fs.writeFile(destUri, media.data);
                } catch {
                    console.warn(`Failed to save media file: ${media.filename}`);
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
