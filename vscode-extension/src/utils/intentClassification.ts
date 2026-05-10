import * as path from 'path';

export type ConversationIntent = 'save' | 'refine' | 'general';

export const SAVE_PATTERNS = [
    /^(please\s+)?(save|export|write|copy)\s+(it\s+|the\s+(doc|document|file|markdown|md)\s+)?(to|at|in|into|as)\s+/i,
    /^(please\s+)?(save|export)\s+(it|this|the\s+(doc|document|file|markdown|md))?\s*$/i,
    /^(please\s+)?(save|export)\s*$/i,
];

/**
 * Fast-path intent classification using pattern matching.
 * Returns 'save' if a save pattern matches, undefined otherwise
 * (meaning the caller should fall back to LLM classification).
 */
export function classifyIntentFast(prompt: string): ConversationIntent | undefined {
    const trimmed = prompt.trim();

    for (const pattern of SAVE_PATTERNS) {
        if (pattern.test(trimmed)) {
            return 'save';
        }
    }

    return undefined;
}

/**
 * Extract a file-system path from the user's save request.
 * Handles prompts like "save to c:\temp\", "export to /home/user/docs", etc.
 */
export function extractTargetPath(prompt: string): string | undefined {
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
 * Resolve a target path, appending a filename if it's a directory
 * and adding .md extension if missing.
 * Pure version without VS Code or fs dependencies (for testing).
 */
export function resolveTargetPathPure(
    targetPath: string,
    documentId: string,
    isAbsolute: boolean,
    isExistingDirectory: boolean,
    workspaceRoot?: string
): string {
    let resolved = targetPath;

    // Resolve relative paths against workspace
    if (!isAbsolute && workspaceRoot) {
        resolved = path.join(workspaceRoot, resolved);
    }

    // If target is a directory (ends with separator or detected as directory), append filename
    if (resolved.endsWith(path.sep) || resolved.endsWith('/') || isExistingDirectory) {
        resolved = path.join(resolved, `${documentId}.md`);
    }

    // Ensure .md extension if no extension provided
    if (!path.extname(resolved)) {
        resolved += '.md';
    }

    return resolved;
}
