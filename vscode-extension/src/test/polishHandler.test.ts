import * as assert from 'assert';
import * as vscode from 'vscode';
import { handlePolish } from '../handlers/polishHandler';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

class MockStream {
    markdownCalls: string[] = [];
    progressCalls: string[] = [];
    buttonCalls: vscode.Command[] = [];
    markdown(value: string | vscode.MarkdownString) {
        this.markdownCalls.push(typeof value === 'string' ? value : value.value);
    }
    progress(value: string) { this.progressCalls.push(value); }
    button(command: vscode.Command) { this.buttonCalls.push(command); }
    anchor() {}
    filetree() {}
    reference() {}
    push() {}
    warning() {}
    confirmation() { return undefined as unknown; }
}

function createMockToken(cancelled = false): vscode.CancellationToken {
    return {
        isCancellationRequested: cancelled,
        onCancellationRequested: () => ({ dispose: () => {} }),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function createMockClient(): any {
    return {};
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function createMockStateManager(): any {
    return {
        getState: () => ({ currentStage: 'idle' as const }),
        setStage: () => {},
    };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function createMockOutputManager(): any {
    return {};
}

function makeRequest(prompt: string): vscode.ChatRequest {
    return {
        prompt,
        command: 'polish',
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('polishHandler', () => {
    it('should show help when no subcommand provided', async () => {
        const stream = new MockStream();
        const result = await handlePolish(
            makeRequest(''),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(),
            createMockOutputManager()
        );

        assert.deepStrictEqual(result, { metadata: { command: 'polish' } });
        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('/polish style'), 'should list style subcommand');
        assert.ok(output.includes('/polish branding'), 'should list branding subcommand');
        assert.ok(output.includes('Content Mentor'), 'should mention Content Mentor');
    });

    it('should show help for invalid subcommand', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('banana'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('/polish style'));
        assert.ok(output.includes('/polish branding'));
    });

    it('should show error when no markdown editor is visible for style', async () => {
        const stream = new MockStream();
        // vscode.window.visibleTextEditors is empty in test mock
        await handlePolish(
            makeRequest('style'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('No Markdown document found'), 'should tell user to open a file');
    });

    it('should show error when no markdown editor is visible for branding', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('branding'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('No Markdown document found'));
    });

    it('should parse subcommand case-insensitively', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('STYLE'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        // With no visible editors, it should show the "no markdown" error (not the help text)
        assert.ok(output.includes('No Markdown document found') || output.includes('Writing Style'));
    });

    it('should return polish metadata in result', async () => {
        const stream = new MockStream();
        const result = await handlePolish(
            makeRequest(''),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(),
            createMockOutputManager()
        );

        assert.deepStrictEqual(result, { metadata: { command: 'polish' } });
    });
});
