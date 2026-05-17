import * as assert from 'assert';
import * as vscode from 'vscode';
import { handlePolish } from '../handlers/polishHandler';
import { BackendError } from '../api/backendClient';

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

function createMockClient(options?: {
    throwOnGet?: Error;
    markdownContent?: string;
}) {
    return {
        getDocument: async (_id: string) => {
            if (options?.throwOnGet) {
                throw options.throwOnGet;
            }
            return {
                document_id: 'doc-1',
                doc_type: 'tutorial',
                markdown_content: options?.markdownContent ?? '# Test document\n\nSome content.',
                word_count: 42,
                revision_number: 1,
                media_files: [],
            };
        },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

function createMockStateManager(documentId?: string) {
    return {
        getState: () => ({
            currentStage: documentId ? 'generated' as const : 'idle' as const,
            currentDocumentId: documentId,
        }),
        setStage: () => {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
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
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        assert.deepStrictEqual(result, { metadata: { command: 'polish' } });
        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('/polish style'), 'should list style subcommand');
        assert.ok(output.includes('/polish all'), 'should list all subcommand');
    });

    it('should show help for invalid subcommand', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('banana'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('/polish style'));
        assert.ok(output.includes('/polish sfi'));
    });

    it('should show error when no document ID exists', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('style'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager(undefined),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('generate a document first'), 'should instruct user to generate first');
    });

    it('should run single check for valid subcommand "style"', async () => {
        const stream = new MockStream();
        const result = await handlePolish(
            makeRequest('style'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        assert.deepStrictEqual(result, { metadata: { command: 'polish' } });
        // Should show progress
        assert.ok(stream.progressCalls.length > 0, 'should emit progress');
        // Summary should exist
        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('Summary'), 'should include summary');
    });

    it('should run all checks for subcommand "all"', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('all'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('Summary'), 'should include summary');
        // With default mocks (no companions, no LM) there should be skipped checks
        assert.ok(output.includes('Skipped'), 'should include skipped count');
    });

    it('should show summary counts (companion/fallback/skipped)', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('all'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        // With no companions and no LM models: all 6 are skipped
        assert.ok(output.includes('Companion'), 'summary should mention companion count');
        assert.ok(output.includes('Fallback'), 'summary should mention fallback count');
        assert.ok(output.includes('Skipped'), 'summary should mention skipped count');
    });

    it('should show error when backend fails to fetch document', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('style'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient({ throwOnGet: new BackendError(404, 'Document not found') }),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('Failed to fetch document'), 'should show fetch error');
        assert.ok(output.includes('Document not found'), 'should include error detail');
    });

    it('should handle generic errors when fetching document', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('meta'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient({ throwOnGet: new Error('Network error') }),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('Failed to fetch document'));
        assert.ok(output.includes('Network error'));
    });

    it('should parse subcommand case-insensitively', async () => {
        const stream = new MockStream();
        await handlePolish(
            makeRequest('STYLE'),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        const output = stream.markdownCalls.join('');
        assert.ok(output.includes('Summary'), 'should process uppercase subcommand');
    });

    it('should return polish metadata in result', async () => {
        const stream = new MockStream();
        const result = await handlePolish(
            makeRequest(''),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            stream as any,
            createMockToken(),
            createMockClient(),
            createMockStateManager('doc-1'),
            createMockOutputManager()
        );

        assert.deepStrictEqual(result, { metadata: { command: 'polish' } });
    });
});
