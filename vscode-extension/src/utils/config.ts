import * as vscode from 'vscode';

function getConfig(): vscode.WorkspaceConfiguration {
    return vscode.workspace.getConfiguration('video-documenter');
}

export function getBackendUrl(): string {
    return getConfig().get<string>('backendUrl', 'http://localhost:8000').replace(/\/$/, '');
}

export function getOutputDirectory(): string {
    return getConfig().get<string>('outputDirectory', 'docs');
}

export function getAutoOpenPreview(): boolean {
    return getConfig().get<boolean>('autoOpenPreview', true);
}

export function getAutoStartBackend(): boolean {
    return getConfig().get<boolean>('autoStartBackend', true);
}

export function getBackendPath(): string {
    return getConfig().get<string>('backendPath', '');
}

export function getProcessingMode(): 'local' | 'cloud' {
    return getConfig().get<'local' | 'cloud'>('processingMode', 'local');
}

export function getFoundryProjectEndpoint(): string {
    return getConfig().get<string>('foundryProjectEndpoint', '');
}

export function getFoundryModel(): string {
    return getConfig().get<string>('foundryModel', 'gpt-4o');
}

export function getFoundryModelMini(): string {
    return getConfig().get<string>('foundryModelMini', 'gpt-4o-mini');
}

export function getBlobAccountUrl(): string {
    return getConfig().get<string>('blobAccountUrl', '');
}

export function getBlobContainerName(): string {
    return getConfig().get<string>('blobContainerName', 'video-documenter');
}

export function getSpeechServiceEndpoint(): string {
    return getConfig().get<string>('speechServiceEndpoint', '');
}

export function getSpeechServiceRegion(): string {
    return getConfig().get<string>('speechServiceRegion', 'eastus');
}

export function getVideoIndexerAccountId(): string {
    return getConfig().get<string>('videoIndexerAccountId', '');
}

export function getVideoIndexerResourceId(): string {
    return getConfig().get<string>('videoIndexerResourceId', '');
}

export function getVideoIndexerLocation(): string {
    return getConfig().get<string>('videoIndexerLocation', 'trial');
}

export function getWhisperModel(): string {
    return getConfig().get<string>('whisperModel', 'base');
}

export function getFfmpegPath(): string {
    return getConfig().get<string>('ffmpegPath', 'ffmpeg');
}
