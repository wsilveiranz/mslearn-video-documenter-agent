import * as assert from 'assert';
import * as path from 'path';
import {
    classifyIntentFast,
    extractTargetPath,
    parseLlmClassification,
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

    it('should defer "write it as tutorial.md" to LLM (ambiguous verb)', () => {
        assert.strictEqual(classifyIntentFast('write it as tutorial.md'), undefined);
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

    // --- Regression: must NOT match refinement phrased with save/write verbs ---

    it('should not match "write it in a more formal tone"', () => {
        assert.strictEqual(classifyIntentFast('write it in a more formal tone'), undefined);
    });

    it('should not match "write the document in a different style"', () => {
        assert.strictEqual(classifyIntentFast('write the document in a different style'), undefined);
    });

    it('should not match "save the doc in a shorter format"', () => {
        assert.strictEqual(classifyIntentFast('save the doc in a shorter format'), undefined);
    });

    it('should not match "copy it in a table format"', () => {
        assert.strictEqual(classifyIntentFast('copy it in a table format'), undefined);
    });

    it('should not match "write it in markdown format"', () => {
        assert.strictEqual(classifyIntentFast('write it in markdown format'), undefined);
    });

    it('should not match "save it as a bullet list"', () => {
        assert.strictEqual(classifyIntentFast('save it as a bullet list'), undefined);
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

    it('should return undefined for natural language with .md extension', () => {
        assert.strictEqual(extractTargetPath('rename file to file-abc.md'), undefined);
    });

    it('should return undefined for long natural language ending in extension', () => {
        assert.strictEqual(extractTargetPath('save the doc in a shorter format.md'), undefined);
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

describe('parseLlmClassification', () => {

    // --- Exact matches ---

    it('should parse "save" exactly', () => {
        assert.strictEqual(parseLlmClassification('save'), 'save');
    });

    it('should parse "refine" exactly', () => {
        assert.strictEqual(parseLlmClassification('refine'), 'refine');
    });

    it('should parse "general" exactly', () => {
        assert.strictEqual(parseLlmClassification('general'), 'general');
    });

    // --- Case insensitivity ---

    it('should handle uppercase "Save"', () => {
        assert.strictEqual(parseLlmClassification('Save'), 'save');
    });

    it('should handle all-caps "REFINE"', () => {
        assert.strictEqual(parseLlmClassification('REFINE'), 'refine');
    });

    it('should handle mixed case "General"', () => {
        assert.strictEqual(parseLlmClassification('General'), 'general');
    });

    // --- Trailing punctuation ---

    it('should handle trailing period "save."', () => {
        assert.strictEqual(parseLlmClassification('save.'), 'save');
    });

    it('should handle trailing period "refine."', () => {
        assert.strictEqual(parseLlmClassification('refine.'), 'refine');
    });

    // --- Whitespace ---

    it('should handle leading/trailing whitespace', () => {
        assert.strictEqual(parseLlmClassification('  save  '), 'save');
    });

    it('should handle newlines', () => {
        assert.strictEqual(parseLlmClassification('\nrefine\n'), 'refine');
    });

    // --- Verbose LLM responses ---

    it('should extract "save" from verbose response', () => {
        assert.strictEqual(parseLlmClassification('The category is save'), 'save');
    });

    it('should extract "refine" from verbose response', () => {
        assert.strictEqual(parseLlmClassification('I would classify this as refine'), 'refine');
    });

    it('should extract "general" from verbose response', () => {
        assert.strictEqual(parseLlmClassification('This is a general question'), 'general');
    });

    // --- Quoted responses ---

    it('should handle double-quoted "save"', () => {
        assert.strictEqual(parseLlmClassification('"save"'), 'save');
    });

    it('should handle single-quoted \'refine\'', () => {
        assert.strictEqual(parseLlmClassification("'refine'"), 'refine');
    });

    // --- Fallback behaviour ---

    it('should default to "refine" for unrecognised response', () => {
        assert.strictEqual(parseLlmClassification('I don\'t know'), 'refine');
    });

    it('should default to "refine" for empty string', () => {
        assert.strictEqual(parseLlmClassification(''), 'refine');
    });

    it('should default to "refine" for gibberish', () => {
        assert.strictEqual(parseLlmClassification('asdfghjkl'), 'refine');
    });

    // --- Priority when multiple keywords appear ---

    it('should prioritise "save" over "refine" when both appear', () => {
        assert.strictEqual(parseLlmClassification('save not refine'), 'save');
    });

    it('should prioritise "general" over "refine" when both appear', () => {
        assert.strictEqual(parseLlmClassification('this is general not refine'), 'general');
    });
});
