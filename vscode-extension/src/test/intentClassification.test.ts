import * as assert from 'assert';
import * as path from 'path';
import {
    classifyIntentFast,
    extractTargetPath,
    resolveTargetPathPure,
} from '../utils/intentClassification';

describe('classifyIntentFast', () => {

    // --- Should detect save intent ---

    it('should classify "save to c:\\temp\\" as save', () => {
        assert.strictEqual(classifyIntentFast('save to c:\\temp\\'), 'save');
    });

    it('should classify "save it to /home/user/docs" as save', () => {
        assert.strictEqual(classifyIntentFast('save it to /home/user/docs'), 'save');
    });

    it('should classify "export to D:\\output" as save', () => {
        assert.strictEqual(classifyIntentFast('export to D:\\output'), 'save');
    });

    it('should classify "save the document to ./output" as save', () => {
        assert.strictEqual(classifyIntentFast('save the document to ./output'), 'save');
    });

    it('should classify "please save to c:\\temp\\" as save', () => {
        assert.strictEqual(classifyIntentFast('please save to c:\\temp\\'), 'save');
    });

    it('should classify "copy it to c:\\docs" as save', () => {
        assert.strictEqual(classifyIntentFast('copy it to c:\\docs'), 'save');
    });

    it('should classify "write the doc to /tmp/" as save', () => {
        assert.strictEqual(classifyIntentFast('write the doc to /tmp/'), 'save');
    });

    it('should classify "save" (bare) as save', () => {
        assert.strictEqual(classifyIntentFast('save'), 'save');
    });

    it('should classify "export" (bare) as save', () => {
        assert.strictEqual(classifyIntentFast('export'), 'save');
    });

    it('should classify "save it" as save', () => {
        assert.strictEqual(classifyIntentFast('save it'), 'save');
    });

    it('should classify "export the file" as save', () => {
        assert.strictEqual(classifyIntentFast('export the file'), 'save');
    });

    it('should classify "save the markdown" as save', () => {
        assert.strictEqual(classifyIntentFast('save the markdown'), 'save');
    });

    it('should classify "write it as tutorial.md" as save', () => {
        assert.strictEqual(classifyIntentFast('write it as tutorial.md'), 'save');
    });

    it('should be case-insensitive', () => {
        assert.strictEqual(classifyIntentFast('SAVE TO C:\\TEMP\\'), 'save');
        assert.strictEqual(classifyIntentFast('Export The Document To /tmp'), 'save');
    });

    // --- Should NOT detect save intent (return undefined for LLM fallback) ---

    it('should return undefined for refinement feedback', () => {
        assert.strictEqual(classifyIntentFast('make the introduction more concise'), undefined);
    });

    it('should return undefined for content change requests', () => {
        assert.strictEqual(classifyIntentFast('add a note about prerequisites'), undefined);
    });

    it('should return undefined for general questions', () => {
        assert.strictEqual(classifyIntentFast('what commands are available?'), undefined);
    });

    it('should return undefined for ambiguous text', () => {
        assert.strictEqual(classifyIntentFast('can you fix the formatting?'), undefined);
    });

    it('should return undefined for empty input', () => {
        assert.strictEqual(classifyIntentFast(''), undefined);
    });

    it('should return undefined for whitespace-only input', () => {
        assert.strictEqual(classifyIntentFast('   '), undefined);
    });
});

describe('extractTargetPath', () => {

    // --- Windows paths ---

    it('should extract Windows absolute path from "save to c:\\temp\\"', () => {
        assert.strictEqual(extractTargetPath('save to c:\\temp\\'), 'c:\\temp\\');
    });

    it('should extract Windows path with subdirectories', () => {
        assert.strictEqual(
            extractTargetPath('save to C:\\Users\\demo\\Documents\\'),
            'C:\\Users\\demo\\Documents\\'
        );
    });

    it('should extract Windows path with forward slashes', () => {
        assert.strictEqual(extractTargetPath('save to C:/temp/output'), 'C:/temp/output');
    });

    // --- Unix paths ---

    it('should extract Unix absolute path', () => {
        assert.strictEqual(extractTargetPath('export to /home/user/docs'), '/home/user/docs');
    });

    it('should extract /tmp/ path', () => {
        assert.strictEqual(extractTargetPath('save to /tmp/'), '/tmp/');
    });

    // --- Relative paths ---

    it('should extract relative path starting with ./', () => {
        assert.strictEqual(extractTargetPath('save to ./output'), './output');
    });

    it('should extract relative path starting with ../', () => {
        assert.strictEqual(extractTargetPath('save to ../docs'), '../docs');
    });

    // --- Filenames ---

    it('should extract filename with extension', () => {
        assert.strictEqual(extractTargetPath('save as tutorial.md'), 'tutorial.md');
    });

    it('should extract filename with .txt extension', () => {
        assert.strictEqual(extractTargetPath('save as output.txt'), 'output.txt');
    });

    // --- Quoted paths ---

    it('should handle double-quoted paths', () => {
        assert.strictEqual(
            extractTargetPath('save to "C:\\path with spaces\\docs"'),
            'C:\\path with spaces\\docs'
        );
    });

    it('should handle single-quoted paths', () => {
        assert.strictEqual(
            extractTargetPath("save to '/home/user/my docs/'"),
            '/home/user/my docs/'
        );
    });

    // --- Verb variations ---

    it('should handle "export" verb', () => {
        assert.strictEqual(extractTargetPath('export to c:\\temp\\'), 'c:\\temp\\');
    });

    it('should handle "copy" verb', () => {
        assert.strictEqual(extractTargetPath('copy to c:\\temp\\'), 'c:\\temp\\');
    });

    it('should handle "write" verb', () => {
        assert.strictEqual(extractTargetPath('write to /tmp/doc.md'), '/tmp/doc.md');
    });

    it('should handle "please save" prefix', () => {
        assert.strictEqual(extractTargetPath('please save to c:\\temp\\'), 'c:\\temp\\');
    });

    it('should handle "save the document to" phrasing', () => {
        assert.strictEqual(
            extractTargetPath('save the document to c:\\output\\'),
            'c:\\output\\'
        );
    });

    // --- No path / invalid ---

    it('should return undefined for bare "save"', () => {
        assert.strictEqual(extractTargetPath('save'), undefined);
    });

    it('should return undefined for "save it"', () => {
        assert.strictEqual(extractTargetPath('save it'), undefined);
    });

    it('should return undefined for non-path text', () => {
        assert.strictEqual(extractTargetPath('make the introduction shorter'), undefined);
    });

    it('should return undefined for empty string', () => {
        assert.strictEqual(extractTargetPath(''), undefined);
    });
});

describe('resolveTargetPathPure', () => {

    const docId = 'doc-abc-123';

    it('should append document filename when target is a directory path', () => {
        const result = resolveTargetPathPure('C:\\temp\\', docId, true, false);
        assert.strictEqual(result, path.join('C:\\temp\\', `${docId}.md`));
    });

    it('should append document filename for Unix directory paths', () => {
        const result = resolveTargetPathPure('/tmp/', docId, true, false);
        // The path ends with / so it's treated as a directory
        assert.ok(result.endsWith(`${docId}.md`));
    });

    it('should append .md extension when no extension given', () => {
        const result = resolveTargetPathPure('C:\\temp\\output', docId, true, false);
        assert.strictEqual(result, 'C:\\temp\\output.md');
    });

    it('should preserve existing extension', () => {
        const result = resolveTargetPathPure('C:\\temp\\doc.txt', docId, true, false);
        assert.strictEqual(result, 'C:\\temp\\doc.txt');
    });

    it('should preserve .md extension', () => {
        const result = resolveTargetPathPure('C:\\temp\\tutorial.md', docId, true, false);
        assert.strictEqual(result, 'C:\\temp\\tutorial.md');
    });

    it('should resolve relative paths against workspace root', () => {
        const result = resolveTargetPathPure(
            'output',
            docId,
            false,
            false,
            'C:\\workspace'
        );
        assert.strictEqual(result, path.join('C:\\workspace', 'output.md'));
    });

    it('should not modify absolute paths with workspace root', () => {
        const result = resolveTargetPathPure(
            'C:\\temp\\doc.md',
            docId,
            true,
            false,
            'C:\\workspace'
        );
        assert.strictEqual(result, 'C:\\temp\\doc.md');
    });

    it('should append filename when isExistingDirectory is true', () => {
        const result = resolveTargetPathPure('C:\\temp', docId, true, true);
        assert.strictEqual(result, path.join('C:\\temp', `${docId}.md`));
    });

    it('should handle relative directory with workspace root', () => {
        const result = resolveTargetPathPure(
            './docs/',
            docId,
            false,
            false,
            'C:\\workspace'
        );
        const expected = path.join('C:\\workspace', 'docs', `${docId}.md`);
        assert.strictEqual(result, expected);
    });
});
