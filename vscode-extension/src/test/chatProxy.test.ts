import * as assert from 'assert';
import * as vscode from 'vscode';
import { runPolishChecks } from '../utils/chatProxy';

// Helper: build a mock ChatResponseStream
function createMockStream(): vscode.ChatResponseStream & { calls: { method: string; args: unknown[] }[] } {
    const calls: { method: string; args: unknown[] }[] = [];
    return {
        calls,
        markdown: (...args: unknown[]) => { calls.push({ method: 'markdown', args }); },
        progress: (...args: unknown[]) => { calls.push({ method: 'progress', args }); },
        button: (...args: unknown[]) => { calls.push({ method: 'button', args }); },
        anchor: (...args: unknown[]) => { calls.push({ method: 'anchor', args }); },
        filetree: (...args: unknown[]) => { calls.push({ method: 'filetree', args }); },
        reference: (...args: unknown[]) => { calls.push({ method: 'reference', args }); },
        push: (...args: unknown[]) => { calls.push({ method: 'push', args }); },
        warning: (...args: unknown[]) => { calls.push({ method: 'warning', args }); },
        confirmation: (...args: unknown[]) => {
            calls.push({ method: 'confirmation', args });
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return undefined as any;
        },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

// Helper: build a non-cancelling token
function createMockToken(cancelled = false): vscode.CancellationToken {
    return {
        isCancellationRequested: cancelled,
        onCancellationRequested: () => ({ dispose: () => {} }),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

describe('runPolishChecks', () => {
    it('returns 3 results (style, meta, fix)', async () => {
        const stream = createMockStream();
        const token = createMockToken();

        const results = await runPolishChecks('# Test doc\n\nSome content.', stream, token);

        assert.strictEqual(results.length, 3);
        const ids = results.map(r => r.check);
        assert.ok(ids.includes('style'));
        assert.ok(ids.includes('meta'));
        assert.ok(ids.includes('fix'));
    });

    it('skips all checks when no LM is available', async () => {
        const stream = createMockStream();
        const token = createMockToken();

        const results = await runPolishChecks('# Test', stream, token);

        for (const r of results) {
            assert.strictEqual(r.source, 'skipped');
        }
    });

    it('respects cancellation token', async () => {
        const stream = createMockStream();
        const token = createMockToken(true);

        const results = await runPolishChecks('# Test', stream, token);

        assert.strictEqual(results.length, 0);
    });

    it('emits progress for each check', async () => {
        const stream = createMockStream();
        const token = createMockToken();

        await runPolishChecks('# Test', stream, token);

        const progressCalls = stream.calls.filter(c => c.method === 'progress');
        assert.ok(progressCalls.length >= 3, 'expected at least 3 progress calls');
    });

    it('returns properly structured PolishResult objects', async () => {
        const stream = createMockStream();
        const token = createMockToken();

        const results = await runPolishChecks('# Test', stream, token);

        for (const result of results) {
            assert.ok('check' in result);
            assert.ok('source' in result);
            assert.ok('summary' in result);
            assert.ok('suggestions' in result);
            assert.ok('issueCount' in result);
            assert.strictEqual(typeof result.check, 'string');
            assert.strictEqual(typeof result.issueCount, 'number');
        }
    });

    describe('with LM model available', () => {
        let originalSelectChatModels: typeof vscode.lm.selectChatModels;

        beforeEach(() => {
            originalSelectChatModels = vscode.lm.selectChatModels;
        });

        afterEach(() => {
            vscode.lm.selectChatModels = originalSelectChatModels;
        });

        it('returns fallback results with issue counts', async () => {
            const mockResponse = '1. Use active voice on line 5\n2. Use "select" instead of "click"';
            vscode.lm.selectChatModels = () => Promise.resolve([{
                id: 'test-model',
                vendor: 'test',
                family: 'test',
                version: '1.0',
                name: 'Test Model',
                maxInputTokens: 4096,
                sendRequest: async () => ({
                    text: (async function* () { yield mockResponse; })(),
                    stream: (async function* () { yield { value: mockResponse }; })(),
                }),
                countTokens: async () => 100,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            }] as any);

            const stream = createMockStream();
            const token = createMockToken();

            const results = await runPolishChecks('# Test doc\nClick the button', stream, token);

            const styleResult = results.find(r => r.check === 'style');
            assert.ok(styleResult);
            assert.strictEqual(styleResult.source, 'fallback');
            assert.strictEqual(styleResult.issueCount, 2);
        });

        it('handles sendRequest error gracefully', async () => {
            vscode.lm.selectChatModels = () => Promise.resolve([{
                id: 'test-model',
                vendor: 'test',
                family: 'test',
                version: '1.0',
                name: 'Test Model',
                maxInputTokens: 4096,
                sendRequest: async () => { throw new Error('Model unavailable'); },
                countTokens: async () => 0,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            }] as any);

            const stream = createMockStream();
            const token = createMockToken();

            const results = await runPolishChecks('# Test', stream, token);

            for (const r of results) {
                assert.strictEqual(r.source, 'skipped');
            }
        });
    });
});
