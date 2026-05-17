/**
 * Companion extension detection and workflow tips.
 *
 * Detects installed MS Learn companion extensions and provides
 * contextual post-generation workflow tips.
 */
import * as vscode from 'vscode';

export interface CompanionExtension {
    /** VS Code extension ID */
    id: string;
    /** Human-readable name */
    name: string;
    /** Whether the extension is currently installed and active */
    available: boolean;
    /** Whether this is a Microsoft-internal extension */
    internal: boolean;
}

/** Known companion extensions for MS Learn documentation workflow */
export const COMPANION_EXTENSIONS: readonly { id: string; name: string; internal: boolean }[] = [
    {
        id: 'docsmsft.docs-authoring-pack',
        name: 'Learn Authoring Pack',
        internal: false,
    },
    {
        id: 'msft-content.content-mentor',
        name: 'Content Mentor',
        internal: true,
    },
    {
        id: 'docsmsft.learn-authoring-assistant',
        name: 'Learn Authoring Assistant',
        internal: true,
    },
] as const;

/**
 * Detect which companion extensions are installed.
 */
export function detectCompanions(): CompanionExtension[] {
    return COMPANION_EXTENSIONS.map(ext => ({
        ...ext,
        available: vscode.extensions.getExtension(ext.id) !== undefined,
    }));
}

/**
 * Get contextual workflow tips based on installed companion extensions.
 * Returns Markdown-formatted tips for post-generation display.
 */
export function getCompanionTips(companions?: CompanionExtension[]): string {
    const detected = companions ?? detectCompanions();
    const tips: string[] = [];

    const authoringPack = detected.find(c => c.id === 'docsmsft.docs-authoring-pack');
    const contentMentor = detected.find(c => c.id === 'msft-content.content-mentor');
    const authoringAssistant = detected.find(c => c.id === 'docsmsft.learn-authoring-assistant');

    if (authoringPack?.available) {
        tips.push('📖 **Learn Authoring Pack** detected — use Learn Preview for a rendered view of your document');
    }

    if (contentMentor?.available) {
        tips.push('🔍 **Content Mentor** detected — use `@content-mentor` in Copilot Chat for AI-powered style review and metadata optimization');
    }

    if (authoringAssistant?.available) {
        tips.push('✍️ **Learn Authoring Assistant** detected — use `/suggestEdits` in Copilot Chat for writing style enforcement');
    }

    if (tips.length === 0) {
        return '';
    }

    return '\n\n---\n\n**📋 Next steps with companion extensions:**\n\n' + tips.join('\n\n');
}

/**
 * Get a summary of companion extension status for diagnostics.
 */
export function getCompanionStatus(): string {
    const companions = detectCompanions();
    const lines = companions.map(c => {
        const status = c.available ? '✅' : '❌';
        const scope = c.internal ? '(internal)' : '(public)';
        return `${status} ${c.name} ${scope}`;
    });
    return lines.join('\n');
}
