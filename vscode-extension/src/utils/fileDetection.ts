import * as path from 'path';

const VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v'];

/**
 * Detect a video file path from user input text.
 * Supports Windows and Unix paths, with or without quotes.
 */
export function detectVideoPath(input: string): string | undefined {
    if (!input || input.trim().length === 0) {
        return undefined;
    }

    // Try quoted paths first
    const quotedMatch = input.match(/["']([^"']+\.\w+)["']/);
    if (quotedMatch) {
        const candidate = quotedMatch[1];
        if (isVideoFile(candidate)) {
            return candidate;
        }
    }

    // Try Windows absolute paths (e.g., C:\path\to\file.mp4)
    const windowsMatch = input.match(/[A-Za-z]:\\[^\s"']+\.\w+/);
    if (windowsMatch) {
        const candidate = windowsMatch[0];
        if (isVideoFile(candidate)) {
            return candidate;
        }
    }

    // Try Unix absolute paths (e.g., /home/user/file.mp4)
    const unixMatch = input.match(/\/[^\s"']+\.\w+/);
    if (unixMatch) {
        const candidate = unixMatch[0];
        if (isVideoFile(candidate)) {
            return candidate;
        }
    }

    // Try relative paths
    const relativeMatch = input.match(/(?:\.\/|\.\\)?[\w\-./\\]+\.\w+/);
    if (relativeMatch) {
        const candidate = relativeMatch[0];
        if (isVideoFile(candidate)) {
            return candidate;
        }
    }

    return undefined;
}

function isVideoFile(filePath: string): boolean {
    const ext = path.extname(filePath).toLowerCase();
    return VIDEO_EXTENSIONS.includes(ext);
}
