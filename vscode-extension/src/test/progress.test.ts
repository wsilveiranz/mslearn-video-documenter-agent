import * as assert from 'assert';
import { formatPipelineProgress, createDefaultStages, PipelineStage, formatElapsed } from '../utils/progress';

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

    describe('formatElapsed', () => {
        it('should format seconds only when under 1 minute', () => {
            const start = Date.now() - 30_000; // 30 seconds ago
            const result = formatElapsed(start);
            assert.strictEqual(result, '30s elapsed');
        });

        it('should format minutes and seconds', () => {
            const start = Date.now() - 90_000; // 1m 30s ago
            const result = formatElapsed(start);
            assert.strictEqual(result, '1m 30s elapsed');
        });

        it('should pad seconds with zero', () => {
            const start = Date.now() - 300_000; // 5m 0s ago
            const result = formatElapsed(start);
            assert.strictEqual(result, '5m 00s elapsed');
        });

        it('should return 0s for future timestamps', () => {
            const start = Date.now() + 10_000; // future
            const result = formatElapsed(start);
            assert.strictEqual(result, '0s elapsed');
        });
    });
});
