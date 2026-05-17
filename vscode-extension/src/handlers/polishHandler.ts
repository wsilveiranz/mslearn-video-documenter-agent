import * as vscode from 'vscode';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';
import { ChatParticipantProxy, PolishCheck, PolishResult, POLISH_CHECKS } from '../utils/chatProxy';

const ALL_CHECKS: PolishCheck[] = ['style', 'brand', 'meta', 'fix', 'seo', 'sfi'];

const HELP_TEXT =
    '📋 **Polish subcommands:**\n\n' +
    '| Command | Description |\n' +
    '|---------|-------------|\n' +
    '| `/polish style` | Writing Style Guide compliance |\n' +
    '| `/polish brand` | Product/technology name correctness |\n' +
    '| `/polish meta` | Metadata optimization |\n' +
    '| `/polish seo` | Search engine optimization |\n' +
    '| `/polish fix` | Auto-fix Markdown formatting |\n' +
    '| `/polish sfi` | Security scan |\n' +
    '| `/polish all` | Run all checks |\n';

function isValidSubcommand(word: string): word is PolishCheck | 'all' {
    return ALL_CHECKS.includes(word as PolishCheck) || word === 'all';
}

function buildSummary(results: PolishResult[]): string {
    const companion = results.filter(r => r.source === 'companion').length;
    const fallback = results.filter(r => r.source === 'fallback').length;
    const skipped = results.filter(r => r.source === 'skipped');

    const lines: string[] = [
        '\n---\n',
        '## Summary\n',
        `| Source | Count |\n|--------|-------|\n` +
        `| Companion | ${companion} |\n` +
        `| Fallback | ${fallback} |\n` +
        `| Skipped | ${skipped.length} |\n`,
    ];

    if (skipped.length > 0) {
        lines.push('\n**Skipped checks:**\n');
        for (const r of skipped) {
            lines.push(`- **${POLISH_CHECKS[r.check].label}**: ${r.summary}\n`);
        }
        lines.push(
            '\n💡 Install companion extensions for full coverage:\n' +
            '- [Learn Authoring Assistant](https://marketplace.visualstudio.com/items?itemName=docsmsft.learn-authoring-assistant)\n' +
            '- [Content Mentor](https://marketplace.visualstudio.com/items?itemName=msft-content.content-mentor)\n'
        );
    }

    return lines.join('');
}

export async function handlePolish(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager,
    _outputManager: OutputManager
): Promise<vscode.ChatResult> {
    const words = request.prompt.trim().toLowerCase().split(/\s+/);
    const subcommand = words[0] || '';

    if (!subcommand || !isValidSubcommand(subcommand)) {
        stream.markdown(HELP_TEXT);
        return { metadata: { command: 'polish' } };
    }

    const documentId = stateManager.getState().currentDocumentId;
    if (!documentId) {
        stream.markdown(
            '❌ No document to polish. Please generate a document first:\n\n' +
            '```\n@video-documenter /generate\n```'
        );
        return { metadata: { command: 'polish' } };
    }

    let content: string;
    try {
        const doc = await client.getDocument(documentId);
        content = doc.markdown_content;
    } catch (error) {
        const message = error instanceof BackendError
            ? `Backend error: ${error.detail}`
            : `Error: ${error instanceof Error ? error.message : String(error)}`;
        stream.markdown(`❌ Failed to fetch document: ${message}`);
        return { metadata: { command: 'polish' } };
    }

    const proxy = new ChatParticipantProxy();
    let results: PolishResult[];

    if (subcommand === 'all') {
        stream.progress('Running all polish checks...');
        results = await proxy.runAllChecks(content, stream, token);
    } else {
        stream.progress(`Running ${POLISH_CHECKS[subcommand].label} check...`);
        const result = await proxy.runCheck(subcommand, content, stream, token);
        results = [result];
    }

    stream.markdown(buildSummary(results));

    return { metadata: { command: 'polish' } };
}
