import * as fs from 'fs';
import * as path from 'path';
import { getBackendUrl } from '../utils/config';

export interface IngestResponse {
    video_id: string;
    status: string;
    message: string;
}

export interface StatusResponse {
    video_id: string;
    status: string; // ProcessingStatus: "queued" | "ingesting" | "processing" | "extracting" | "structuring" | "writing" | "editing" | "evaluating" | "completed" | "failed"
    step: number;
    total_steps: number;
    current_stage: string;
    progress_detail?: string;
    document_id: string | null;
    extraction_summary: {
        transcript_segments: number;
        scenes: number;
        keyframes: number;
        has_vision_descriptions: boolean;
    } | null;
    data_quality: DataQualityResponse | null;
}

export interface GenerateResponse {
    document_id: string;
    status: string;
    message: string;
}

export interface ExtractionResponse {
    video_id: string;
    status: string;
    message: string;
}

export interface EvalScores {
    completeness: number;
    accuracy: number;
    style_compliance: number;
    readability: number;
    grounding: number;
    overall: number;
    passed: boolean;
}

export interface DocumentResponse {
    document_id: string;
    doc_type: string;
    markdown_content: string;
    word_count: number;
    revision_number: number;
    media_files: Array<{
        filename: string;
        output_path: string;
        alt_text: string;
    }>;
    eval_scores?: EvalScores;
}

export interface DataQualityResponse {
    quality_level: 'rich' | 'adequate' | 'thin' | 'minimal';
    transcript_assessment: string;
    visual_assessment: string;
    coverage_gaps: string[];
    warnings: string[];
    recommendations: string[];
    grounding_confidence: number;
    raw_metrics: Record<string, unknown>;
}

export interface HealthResponse {
    status: string;
    service: string;
}

export interface M365Document {
    title: string;
    content_preview: string;
    url: string;
    source_type: string;
}

export interface M365SearchResult {
    documents: M365Document[];
    summary: string;
    query: string;
    available: boolean;
}

export interface ProgressMessage {
    type: string; // "progress"
    video_id: string;
    stage: string;
    step: number;
    total_steps: number;
    detail: string;
}

export interface BackendConfig {
    baseUrl: string;
}

export interface BackendMetadata {
    author?: string;
    ms_author?: string;
    ms_service?: string;
    customer_intent?: string;
}

export interface Disposable {
    dispose(): void;
}

export class BackendClient {
    private readonly baseUrl: string;
    private sessionSecret: string | null = null;
    private secretFetchPromise: Promise<void> | null = null;
    private bootstrapToken: string | undefined;

    constructor(config?: BackendConfig) {
        this.baseUrl = (config?.baseUrl ?? getBackendUrl()).replace(/\/$/, '');
    }

    /** Set the bootstrap token used to authenticate session-secret retrieval. */
    setBootstrapToken(token: string): void {
        this.bootstrapToken = token;
    }

    /**
     * Fetch the one-time session secret from the backend.
     * Called automatically before requests; safe to call multiple times.
     */
    async fetchSessionSecret(bootstrapToken?: string): Promise<void> {
        if (this.sessionSecret) {
            return;
        }
        if (this.secretFetchPromise) {
            return this.secretFetchPromise;
        }
        this.secretFetchPromise = (async () => {
            try {
                const url = `${this.baseUrl}/api/v1/auth/session-secret`;
                const headers: Record<string, string> = {};
                if (bootstrapToken) {
                    headers['X-Bootstrap-Token'] = bootstrapToken;
                }
                const response = await fetch(url, { headers });
                if (response.ok) {
                    const data = await response.json() as { secret: string };
                    this.sessionSecret = data.secret;
                } else {
                    // Clear promise so next call retries
                    this.secretFetchPromise = null;
                }
            } catch {
                // Non-fatal: backend may not be ready yet — allow retry
                this.secretFetchPromise = null;
            }
        })();
        return this.secretFetchPromise;
    }

    async checkHealth(): Promise<HealthResponse> {
        const result = await this.get<HealthResponse>('/health');
        // Fetch session secret after first successful health check
        await this.fetchSessionSecret(this.bootstrapToken);
        return result;
    }

    async ingestVideo(filePath: string, model?: string): Promise<IngestResponse> {
        const url = `${this.baseUrl}/api/v1/videos/ingest`;

        const fileBuffer = await fs.promises.readFile(filePath);
        const fileName = path.basename(filePath);

        const formData = new FormData();
        const blob = new Blob([fileBuffer]);
        formData.append('file', blob, fileName);
        if (model) {
            formData.append('model', model);
        }

        const headers: Record<string, string> = {};
        if (this.sessionSecret) {
            headers['X-Session-Secret'] = this.sessionSecret;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: formData,
        });

        return this.handleResponse<IngestResponse>(response);
    }

    async ingestVideoByPath(videoPath: string, model?: string): Promise<IngestResponse> {
        const url = `${this.baseUrl}/api/v1/videos/ingest`;

        const formData = new FormData();
        formData.append('video_path', videoPath);
        if (model) {
            formData.append('model', model);
        }

        const headers: Record<string, string> = {};
        if (this.sessionSecret) {
            headers['X-Session-Secret'] = this.sessionSecret;
        }

        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: formData,
        });

        return this.handleResponse<IngestResponse>(response);
    }

    async getVideoStatus(videoId: string): Promise<StatusResponse> {
        return this.get<StatusResponse>(`/videos/${videoId}/status`);
    }

    async extractVideo(videoId: string, model?: string): Promise<ExtractionResponse> {
        return this.post<ExtractionResponse>(`/videos/${videoId}/extract`, { model: model ?? null });
    }

    async getExtractionResults(videoId: string): Promise<Record<string, unknown>> {
        return this.get<Record<string, unknown>>(`/videos/${videoId}/extraction`);
    }

    async assessQuality(videoId: string, model?: string): Promise<DataQualityResponse> {
        return this.post<DataQualityResponse>(`/videos/${videoId}/assess-quality`, { model: model ?? null });
    }

    async generateDocument(
        videoId: string,
        docType: string,
        supplementaryContext: string = '',
        metadata?: BackendMetadata,
        model?: string
    ): Promise<GenerateResponse> {
        const body: Record<string, unknown> = {
            video_id: videoId,
            doc_type: docType,
            supplementary_context: supplementaryContext,
        };
        if (metadata) {
            body.metadata = metadata;
        }
        if (model) {
            body.model = model;
        }
        return this.post<GenerateResponse>('/documents/generate', body);
    }

    async getDocument(documentId: string): Promise<DocumentResponse> {
        return this.get<DocumentResponse>(`/documents/${documentId}`);
    }

    async downloadMedia(documentId: string, filename: string): Promise<Buffer> {
        const url = `${this.baseUrl}/api/v1/documents/${documentId}/media/${encodeURIComponent(filename)}`;
        const headers: Record<string, string> = {};
        if (this.sessionSecret) {
            headers['X-Session-Secret'] = this.sessionSecret;
        }
        const response = await fetch(url, { headers });
        if (!response.ok) {
            const text = await response.text().catch(() => '');
            throw new BackendError(
                response.status,
                `Failed to download media '${filename}'${text ? `: ${text}` : ''}`,
            );
        }
        const arrayBuffer = await response.arrayBuffer();
        return Buffer.from(arrayBuffer);
    }

    async refineDocument(documentId: string, feedback: string, model?: string, enrichM365?: boolean): Promise<GenerateResponse> {
        const body: Record<string, unknown> = { feedback };
        if (model) {
            body.model = model;
        }
        if (enrichM365) {
            body.enrich_m365 = true;
        }
        return this.post<GenerateResponse>(`/documents/${documentId}/refine`, body);
    }

    /**
     * Search M365 for supplementary context via Work IQ.
     * Only call when the user explicitly requests context enrichment.
     */
    async searchM365Context(query: string, videoId?: string): Promise<M365SearchResult> {
        const body: Record<string, unknown> = { query };
        if (videoId) {
            body.video_id = videoId;
        }
        return this.post<M365SearchResult>('/context/search-m365', body);
    }

    /**
     * Convert a document file (docx, pdf, pptx, etc.) to Markdown via MarkItDown.
     * Returns the converted Markdown text, or an error object describing what went wrong.
     */
    async convertDocument(filePath: string): Promise<{ markdown: string; word_count: number } | { error: string }> {
        try {
            return await this.post<{ markdown: string; word_count: number }>('/context/convert-path', { path: filePath });
        } catch (e: unknown) {
            const message = e instanceof Error ? e.message : String(e);
            return { error: message };
        }
    }

    connectProgress(videoId: string, onProgress: (msg: ProgressMessage) => void): Disposable {
        // WebSocket global is available in Node.js 18+ (VS Code 1.82+)
        if (typeof WebSocket === 'undefined') {
            return { dispose: () => {} };
        }

        const wsUrl = this.baseUrl.replace(/^http/, 'ws') + `/api/v1/ws/progress/${videoId}`;
        const ws = new WebSocket(wsUrl);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(String(event.data)) as ProgressMessage;
                onProgress(data);
            } catch {
                // Ignore malformed messages
            }
        };

        ws.onerror = () => {
            // WebSocket errors are non-fatal — progress just won't stream
        };

        return {
            dispose: () => {
                if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                    ws.close();
                }
            },
        };
    }

    async pollForCompletion(
        videoId: string,
        onProgress?: (status: StatusResponse) => void,
        intervalMs: number = 2000,
        timeoutMs: number = 600000
    ): Promise<StatusResponse> {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            const status = await this.getVideoStatus(videoId);
            onProgress?.(status);

            if (status.status === 'completed' || status.status === 'failed') {
                return status;
            }

            await new Promise(resolve => setTimeout(resolve, intervalMs));
        }
        throw new Error(`Processing timed out after ${timeoutMs / 1000}s`);
    }

    private async get<T>(apiPath: string): Promise<T> {
        const url = `${this.baseUrl}/api/v1${apiPath}`;
        const headers: Record<string, string> = {};
        if (this.sessionSecret) {
            headers['X-Session-Secret'] = this.sessionSecret;
        }
        const response = await fetch(url, { headers });
        return this.handleResponse<T>(response);
    }

    private async post<T>(apiPath: string, body: Record<string, unknown>): Promise<T> {
        const url = `${this.baseUrl}/api/v1${apiPath}`;
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (this.sessionSecret) {
            headers['X-Session-Secret'] = this.sessionSecret;
        }
        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
        });
        return this.handleResponse<T>(response);
    }

    private async handleResponse<T>(response: Response): Promise<T> {
        if (!response.ok) {
            let detail = response.statusText;
            try {
                const errorBody = await response.json() as { detail?: string };
                if (errorBody.detail) {
                    detail = errorBody.detail;
                }
            } catch {
                // Use statusText if body parsing fails
            }
            throw new BackendError(response.status, detail);
        }
        return await response.json() as T;
    }
}

export class BackendError extends Error {
    constructor(
        public readonly statusCode: number,
        public readonly detail: string
    ) {
        super(`Backend error (${statusCode}): ${detail}`);
        this.name = 'BackendError';
    }
}
