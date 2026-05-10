import * as http from 'node:http';
import * as vscode from 'vscode';

// ── Types ──────────────────────────────────────────────────────────────────

interface OpenAIMessage {
    role: 'system' | 'user' | 'assistant';
    content: string | OpenAIContentPart[];
}

interface OpenAIContentPart {
    type: 'text' | 'image_url';
    text?: string;
    image_url?: { url: string };
}

interface ChatCompletionRequest {
    model?: string;
    messages: OpenAIMessage[];
    stream?: boolean;
    temperature?: number;
    max_tokens?: number;
}

interface OpenAIError {
    error: {
        message: string;
        type: string;
        code: string | null;
    };
}

// ── Helpers ────────────────────────────────────────────────────────────────

function generateId(): string {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let id = 'chatcmpl-';
    for (let i = 0; i < 24; i++) {
        id += chars[Math.floor(Math.random() * chars.length)];
    }
    return id;
}

function makeErrorJson(message: string, type: string, code: string | null = null): string {
    const body: OpenAIError = { error: { message, type, code } };
    return JSON.stringify(body);
}

/** Parse a data-URL into its MIME type and raw bytes. */
function parseDataUrl(dataUrl: string): { mime: string; data: Uint8Array } | null {
    const match = dataUrl.match(/^data:([^;]+);base64,(.+)$/);
    if (!match) {
        return null;
    }
    const mime = match[1];
    const data = Uint8Array.from(Buffer.from(match[2], 'base64'));
    return { mime, data };
}

/** Set CORS headers so the Python backend on a different port can reach us. */
function setCorsHeaders(res: http.ServerResponse): void {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
}

function sendJson(res: http.ServerResponse, status: number, body: string): void {
    setCorsHeaders(res);
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(body);
}

// ── LmProxyServer ──────────────────────────────────────────────────────────

const DEFAULT_PORT = 3001;
const MAX_PORT_ATTEMPTS = 20;

export class LmProxyServer {
    private server: http.Server | null = null;
    private port = 0;
    private cachedModels: vscode.LanguageModelChat[] = [];
    private modelsLastRefreshed = 0;
    private readonly modelCacheTtlMs = 60_000;
    private readonly outputChannel: vscode.LogOutputChannel;

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('LM Proxy', { log: true });
    }

    /** Start the HTTP server. Returns the port it's listening on. */
    async start(preferredPort?: number): Promise<number> {
        if (this.server) {
            return this.port;
        }

        this.server = http.createServer((req, res) => {
            this.handleRequest(req, res);
        });

        const startPort = preferredPort && preferredPort > 0 ? preferredPort : DEFAULT_PORT;
        this.port = await this.listen(this.server, startPort);
        this.outputChannel.info(`LM Proxy server listening on http://127.0.0.1:${this.port}`);
        return this.port;
    }

    /** Stop the HTTP server. */
    async stop(): Promise<void> {
        return new Promise((resolve) => {
            if (!this.server) {
                resolve();
                return;
            }
            this.server.close(() => {
                this.server = null;
                this.port = 0;
                this.outputChannel.info('LM Proxy server stopped');
                resolve();
            });
        });
    }

    /** Return the port the server is currently listening on (0 if not started). */
    getPort(): number {
        return this.port;
    }

    // ── Private: port binding ──────────────────────────────────────────────

    private listen(server: http.Server, startPort: number): Promise<number> {
        return new Promise((resolve, reject) => {
            let attempt = 0;
            const tryPort = (port: number): void => {
                server.once('error', (err: NodeJS.ErrnoException) => {
                    if (err.code === 'EADDRINUSE' && attempt < MAX_PORT_ATTEMPTS) {
                        attempt++;
                        tryPort(port + 1);
                    } else {
                        reject(err);
                    }
                });
                server.listen(port, '127.0.0.1', () => {
                    resolve(port);
                });
            };
            tryPort(startPort);
        });
    }

    // ── Private: request router ────────────────────────────────────────────

    private handleRequest(req: http.IncomingMessage, res: http.ServerResponse): void {
        // CORS preflight
        if (req.method === 'OPTIONS') {
            setCorsHeaders(res);
            res.writeHead(204);
            res.end();
            return;
        }

        const url = req.url ?? '/';

        if (req.method === 'GET' && url === '/health') {
            this.handleHealth(res);
            return;
        }

        if (req.method === 'POST' && url === '/v1/chat/completions') {
            this.handleChatCompletions(req, res);
            return;
        }

        sendJson(res, 404, makeErrorJson(`Not found: ${req.method} ${url}`, 'invalid_request_error'));
    }

    // ── Private: /health ───────────────────────────────────────────────────

    private handleHealth(res: http.ServerResponse): void {
        this.getModels()
            .then((models) => {
                const body = JSON.stringify({
                    status: 'ok',
                    models: models.map((m) => ({ id: m.id, name: m.name, family: m.family, vendor: m.vendor })),
                });
                sendJson(res, 200, body);
            })
            .catch((err: unknown) => {
                const message = err instanceof Error ? err.message : String(err);
                sendJson(res, 503, makeErrorJson(`Model lookup failed: ${message}`, 'server_error'));
            });
    }

    // ── Private: /v1/chat/completions ──────────────────────────────────────

    private handleChatCompletions(req: http.IncomingMessage, res: http.ServerResponse): void {
        this.readBody(req)
            .then(async (raw) => {
                let body: ChatCompletionRequest;
                try {
                    body = JSON.parse(raw) as ChatCompletionRequest;
                } catch {
                    sendJson(res, 400, makeErrorJson('Invalid JSON in request body', 'invalid_request_error'));
                    return;
                }

                if (!body.messages || !Array.isArray(body.messages) || body.messages.length === 0) {
                    sendJson(res, 400, makeErrorJson('"messages" is required and must be a non-empty array', 'invalid_request_error'));
                    return;
                }

                const model = await this.selectModel(body.model);
                if (!model) {
                    sendJson(
                        res,
                        503,
                        makeErrorJson(
                            'No Copilot language models are currently available. Make sure GitHub Copilot is signed in and active.',
                            'model_not_available',
                        ),
                    );
                    return;
                }

                const messages = this.translateMessages(body.messages);
                const cts = new vscode.CancellationTokenSource();

                // Abort on client disconnect
                req.on('close', () => cts.cancel());

                const options: vscode.LanguageModelChatRequestOptions = {
                    justification: 'LM Proxy: backend pipeline request',
                    modelOptions: {},
                };
                if (body.temperature !== undefined && options.modelOptions) {
                    options.modelOptions['temperature'] = body.temperature;
                }
                if (body.max_tokens !== undefined && options.modelOptions) {
                    options.modelOptions['max_tokens'] = body.max_tokens;
                }

                try {
                    const chatResponse = await model.sendRequest(messages, options, cts.token);

                    if (body.stream) {
                        await this.sendStreaming(res, chatResponse, model.id);
                    } else {
                        await this.sendNonStreaming(res, chatResponse, model.id);
                    }
                } catch (err: unknown) {
                    if (cts.token.isCancellationRequested) {
                        // Client disconnected — nothing to send
                        return;
                    }
                    this.outputChannel.error('Chat completion error', err instanceof Error ? err.message : String(err));
                    const { status, json } = this.mapLmError(err);
                    sendJson(res, status, json);
                } finally {
                    cts.dispose();
                }
            })
            .catch((err: unknown) => {
                const message = err instanceof Error ? err.message : String(err);
                sendJson(res, 500, makeErrorJson(`Internal error: ${message}`, 'server_error'));
            });
    }

    // ── Private: message translation ───────────────────────────────────────

    private translateMessages(messages: OpenAIMessage[]): vscode.LanguageModelChatMessage[] {
        const result: vscode.LanguageModelChatMessage[] = [];
        let systemPrefix = '';

        for (const msg of messages) {
            if (msg.role === 'system') {
                // Copilot models don't have a separate system role —
                // accumulate system content and prepend to the next user message.
                const text = typeof msg.content === 'string' ? msg.content : this.flattenTextParts(msg.content);
                systemPrefix += (systemPrefix ? '\n\n' : '') + text;
                continue;
            }

            if (msg.role === 'assistant') {
                // Flush any pending system prefix as a user message before assistant
                if (systemPrefix) {
                    result.push(vscode.LanguageModelChatMessage.User(systemPrefix));
                    systemPrefix = '';
                }
                const text = typeof msg.content === 'string' ? msg.content : this.flattenTextParts(msg.content);
                result.push(vscode.LanguageModelChatMessage.Assistant(text));
                continue;
            }

            // role === 'user'
            const parts = this.buildUserParts(msg.content, systemPrefix);
            systemPrefix = '';
            result.push(vscode.LanguageModelChatMessage.User(parts));
        }

        // If there's a trailing system message with no subsequent user message, emit it as user
        if (systemPrefix) {
            result.push(vscode.LanguageModelChatMessage.User(systemPrefix));
        }

        return result;
    }

    private buildUserParts(
        content: string | OpenAIContentPart[],
        systemPrefix: string,
    ): Array<vscode.LanguageModelTextPart | vscode.LanguageModelDataPart> {
        const parts: Array<vscode.LanguageModelTextPart | vscode.LanguageModelDataPart> = [];

        if (systemPrefix) {
            parts.push(new vscode.LanguageModelTextPart(systemPrefix + '\n\n'));
        }

        if (typeof content === 'string') {
            parts.push(new vscode.LanguageModelTextPart(content));
            return parts;
        }

        for (const part of content) {
            if (part.type === 'text' && part.text !== undefined) {
                parts.push(new vscode.LanguageModelTextPart(part.text));
            } else if (part.type === 'image_url' && part.image_url?.url) {
                const parsed = parseDataUrl(part.image_url.url);
                if (parsed) {
                    parts.push(vscode.LanguageModelDataPart.image(parsed.data, parsed.mime));
                } else {
                    // Non-base64 URLs can't be sent through the LM API; include as text fallback
                    parts.push(new vscode.LanguageModelTextPart(`[Image: ${part.image_url.url.substring(0, 120)}]`));
                }
            }
        }

        return parts;
    }

    private flattenTextParts(content: OpenAIContentPart[]): string {
        return content
            .filter((p) => p.type === 'text' && p.text !== undefined)
            .map((p) => p.text!)
            .join('\n');
    }

    // ── Private: streaming response ────────────────────────────────────────

    private async sendStreaming(
        res: http.ServerResponse,
        chatResponse: vscode.LanguageModelChatResponse,
        modelId: string,
    ): Promise<void> {
        const completionId = generateId();

        setCorsHeaders(res);
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        });

        for await (const fragment of chatResponse.text) {
            if (res.destroyed) {
                break;
            }
            const chunk = JSON.stringify({
                id: completionId,
                object: 'chat.completion.chunk',
                model: modelId,
                choices: [{ index: 0, delta: { content: fragment }, finish_reason: null }],
            });
            res.write(`data: ${chunk}\n\n`);
        }

        if (!res.destroyed) {
            const done = JSON.stringify({
                id: completionId,
                object: 'chat.completion.chunk',
                model: modelId,
                choices: [{ index: 0, delta: {}, finish_reason: 'stop' }],
            });
            res.write(`data: ${done}\n\n`);
            res.write('data: [DONE]\n\n');
        }

        res.end();
    }

    // ── Private: non-streaming response ────────────────────────────────────

    private async sendNonStreaming(
        res: http.ServerResponse,
        chatResponse: vscode.LanguageModelChatResponse,
        modelId: string,
    ): Promise<void> {
        let fullText = '';
        for await (const fragment of chatResponse.text) {
            fullText += fragment;
        }

        const body = JSON.stringify({
            id: generateId(),
            object: 'chat.completion',
            model: modelId,
            choices: [
                {
                    index: 0,
                    message: { role: 'assistant', content: fullText },
                    finish_reason: 'stop',
                },
            ],
            usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
        });

        sendJson(res, 200, body);
    }

    // ── Private: model selection ───────────────────────────────────────────

    private async getModels(): Promise<vscode.LanguageModelChat[]> {
        const now = Date.now();
        if (this.cachedModels.length > 0 && now - this.modelsLastRefreshed < this.modelCacheTtlMs) {
            return this.cachedModels;
        }
        this.cachedModels = await vscode.lm.selectChatModels();
        this.modelsLastRefreshed = now;
        return this.cachedModels;
    }

    private async selectModel(requestedModel?: string): Promise<vscode.LanguageModelChat | undefined> {
        const models = await this.getModels();
        if (models.length === 0) {
            return undefined;
        }

        // If a specific model ID or family was requested, try to match it
        if (requestedModel && requestedModel !== 'copilot-auto') {
            const stripped = requestedModel.replace(/^copilot-/, '');
            const exact = models.find((m) => m.id === requestedModel || m.id === stripped);
            if (exact) {
                return exact;
            }
            const byFamily = models.find(
                (m) => m.family === stripped || m.family.includes(stripped) || m.id.includes(stripped),
            );
            if (byFamily) {
                return byFamily;
            }
        }

        // Prefer gpt-4o for best quality / vision support
        const gpt4o = models.find((m) => m.family.includes('gpt-4o') || m.id.includes('gpt-4o'));
        if (gpt4o) {
            return gpt4o;
        }

        // Fall back to any available model
        return models[0];
    }

    // ── Private: error mapping ─────────────────────────────────────────────

    private mapLmError(err: unknown): { status: number; json: string } {
        if (err instanceof vscode.LanguageModelError) {
            if (err.code === 'NoPermissions') {
                return { status: 403, json: makeErrorJson(err.message, 'permission_error', 'no_permissions') };
            }
            if (err.code === 'Blocked') {
                return { status: 429, json: makeErrorJson(err.message, 'rate_limit_error', 'blocked') };
            }
            if (err.code === 'NotFound') {
                return { status: 404, json: makeErrorJson(err.message, 'model_not_found', 'not_found') };
            }
        }
        const message = err instanceof Error ? err.message : String(err);
        return { status: 500, json: makeErrorJson(message, 'server_error') };
    }

    // ── Private: body reading ──────────────────────────────────────────────

    private readBody(req: http.IncomingMessage): Promise<string> {
        return new Promise((resolve, reject) => {
            const chunks: Buffer[] = [];
            req.on('data', (chunk: Buffer) => chunks.push(chunk));
            req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
            req.on('error', reject);
        });
    }
}
