import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { getOutputDirectory, getAutoOpenPreview } from './config';

export interface MediaFile {
    filename: string;
    sourcePath: string;
}

export class OutputManager {
    /**
     * Save a generated document and its media files to the workspace.
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
        const baseDir = path.join(workspaceFolder.uri.fsPath, outputDir);

        // Create output directory
        if (!fs.existsSync(baseDir)) {
            fs.mkdirSync(baseDir, { recursive: true });
        }

        // Save markdown file
        const mdFileName = `${documentId}.md`;
        const mdFilePath = path.join(baseDir, mdFileName);
        fs.writeFileSync(mdFilePath, markdownContent, 'utf-8');

        // Save media files
        if (mediaFiles.length > 0) {
            const mediaDir = path.join(baseDir, 'media');
            if (!fs.existsSync(mediaDir)) {
                fs.mkdirSync(mediaDir, { recursive: true });
            }

            for (const media of mediaFiles) {
                const destPath = path.join(mediaDir, media.filename);
                try {
                    if (fs.existsSync(media.sourcePath)) {
                        fs.copyFileSync(media.sourcePath, destPath);
                    }
                } catch {
                    // Log but don't fail if a media file can't be copied
                    console.warn(`Failed to copy media file: ${media.sourcePath}`);
                }
            }
        }

        return mdFilePath;
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
        const mdFilePath = path.join(workspaceFolder.uri.fsPath, outputDir, `${documentId}.md`);

        fs.writeFileSync(mdFilePath, markdownContent, 'utf-8');
        return mdFilePath;
    }
}

export function createOutputManager(): OutputManager {
    return new OutputManager();
}
