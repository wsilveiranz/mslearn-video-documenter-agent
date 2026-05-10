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
