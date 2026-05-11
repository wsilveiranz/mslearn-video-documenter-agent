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

    it('strips Windows-invalid characters', () => {
        assert.strictEqual(sanitizeFilename('my:doc*name?.md'), 'mydocname.md');
    });

    it('strips angle brackets and pipes', () => {
        assert.strictEqual(sanitizeFilename('file<name>|here.md'), 'filenamehere.md');
    });

    it('prefixes reserved Windows device names', () => {
        assert.strictEqual(sanitizeFilename('CON.md'), '_CON.md');
        assert.strictEqual(sanitizeFilename('prn.md'), '_prn.md');
        assert.strictEqual(sanitizeFilename('NUL'), '_NUL.md');
        assert.strictEqual(sanitizeFilename('COM1.md'), '_COM1.md');
        assert.strictEqual(sanitizeFilename('LPT9'), '_LPT9.md');
    });

    it('does not prefix non-reserved names', () => {
        assert.strictEqual(sanitizeFilename('CONTROL.md'), 'CONTROL.md');
        assert.strictEqual(sanitizeFilename('connect.md'), 'connect.md');
    });

    it('strips trailing dots and spaces from stem', () => {
        assert.strictEqual(sanitizeFilename('myfile...md'), 'myfile.md');
        assert.strictEqual(sanitizeFilename('myfile .md'), 'myfile.md');
    });
});
