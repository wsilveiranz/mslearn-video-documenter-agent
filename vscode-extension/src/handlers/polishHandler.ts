import * as vscode from 'vscode';
import { BackendClient } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager } from '../utils/outputManager';

type PolishSubcommand = 'style' | 'branding';

const SUBCOMMANDS: Record<PolishSubcommand, {
    label: string;
    description: string;
    participantQuery: string;
}> = {
    style: {
        label: 'Writing Style',
        description: 'MS Writing Style Guide compliance',
        participantQuery: '@learn-authoring-assistant /suggestEdits',
    },
    branding: {
        label: 'Branding',
        description: 'Product and technology name correctness',
        participantQuery: '@learn-authoring-assistant /correctBranding',
    },
};

const HELP_TEXT =
    '📋 **Polish subcommands:**\n\n' +
    '| Command | Description |\n' +
    '|---------|-------------|\n' +
    '| `/polish style` | Writing Style Guide compliance |\n' +
    '| `/polish branding` | Product/technology name correctness |\n' +
    '\n' +
    'These open **Learn Authoring Assistant** directly for the check.\n\n' +
    '💡 For Markdown formatting, metadata, and SEO checks, use **Content Mentor** (`@content-mentor`) directly.\n';

/**
 * Find the visible Markdown editor, even when chat has focus in the editor area.
 * Falls back from activeTextEditor → visibleTextEditors with markdown languageId.
 */
function findMarkdownEditor(): vscode.TextEditor | undefined {
    // Prefer the active editor if it's already a Markdown file
    const active = vscode.window.activeTextEditor;
    if (active && active.document.languageId === 'markdown') {
        return active;
    }
    // When chat is in the editor area, activeTextEditor is undefined or the chat panel.
    // Search visible editors for the most recent Markdown file.
    const visible = vscode.window.visibleTextEditors ?? [];
    return visible.find(e => e.document.languageId === 'markdown');
}

export async function handlePolish(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    _token: vscode.CancellationToken,
    _client: BackendClient,
    _stateManager: ConversationStateManager,
    _outputManager: OutputManager
): Promise<vscode.ChatResult> {
    const subcommand = request.prompt.trim().toLowerCase().split(/\s+/)[0] || '';

    if (!(subcommand in SUBCOMMANDS)) {
        stream.markdown(HELP_TEXT);
        return { metadata: { command: 'polish' } };
    }

    const config = SUBCOMMANDS[subcommand as PolishSubcommand];

    // Ensure a Markdown editor is visible and focused before delegating
    const mdEditor = findMarkdownEditor();
    if (!mdEditor) {
        stream.markdown(
            '❌ No Markdown document found. Open a `.md` file in the editor first, ' +
            'then run this command again.\n'
        );
        return { metadata: { command: 'polish' } };
    }

    // Focus the Markdown editor so Learn Authoring Assistant can find it
    await vscode.window.showTextDocument(mdEditor.document, mdEditor.viewColumn, false);

    stream.markdown(
        `🔍 Opening **Learn Authoring Assistant** for ${config.label} check…\n\n` +
        'The check will run against the Markdown document now focused in the editor.\n'
    );

    const chatCommand: vscode.Command = {
        command: 'workbench.action.chat.open',
        title: `Run ${config.label} check`,
        arguments: [{ query: config.participantQuery }],
    };
    stream.button(chatCommand);

    return { metadata: { command: 'polish' } };
}
