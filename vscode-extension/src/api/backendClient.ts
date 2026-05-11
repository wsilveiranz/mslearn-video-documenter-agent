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

export interface DocumentResponse {
    document_id: string;
    doc_type: string;
    markdown_content: string;
    word_count: number;
    revision_number: number;
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

    constructor(config?: BackendConfig) {
        this.baseUrl = (config?.baseUrl ?? getBackendUrl()).replace(/\/$/, '');
    }

    async checkHealth(): Promise<HealthResponse> {
        return this.get<HealthResponse>('/health');
    }

    async ingestVideo(filePath: string): Promise<IngestResponse> {
        const url = `${this.baseUrl}/api/v1/videos/ingest`;

        const fileBuffer = await fs.promises.readFile(filePath);
        const fileName = path.basename(filePath);

        const formData = new FormData();
        const blob = new Blob([fileBuffer]);
        formData.append('file', blob, fileName);

        const response = await fetch(url, {
            method: 'POST',
            body: formData,
        });

        return this.handleResponse<IngestResponse>(response);
    }

    async ingestVideoByPath(videoPath: string): Promise<IngestResponse> {
        const url = `${this.baseUrl}/api/v1/videos/ingest`;

        const formData = new FormData();
        formData.append('video_path', videoPath);

        const response = await fetch(url, {
            method: 'POST',
            body: formData,
        });

        return this.handleResponse<IngestResponse>(response);
    }

    async getVideoStatus(videoId: string): Promise<StatusResponse> {
        return this.get<StatusResponse>(`/videos/${videoId}/status`);
    }

    async extractVideo(videoId: string): Promise<GenerateResponse> {
        return this.post<GenerateResponse>(`/videos/${videoId}/extract`, {});
    }

    async getExtractionResults(videoId: string): Promise<Record<string, unknown>> {
        return this.get<Record<string, unknown>>(`/videos/${videoId}/extraction`);
    }

    async assessQuality(videoId: string): Promise<DataQualityResponse> {
        return this.post<DataQualityResponse>(`/videos/${videoId}/assess-quality`, {});
    }

    async generateDocument(
        videoId: string,
        docType: string,
        supplementaryContext: string = '',
        metadata?: BackendMetadata
    ): Promise<GenerateResponse> {
        const body: Record<string, unknown> = {
            video_id: videoId,
            doc_type: docType,
            supplementary_context: supplementaryContext,
        };
        if (metadata) {
            body.metadata = metadata;
        }
        return this.post<GenerateResponse>('/documents/generate', body);
    }

    async getDocument(documentId: string): Promise<DocumentResponse> {
        return this.get<DocumentResponse>(`/documents/${documentId}`);
    }

    async refineDocument(documentId: string, feedback: string): Promise<GenerateResponse> {
        return this.post<GenerateResponse>(`/documents/${documentId}/refine`, { feedback });
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
        const response = await fetch(url);
        return this.handleResponse<T>(response);
    }

    private async post<T>(apiPath: string, body: Record<string, unknown>): Promise<T> {
        const url = `${this.baseUrl}/api/v1${apiPath}`;
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
