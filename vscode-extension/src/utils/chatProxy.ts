/**
 * Chat participant proxy for invoking companion extensions.
 *
 * Since VS Code does not expose a public API for one chat participant to
 * programmatically invoke another, this module provides:
 * 1. Detection of installed companion chat participants
 * 2. Button-based invocation (user clicks to open companion in chat)
 * 3. Built-in fallback checks using the VS Code Language Model API
 */
import * as vscode from 'vscode';
import { detectCompanions, CompanionExtension } from './companions';

export interface PolishResult {
    /** Which check was performed */
    check: PolishCheck;
    /** Whether the check was performed by a companion or fallback */
    source: 'companion' | 'fallback' | 'skipped';
    /** Human-readable summary of findings */
    summary: string;
    /** Detailed suggestions (Markdown formatted) */
    suggestions: string;
    /** Number of issues found */
    issueCount: number;
}

export type PolishCheck = 'style' | 'brand' | 'meta' | 'seo' | 'fix' | 'sfi';

export const POLISH_CHECKS: Record<PolishCheck, {
    label: string;
    description: string;
    companion: { id: string; name: string; command: string; participantHandle?: string } | null;
    fallbackAvailable: boolean;
}> = {
    style: {
        label: 'Writing Style',
        description: 'MS Writing Style Guide compliance (35 rules)',
        companion: { id: 'docsmsft.learn-authoring-assistant', name: 'Learn Authoring Assistant', command: 'suggestEdits' },
        fallbackAvailable: true,
    },
    brand: {
        label: 'Branding',
        description: 'Product/technology name correctness',
        companion: { id: 'docsmsft.learn-authoring-assistant', name: 'Learn Authoring Assistant', command: 'correctBranding' },
        fallbackAvailable: false,
    },
    meta: {
        label: 'Metadata',
        description: 'Title, description, ms.date optimization',
        companion: { id: 'msft-content.content-mentor', name: 'Content Mentor', command: 'metadata' },
        fallbackAvailable: true,
    },
    seo: {
        label: 'SEO',
        description: 'Search engine optimization',
        companion: { id: 'msft-content.content-mentor', name: 'Content Mentor', command: 'seo' },
        fallbackAvailable: false,
    },
    fix: {
        label: 'Auto-fix Markdown',
        description: 'Fix common Markdown formatting issues',
        companion: { id: 'msft-content.content-mentor', name: 'Content Mentor', command: 'autoFixMarkdown' },
        fallbackAvailable: true,
    },
    sfi: {
        label: 'Security (SFI)',
        description: 'Sensitive information scan',
        companion: { id: 'msft-content.content-mentor', name: 'Content Mentor', command: 'sfi' },
        fallbackAvailable: false,
    },
};

/** Maximum document length sent to fallback LM prompts (characters) */
const MAX_DOCUMENT_LENGTH = 8000;

const FALLBACK_PROMPTS: Partial<Record<PolishCheck, string>> = {
    style: `Review this Microsoft Learn Markdown document for compliance with the Microsoft Writing Style Guide.
Check for: active voice, present tense, second person (you/your), contractions, sentence case headings,
Oxford commas, "select" instead of "click", bold UI elements, numbers (spell out 0-9).
List each issue with: line reference, current text, suggested fix, rule name.
Document:
`,
    meta: `Review the YAML frontmatter of this MS Learn document. Check:
- title: 43-59 characters
- description: 75-300 characters
- ms.date: valid MM/DD/YYYY format
- ms.topic: matches document type
- customer_intent: present and well-formed
List each issue found.
Document:
`,
    fix: `Review this Markdown document for common formatting issues:
- Inconsistent heading levels (skipping H2→H4)
- Missing blank lines before/after code blocks
- Broken :::image::: syntax
- Unclosed code fences
- Trailing whitespace in headings
List each fix needed with line reference.
Document:
`,
};

export class ChatParticipantProxy {
    private _companions: CompanionExtension[] | null = null;

    /** Get cached companion detection results */
    getCompanions(): CompanionExtension[] {
        if (!this._companions) {
            this._companions = detectCompanions();
        }
        return this._companions;
    }

    /** Check if a specific companion is available for a check */
    isCompanionAvailable(check: PolishCheck): boolean {
        const config = POLISH_CHECKS[check];
        if (!config.companion) {
            return false;
        }
        const companions = this.getCompanions();
        return companions.some(c => c.id === config.companion!.id && c.available);
    }

    /**
     * Run a polish check.
     * Always runs built-in fallback when available for immediate results.
     * Additionally offers companion button when a companion is installed.
     * If no fallback and no companion → skipped.
     */
    async runCheck(
        check: PolishCheck,
        documentContent: string,
        stream: vscode.ChatResponseStream,
        token: vscode.CancellationToken
    ): Promise<PolishResult> {
        const config = POLISH_CHECKS[check];
        const companionAvailable = this.isCompanionAvailable(check);

        // Run fallback for immediate results when available
        if (config.fallbackAvailable) {
            stream.markdown(`\n### 🔍 ${config.label}\n\n`);
            stream.progress(`Running ${config.label} check...`);
            const result = await this._runFallbackCheck(check, documentContent, token);

            // Offer companion button as a supplementary option
            if (companionAvailable) {
                stream.markdown(`\n\n💡 For a more thorough check, use **${config.companion!.name}** directly:\n\n`);
                this._createCompanionButton(check, stream);
            }

            return result;
        }

        // No fallback — rely on companion button only
        if (companionAvailable) {
            stream.markdown(`\n### ✅ ${config.label}\n\n`);
            stream.markdown(`**${config.companion!.name}** is installed — use it for the ${config.label.toLowerCase()} check.\n\n`);
            this._createCompanionButton(check, stream);

            return {
                check,
                source: 'companion',
                summary: `${config.companion!.name} is available for ${config.label} check`,
                suggestions: `Use the button above to run the ${config.label} check with ${config.companion!.name}.`,
                issueCount: 0,
            };
        }

        // Neither fallback nor companion
        return {
            check,
            source: 'skipped',
            summary: `${config.label} check skipped — requires ${config.companion?.name ?? 'companion extension'}`,
            suggestions: config.companion
                ? `Install **${config.companion.name}** (\`${config.companion.id}\`) for ${config.label} checking.`
                : '',
            issueCount: 0,
        };
    }

    /**
     * Run all polish checks in sequence.
     */
    async runAllChecks(
        documentContent: string,
        stream: vscode.ChatResponseStream,
        token: vscode.CancellationToken
    ): Promise<PolishResult[]> {
        const results: PolishResult[] = [];
        const checks = Object.keys(POLISH_CHECKS) as PolishCheck[];

        for (const check of checks) {
            if (token.isCancellationRequested) {
                break;
            }
            const result = await this.runCheck(check, documentContent, stream, token);
            results.push(result);
        }

        return results;
    }

    /**
     * Run a fallback check using the VS Code Language Model API.
     */
    private async _runFallbackCheck(
        check: PolishCheck,
        documentContent: string,
        token: vscode.CancellationToken
    ): Promise<PolishResult> {
        const promptTemplate = FALLBACK_PROMPTS[check];
        if (!promptTemplate) {
            return {
                check,
                source: 'skipped',
                summary: `No fallback prompt available for ${check}`,
                suggestions: '',
                issueCount: 0,
            };
        }

        const truncatedContent = documentContent.length > MAX_DOCUMENT_LENGTH
            ? documentContent.slice(0, MAX_DOCUMENT_LENGTH) + '\n\n[... truncated for length ...]'
            : documentContent;

        const prompt = promptTemplate + truncatedContent;

        try {
            const models = await vscode.lm.selectChatModels({ family: 'gpt-4o' });
            const model = models[0] ?? (await vscode.lm.selectChatModels())[0];

            if (!model) {
                return {
                    check,
                    source: 'skipped',
                    summary: 'No language model available for fallback check',
                    suggestions: 'Ensure GitHub Copilot is active and a language model is available.',
                    issueCount: 0,
                };
            }

            const messages = [vscode.LanguageModelChatMessage.User(prompt)];
            const response = await model.sendRequest(messages, {}, token);

            let text = '';
            for await (const chunk of response.text) {
                text += chunk;
            }

            const issueCount = countIssues(text);

            return {
                check,
                source: 'fallback',
                summary: issueCount > 0
                    ? `Found ${issueCount} potential issue${issueCount === 1 ? '' : 's'}`
                    : 'No issues found',
                suggestions: text,
                issueCount,
            };
        } catch (error: unknown) {
            const message = error instanceof Error ? error.message : String(error);
            return {
                check,
                source: 'skipped',
                summary: `Fallback check failed: ${message}`,
                suggestions: '',
                issueCount: 0,
            };
        }
    }

    /**
     * Create a chat button that opens the companion's chat participant.
     * Uses vscode.ChatResponseStream.button() to render a clickable action.
     * Only creates a button if the participant handle is known.
     */
    private _createCompanionButton(
        check: PolishCheck,
        stream: vscode.ChatResponseStream
    ): void {
        const config = POLISH_CHECKS[check];
        if (!config.companion) {
            return;
        }

        // Use explicit participant handle if known, otherwise skip button
        const handle = config.companion.participantHandle;
        if (!handle) {
            stream.markdown(
                `> Open **${config.companion.name}** from the Copilot Chat participant list ` +
                `and run \`/${config.companion.command}\`\n`
            );
            return;
        }

        const chatCommand: vscode.Command = {
            command: 'workbench.action.chat.open',
            title: `Run ${config.label} check`,
            arguments: [{
                query: `@${handle} /${config.companion.command}`,
            }],
        };

        stream.button(chatCommand);
    }
}

/**
 * Count the number of issues in LM response text by looking for
 * numbered list items, bullet points starting with issue-like patterns,
 * or lines containing "issue" / "error" / "warning".
 */
function countIssues(text: string): number {
    const lines = text.split('\n');
    let count = 0;
    for (const line of lines) {
        const trimmed = line.trim();
        // Count numbered list items (1. , 2. , etc.) and bullet items (- , * )
        if (/^\d+\.\s/.test(trimmed) || /^[-*]\s/.test(trimmed)) {
            count++;
        }
    }
    return count;
}
