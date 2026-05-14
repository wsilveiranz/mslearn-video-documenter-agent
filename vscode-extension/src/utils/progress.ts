export interface PipelineStage {
    name: string;
    status: 'pending' | 'running' | 'done' | 'error';
    detail?: string;
}

const STATUS_ICONS: Record<PipelineStage['status'], string> = {
    pending: '⬜',
    running: '🔄',
    done: '✅',
    error: '❌',
};

export function formatPipelineProgress(stages: PipelineStage[]): string {
    const lines = stages.map(
        (s) => `${STATUS_ICONS[s.status]} ${s.name}${s.detail ? ` — ${s.detail}` : ''}`
    );
    return '**Pipeline Progress:**\n' + lines.join('\n');
}

export function createDefaultStages(): PipelineStage[] {
    return [
        { name: 'Ingestion', status: 'pending' },
        { name: 'Extraction', status: 'pending' },
        { name: 'Structure Analysis', status: 'pending' },
        { name: 'Document Generation', status: 'pending' },
        { name: 'Style Editing', status: 'pending' },
        { name: 'Quality Evaluation', status: 'pending' },
    ];
}

/**
 * Format elapsed time since `startTime` as a human-readable string.
 *
 * Examples: `"30s elapsed"`, `"1m 30s elapsed"`, `"5m 00s elapsed"`.
 */
export function formatElapsed(startTime: number): string {
    const elapsedMs = Date.now() - startTime;
    const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    if (minutes > 0) {
        return `${minutes}m ${seconds.toString().padStart(2, '0')}s elapsed`;
    }
    return `${totalSeconds}s elapsed`;
}
