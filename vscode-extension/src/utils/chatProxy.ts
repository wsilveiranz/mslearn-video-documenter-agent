/**
 * Lightweight polish checks using the VS Code Language Model API.
 *
 * Runs three MS Learn quality checks (style, metadata, formatting) via
 * Copilot's language model.  No companion extension routing — companion
 * tools like Content Mentor should be invoked directly by the user.
 */
import * as vscode from 'vscode';

export interface PolishResult {
    /** Which check was performed */
    check: string;
    /** Whether the check ran or was skipped */
    source: 'fallback' | 'skipped';
    /** Human-readable summary */
    summary: string;
    /** Detailed suggestions (Markdown) */
    suggestions: string;
    /** Estimated issue count */
    issueCount: number;
}

/** Maximum document length sent to LM prompts (characters) */
const MAX_DOCUMENT_LENGTH = 8000;

const CHECKS: { id: string; label: string; prompt: string }[] = [
    {
        id: 'style',
        label: 'Writing Style',
        prompt: `Review this Microsoft Learn Markdown document for compliance with the Microsoft Writing Style Guide.
Check for: active voice, present tense, second person (you/your), contractions, sentence case headings,
Oxford commas, "select" instead of "click", bold UI elements, numbers (spell out 0-9).
List each issue with: line reference, current text, suggested fix, rule name.
Document:
`,
    },
    {
        id: 'meta',
        label: 'Metadata',
        prompt: `Review the YAML frontmatter of this MS Learn document. Check:
- title: 43-59 characters
- description: 75-300 characters
- ms.date: valid MM/DD/YYYY format
- ms.topic: matches document type
- customer_intent: present and well-formed
List each issue found.
Document:
`,
    },
    {
        id: 'fix',
        label: 'Markdown Formatting',
        prompt: `Review this Markdown document for common formatting issues:
- Inconsistent heading levels (skipping H2→H4)
- Missing blank lines before/after code blocks
- Broken :::image::: syntax
- Unclosed code fences
- Trailing whitespace in headings
List each fix needed with line reference.
Document:
`,
    },
];

/**
 * Run all polish checks sequentially and stream results inline.
 */
export async function runPolishChecks(
    documentContent: string,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<PolishResult[]> {
    const truncatedContent = documentContent.length > MAX_DOCUMENT_LENGTH
        ? documentContent.slice(0, MAX_DOCUMENT_LENGTH) + '\n\n[... truncated for length ...]'
        : documentContent;

    const results: PolishResult[] = [];

    for (const check of CHECKS) {
        if (token.isCancellationRequested) {
            break;
        }
        stream.progress(`Checking ${check.label}…`);
        const result = await runSingleCheck(check, truncatedContent, stream, token);
        results.push(result);
    }

    return results;
}

async function runSingleCheck(
    check: { id: string; label: string; prompt: string },
    truncatedContent: string,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
): Promise<PolishResult> {
    const prompt = check.prompt + truncatedContent;

    try {
        const models = await vscode.lm.selectChatModels({ family: 'gpt-4o' });
        const model = models[0] ?? (await vscode.lm.selectChatModels())[0];

        if (!model) {
            return {
                check: check.id,
                source: 'skipped',
                summary: 'No language model available',
                suggestions: '',
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

        stream.markdown(`\n### 🔍 ${check.label}\n\n${text}\n`);

        return {
            check: check.id,
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
            check: check.id,
            source: 'skipped',
            summary: `Check failed: ${message}`,
            suggestions: '',
            issueCount: 0,
        };
    }
}

/**
 * Count issues by looking for numbered/bulleted list items in the LM response.
 */
function countIssues(text: string): number {
    let count = 0;
    for (const line of text.split('\n')) {
        const trimmed = line.trim();
        if (/^\d+\.\s/.test(trimmed) || /^[-*]\s/.test(trimmed)) {
            count++;
        }
    }
    return count;
}
