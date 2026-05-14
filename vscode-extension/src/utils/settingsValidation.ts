import * as vscode from 'vscode';
import { getProcessingMode, getFoundryProjectEndpoint, getBlobAccountUrl, getVideoIndexerAccountId, getVideoIndexerResourceId, getSpeechServiceEndpoint } from './config';

/**
 * Validate that required settings are configured for the selected processing mode.
 * Shows a warning notification if cloud mode is selected but key Azure settings are missing.
 */
export function validateSettings(): void {
    if (getProcessingMode() !== 'cloud') {
        return;
    }

    const missing: string[] = [];

    if (!getFoundryProjectEndpoint()) {
        missing.push('Foundry Project Endpoint');
    }
    if (!getBlobAccountUrl()) {
        missing.push('Blob Account URL');
    }
    if (!getVideoIndexerAccountId()) {
        missing.push('Video Indexer Account ID');
    }
    if (!getVideoIndexerResourceId()) {
        missing.push('Video Indexer Resource ID');
    }
    if (!getSpeechServiceEndpoint()) {
        missing.push('Speech Service Endpoint');
    }

    if (missing.length > 0) {
        const message = `Video Documenter: Cloud mode is selected but required settings are missing: ${missing.join(', ')}. Configure them in Settings.`;
        void vscode.window.showWarningMessage(message, 'Open Settings').then(action => {
            if (action === 'Open Settings') {
                void vscode.commands.executeCommand(
                    'workbench.action.openSettings',
                    'video-documenter'
                );
            }
        });
    }
}
