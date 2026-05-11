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
