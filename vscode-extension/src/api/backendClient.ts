/**
 * HTTP client for communicating with the Python FastAPI backend.
 * Stub implementation — will be connected in Phase 2.
 */

export interface BackendConfig {
    baseUrl: string;
}

export class BackendClient {
    private readonly baseUrl: string;

    constructor(config: BackendConfig = { baseUrl: 'http://localhost:8000' }) {
        this.baseUrl = config.baseUrl.replace(/\/$/, '');
    }

    async ingestVideo(_filePath: string): Promise<{ videoId: string }> {
        // TODO: POST /api/v1/videos/ingest with multipart upload
        throw new Error('Backend integration not yet implemented');
    }

    async getVideoStatus(_videoId: string): Promise<{ status: string; progress: number }> {
        // TODO: GET /api/v1/videos/{id}/status
        throw new Error('Backend integration not yet implemented');
    }

    async generateDocument(
        _videoId: string,
        _docType: string
    ): Promise<{ documentId: string }> {
        // TODO: POST /api/v1/documents/generate
        throw new Error('Backend integration not yet implemented');
    }

    async getDocument(_documentId: string): Promise<{ markdown: string }> {
        // TODO: GET /api/v1/documents/{id}
        throw new Error('Backend integration not yet implemented');
    }
}
