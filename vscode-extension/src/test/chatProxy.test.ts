import * as assert from 'assert';
import {
    ChatParticipantProxy,
    POLISH_CHECKS,
    PolishCheck,
    PolishResult,
} from '../utils/chatProxy';
import * as vscode from 'vscode';

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
function createMockToken(): vscode.CancellationToken {
    return {
        isCancellationRequested: false,
        onCancellationRequested: () => ({ dispose: () => {} }),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

describe('POLISH_CHECKS', () => {
    const allChecks: PolishCheck[] = ['style', 'brand', 'meta', 'seo', 'fix', 'sfi'];

    it('has all 6 checks defined', () => {
        const keys = Object.keys(POLISH_CHECKS);
        assert.strictEqual(keys.length, 6);
        for (const check of allChecks) {
            assert.ok(check in POLISH_CHECKS, `missing check: ${check}`);
        }
    });

    it('has correct companion IDs for each check', () => {
        assert.strictEqual(POLISH_CHECKS.style.companion?.id, 'docsmsft.learn-authoring-assistant');
        assert.strictEqual(POLISH_CHECKS.brand.companion?.id, 'docsmsft.learn-authoring-assistant');
        assert.strictEqual(POLISH_CHECKS.meta.companion?.id, 'msft-content.content-mentor');
        assert.strictEqual(POLISH_CHECKS.seo.companion?.id, 'msft-content.content-mentor');
        assert.strictEqual(POLISH_CHECKS.fix.companion?.id, 'msft-content.content-mentor');
        assert.strictEqual(POLISH_CHECKS.sfi.companion?.id, 'msft-content.content-mentor');
    });

    it('has fallback available only for style, meta, fix', () => {
        assert.strictEqual(POLISH_CHECKS.style.fallbackAvailable, true);
        assert.strictEqual(POLISH_CHECKS.brand.fallbackAvailable, false);
        assert.strictEqual(POLISH_CHECKS.meta.fallbackAvailable, true);
        assert.strictEqual(POLISH_CHECKS.seo.fallbackAvailable, false);
        assert.strictEqual(POLISH_CHECKS.fix.fallbackAvailable, true);
        assert.strictEqual(POLISH_CHECKS.sfi.fallbackAvailable, false);
    });
});

describe('ChatParticipantProxy', () => {
    let proxy: ChatParticipantProxy;

    beforeEach(() => {
        proxy = new ChatParticipantProxy();
    });

    describe('isCompanionAvailable', () => {
        it('returns false when no companions are installed (default mock)', () => {
            // vscode.extensions.getExtension returns undefined by default
            assert.strictEqual(proxy.isCompanionAvailable('style'), false);
            assert.strictEqual(proxy.isCompanionAvailable('meta'), false);
            assert.strictEqual(proxy.isCompanionAvailable('fix'), false);
        });

        it('returns false for all checks when mock returns undefined', () => {
            const allChecks: PolishCheck[] = ['style', 'brand', 'meta', 'seo', 'fix', 'sfi'];
            for (const check of allChecks) {
                assert.strictEqual(proxy.isCompanionAvailable(check), false);
            }
        });
    });

    describe('getCompanions', () => {
        it('returns an array of companion extensions', () => {
            const companions = proxy.getCompanions();
            assert.ok(Array.isArray(companions));
            assert.ok(companions.length > 0);
        });

        it('caches results on subsequent calls', () => {
            const first = proxy.getCompanions();
            const second = proxy.getCompanions();
            assert.strictEqual(first, second);
        });
    });

    describe('runCheck', () => {
        it('returns skipped result when companion unavailable and no fallback', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            // 'brand' has no fallback and mock has no companion installed
            const result = await proxy.runCheck('brand', '# Test', stream, token);

            assert.strictEqual(result.check, 'brand');
            assert.strictEqual(result.source, 'skipped');
            assert.strictEqual(result.issueCount, 0);
            assert.ok(result.summary.includes('skipped'));
        });

        it('returns skipped result for seo when companion unavailable', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            const result = await proxy.runCheck('seo', '# Test', stream, token);

            assert.strictEqual(result.check, 'seo');
            assert.strictEqual(result.source, 'skipped');
        });

        it('returns skipped result for sfi when companion unavailable', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            const result = await proxy.runCheck('sfi', '# Test', stream, token);

            assert.strictEqual(result.check, 'sfi');
            assert.strictEqual(result.source, 'skipped');
        });

        it('attempts fallback when companion unavailable but fallback is available', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            // 'style' has fallback available; LM mock returns empty models → skipped
            const result = await proxy.runCheck('style', '# Test doc', stream, token);

            // With no LM models available, it should still return a result (skipped due to no model)
            assert.strictEqual(result.check, 'style');
            // source is 'skipped' because lm.selectChatModels returns [] in the mock
            assert.strictEqual(result.source, 'skipped');
            assert.ok(result.summary.includes('No language model'));
        });

        it('returns properly structured PolishResult', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            const result = await proxy.runCheck('meta', '# Test', stream, token);

            assert.ok('check' in result);
            assert.ok('source' in result);
            assert.ok('summary' in result);
            assert.ok('suggestions' in result);
            assert.ok('issueCount' in result);
            assert.strictEqual(typeof result.check, 'string');
            assert.strictEqual(typeof result.source, 'string');
            assert.strictEqual(typeof result.summary, 'string');
            assert.strictEqual(typeof result.suggestions, 'string');
            assert.strictEqual(typeof result.issueCount, 'number');
        });

        it('streams progress output when running fallback', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            await proxy.runCheck('fix', '# Test', stream, token);

            const progressCalls = stream.calls.filter(c => c.method === 'progress');
            assert.ok(progressCalls.length > 0, 'expected at least one progress call');
        });
    });

    describe('runAllChecks', () => {
        it('returns results for all 6 checks', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            const results = await proxy.runAllChecks('# Test doc', stream, token);

            assert.strictEqual(results.length, 6);
            const checks = results.map(r => r.check);
            assert.ok(checks.includes('style'));
            assert.ok(checks.includes('brand'));
            assert.ok(checks.includes('meta'));
            assert.ok(checks.includes('seo'));
            assert.ok(checks.includes('fix'));
            assert.ok(checks.includes('sfi'));
        });

        it('respects cancellation token', async () => {
            const stream = createMockStream();
            const token: vscode.CancellationToken = {
                isCancellationRequested: true,
                onCancellationRequested: () => ({ dispose: () => {} }),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            } as any;

            const results = await proxy.runAllChecks('# Test', stream, token);

            // Should return 0 results since cancellation is already requested
            assert.strictEqual(results.length, 0);
        });

        it('each result has the correct check property', async () => {
            const stream = createMockStream();
            const token = createMockToken();

            const results = await proxy.runAllChecks('# Test', stream, token);
            const expectedChecks: PolishCheck[] = ['style', 'brand', 'meta', 'seo', 'fix', 'sfi'];

            for (let i = 0; i < expectedChecks.length; i++) {
                assert.strictEqual(results[i].check, expectedChecks[i]);
            }
        });
    });

    describe('runCheck with LM model available', () => {
        let originalSelectChatModels: typeof vscode.lm.selectChatModels;

        beforeEach(() => {
            originalSelectChatModels = vscode.lm.selectChatModels;
        });

        afterEach(() => {
            vscode.lm.selectChatModels = originalSelectChatModels;
        });

        it('calls fallback LM and returns result with issues', async () => {
            // Patch the lm mock to return a model with sendRequest
            const mockResponse = '1. Use active voice on line 5\n2. Use "select" instead of "click" on line 12\n3. Missing Oxford comma on line 20';
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

            const result = await proxy.runCheck('style', '# Test document\nClick the button', stream, token);

            assert.strictEqual(result.check, 'style');
            assert.strictEqual(result.source, 'fallback');
            assert.strictEqual(result.issueCount, 3);
            assert.ok(result.suggestions.includes('active voice'));
        });

        it('returns fallback result for meta check', async () => {
            const mockResponse = '- title: too short (20 characters, should be 43-59)\n- ms.date: missing';
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
                countTokens: async () => 50,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            }] as any);

            const stream = createMockStream();
            const token = createMockToken();

            const result = await proxy.runCheck('meta', '---\ntitle: Short\n---', stream, token);

            assert.strictEqual(result.check, 'meta');
            assert.strictEqual(result.source, 'fallback');
            assert.strictEqual(result.issueCount, 2);
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

            const result = await proxy.runCheck('style', '# Test', stream, token);

            assert.strictEqual(result.source, 'skipped');
            assert.ok(result.summary.includes('Model unavailable'));
        });

        it('truncates long documents before sending to LM', async () => {
            let receivedPrompt = '';
            vscode.lm.selectChatModels = () => Promise.resolve([{
                id: 'test-model',
                vendor: 'test',
                family: 'test',
                version: '1.0',
                name: 'Test Model',
                maxInputTokens: 4096,
                sendRequest: async (messages: Array<{ content: string }>) => {
                    receivedPrompt = messages[0].content;
                    return {
                        text: (async function* () { yield 'No issues found.'; })(),
                        stream: (async function* () { yield { value: 'No issues found.' }; })(),
                    };
                },
                countTokens: async () => 50,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            }] as any);

            const stream = createMockStream();
            const token = createMockToken();
            const longDoc = 'x'.repeat(10000);

            await proxy.runCheck('style', longDoc, stream, token);

            assert.ok(receivedPrompt.includes('[... truncated for length ...]'));
            // The truncated content should be much shorter than the original
            assert.ok(receivedPrompt.length < longDoc.length);
        });
    });
});
