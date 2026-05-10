import * as assert from 'assert';
import { formatPipelineProgress, createDefaultStages, PipelineStage } from '../utils/progress';

describe('progress utilities', () => {
    describe('createDefaultStages', () => {
        it('should create 6 default stages', () => {
            const stages = createDefaultStages();
            assert.strictEqual(stages.length, 6);
        });

        it('should have all stages as pending', () => {
            const stages = createDefaultStages();
            assert.ok(stages.every(s => s.status === 'pending'));
        });

        it('should include expected stage names', () => {
            const stages = createDefaultStages();
            const names = stages.map(s => s.name);
            assert.ok(names.includes('Ingestion'));
            assert.ok(names.includes('Extraction'));
            assert.ok(names.includes('Quality Evaluation'));
        });
    });

    describe('formatPipelineProgress', () => {
        it('should format stages with status icons', () => {
            const stages: PipelineStage[] = [
                { name: 'Ingestion', status: 'done' },
                { name: 'Extraction', status: 'running' },
                { name: 'Writing', status: 'pending' },
            ];
            const result = formatPipelineProgress(stages);
            assert.ok(result.includes('✅'));
            assert.ok(result.includes('🔄'));
            assert.ok(result.includes('⬜'));
            assert.ok(result.includes('Ingestion'));
        });

        it('should include detail text when present', () => {
            const stages: PipelineStage[] = [
                { name: 'Extraction', status: 'running', detail: 'Processing frames' },
            ];
            const result = formatPipelineProgress(stages);
            assert.ok(result.includes('Processing frames'));
        });

        it('should show error icon for failed stages', () => {
            const stages: PipelineStage[] = [
                { name: 'Ingestion', status: 'error' },
            ];
            const result = formatPipelineProgress(stages);
            assert.ok(result.includes('❌'));
        });
    });
});
