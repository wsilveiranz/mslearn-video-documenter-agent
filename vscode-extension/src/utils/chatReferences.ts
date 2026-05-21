import * as vscode from 'vscode';
import * as path from 'path';
import { BackendClient } from '../api/backendClient';

export interface ReferenceFileContent {
    filename: string;
    content: string;
}

/** Maximum size per individual reference file (100 KB). */
const MAX_REF_FILE_BYTES = 100 * 1024;
/** Maximum total size for all reference files combined (500 KB). */
const MAX_TOTAL_REF_BYTES = 500 * 1024;
/** File extensions that require backend conversion (binary formats). */
const CONVERT_EXTENSIONS = new Set(['.docx', '.pdf', '.pptx', '.xlsx', '.html', '.csv', '.xml']);

function getReferenceUri(value: unknown): vscode.Uri | null {
    if (value instanceof vscode.Uri) {
        return value;
    }
    if (value instanceof vscode.Location && value.uri instanceof vscode.Uri) {
        return value.uri;
    }
    if (typeof value === 'object' && value !== null && 'uri' in value) {
        const uri = (value as { uri?: unknown }).uri;
        return uri instanceof vscode.Uri ? uri : null;
    }
    return null;
}

/**
 * Extract file contents from VS Code Chat prompt references.
 * Reads each file-type reference, applies size limits, and optionally
 * converts binary formats via the backend MarkItDown service.
 */
export async function extractChatReferences(
    references: readonly vscode.ChatPromptReference[],
    client: BackendClient,
    stream?: vscode.ChatResponseStream,
): Promise<ReferenceFileContent[]> {
    const results: ReferenceFileContent[] = [];
    let totalBytes = 0;

    for (const ref of references) {
        const uri = getReferenceUri(ref.value);
        if (!uri || uri.scheme !== 'file') {
            continue;
        }

        const basename = path.basename(uri.fsPath);
        const ext = path.extname(uri.fsPath).toLowerCase();

        try {
            let text: string;

            if (CONVERT_EXTENSIONS.has(ext)) {
                if (stream) {
                    stream.progress(`Converting reference: ${basename}...`);
                }
                const result = await client.convertDocument(uri.fsPath);
                if ('error' in result) {
                    if (stream) {
                        stream.progress(`⚠️ Could not convert ${basename}: ${result.error}`);
                    }
                    continue;
                }
                if (!result.markdown) {
                    continue;
                }
                text = result.markdown;
            } else {
                const bytes = await vscode.workspace.fs.readFile(uri);
                text = Buffer.from(bytes).toString('utf-8');
            }

            if (text.length > MAX_REF_FILE_BYTES) {
                text = text.slice(0, MAX_REF_FILE_BYTES) + '\n[… truncated — file exceeds 100 KB limit]';
                if (stream) {
                    stream.progress(`Reference truncated (exceeds 100 KB): ${basename}`);
                }
            }

            totalBytes += text.length;
            results.push({ filename: basename, content: text });

            if (totalBytes >= MAX_TOTAL_REF_BYTES) {
                if (stream) {
                    stream.progress('Some references skipped — total size exceeds 500 KB limit.');
                }
                break;
            }
        } catch {
            // Skip files that can't be read
        }
    }

    return results;
}
