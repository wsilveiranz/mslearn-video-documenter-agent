import * as assert from 'assert';
import { BackendError } from '../api/backendClient';

describe('BackendError', () => {
    it('should store statusCode and detail', () => {
        const err = new BackendError(404, 'Not found');
        assert.strictEqual(err.statusCode, 404);
        assert.strictEqual(err.detail, 'Not found');
        assert.strictEqual(err.name, 'BackendError');
    });

    it('should have descriptive message', () => {
        const err = new BackendError(500, 'Internal error');
        assert.ok(err.message.includes('500'));
        assert.ok(err.message.includes('Internal error'));
    });

    it('should be an instance of Error', () => {
        const err = new BackendError(400, 'Bad request');
        assert.ok(err instanceof Error);
        assert.ok(err instanceof BackendError);
    });
});
