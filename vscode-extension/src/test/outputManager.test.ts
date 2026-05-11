import * as assert from 'assert';
import { sanitizeFilename } from '../utils/outputManager';

describe('sanitizeFilename', () => {
    it('passes through a clean filename', () => {
        assert.strictEqual(sanitizeFilename('my-doc.md'), 'my-doc.md');
    });

    it('appends .md when missing', () => {
        assert.strictEqual(sanitizeFilename('my-doc'), 'my-doc.md');
    });

    it('strips surrounding double quotes', () => {
        assert.strictEqual(sanitizeFilename('"my-doc.md"'), 'my-doc.md');
    });

    it('strips surrounding single quotes', () => {
        assert.strictEqual(sanitizeFilename("'my-doc.md'"), 'my-doc.md');
    });

    it('strips forward slashes', () => {
        assert.strictEqual(sanitizeFilename('path/to/my-doc.md'), 'pathtomy-doc.md');
    });

    it('strips backslashes', () => {
        assert.strictEqual(sanitizeFilename('path\\to\\my-doc.md'), 'pathtomy-doc.md');
    });

    it('strips .. segments', () => {
        assert.strictEqual(sanitizeFilename('../../etc/passwd.md'), 'etcpasswd.md');
    });

    it('trims whitespace', () => {
        assert.strictEqual(sanitizeFilename('  my-doc.md  '), 'my-doc.md');
    });

    it('falls back to document.md when empty after sanitization', () => {
        assert.strictEqual(sanitizeFilename('   '), 'document.md');
    });

    it('falls back to document.md when only .md remains', () => {
        assert.strictEqual(sanitizeFilename('.md'), 'document.md');
    });

    it('falls back to document.md for empty string', () => {
        assert.strictEqual(sanitizeFilename(''), 'document.md');
    });

    it('handles quotes-only input', () => {
        assert.strictEqual(sanitizeFilename('""'), 'document.md');
    });
});
