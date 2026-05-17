import * as assert from 'assert';
import { detectCompanions, getCompanionTips, getCompanionStatus, COMPANION_EXTENSIONS } from '../utils/companions';

// companions.ts calls vscode.extensions.getExtension, which is mocked in __mocks__/vscode.ts
// (returns undefined by default, i.e. no extensions installed).
// Tests that need specific availability states pass pre-built arrays to getCompanionTips().

describe('COMPANION_EXTENSIONS', () => {
    it('has the correct number of entries', () => {
        assert.strictEqual(COMPANION_EXTENSIONS.length, 3);
    });

    it('marks internal extensions correctly', () => {
        const publicExts = COMPANION_EXTENSIONS.filter(e => !e.internal);
        const internalExts = COMPANION_EXTENSIONS.filter(e => e.internal);
        assert.strictEqual(publicExts.length, 1);
        assert.strictEqual(internalExts.length, 2);
        assert.strictEqual(publicExts[0].id, 'docsmsft.docs-authoring-pack');
    });

    it('contains the expected extension IDs', () => {
        const ids = COMPANION_EXTENSIONS.map(e => e.id);
        assert.ok(ids.includes('docsmsft.docs-authoring-pack'));
        assert.ok(ids.includes('msft-content.content-mentor'));
        assert.ok(ids.includes('docsmsft.learn-authoring-assistant'));
    });
});

describe('detectCompanions', () => {
    it('returns an entry for each companion extension', () => {
        const result = detectCompanions();
        assert.strictEqual(result.length, COMPANION_EXTENSIONS.length);
    });

    it('marks all companions as unavailable when vscode mock returns undefined', () => {
        // The mock returns undefined for all getExtension calls
        const result = detectCompanions();
        assert.ok(result.every(c => !c.available));
    });

    it('preserves id, name, and internal fields from COMPANION_EXTENSIONS', () => {
        const result = detectCompanions();
        for (let i = 0; i < COMPANION_EXTENSIONS.length; i++) {
            assert.strictEqual(result[i].id, COMPANION_EXTENSIONS[i].id);
            assert.strictEqual(result[i].name, COMPANION_EXTENSIONS[i].name);
            assert.strictEqual(result[i].internal, COMPANION_EXTENSIONS[i].internal);
        }
    });
});

describe('getCompanionTips', () => {
    it('returns empty string when no companions are available', () => {
        const companions = COMPANION_EXTENSIONS.map(ext => ({ ...ext, available: false }));
        assert.strictEqual(getCompanionTips(companions), '');
    });

    it('includes Learn Authoring Pack tip when available', () => {
        const companions = COMPANION_EXTENSIONS.map(ext => ({
            ...ext,
            available: ext.id === 'docsmsft.docs-authoring-pack',
        }));
        const tips = getCompanionTips(companions);
        assert.ok(tips.includes('Learn Authoring Pack'));
        assert.ok(tips.includes('Learn Preview'));
    });

    it('includes Content Mentor tip when available', () => {
        const companions = COMPANION_EXTENSIONS.map(ext => ({
            ...ext,
            available: ext.id === 'msft-content.content-mentor',
        }));
        const tips = getCompanionTips(companions);
        assert.ok(tips.includes('Content Mentor'));
        assert.ok(tips.includes('@content-mentor'));
    });

    it('includes Learn Authoring Assistant tip when available', () => {
        const companions = COMPANION_EXTENSIONS.map(ext => ({
            ...ext,
            available: ext.id === 'docsmsft.learn-authoring-assistant',
        }));
        const tips = getCompanionTips(companions);
        assert.ok(tips.includes('Learn Authoring Assistant'));
        assert.ok(tips.includes('/suggestEdits'));
    });

    it('includes all tips when all companions are available', () => {
        const companions = COMPANION_EXTENSIONS.map(ext => ({ ...ext, available: true }));
        const tips = getCompanionTips(companions);
        assert.ok(tips.includes('Learn Authoring Pack'));
        assert.ok(tips.includes('Content Mentor'));
        assert.ok(tips.includes('Learn Authoring Assistant'));
        assert.ok(tips.includes('/suggestEdits'));
        assert.ok(tips.includes('@content-mentor'));
        assert.ok(tips.includes('Learn Preview'));
    });

    it('returns a non-empty string with header when at least one companion is available', () => {
        const companions = COMPANION_EXTENSIONS.map(ext => ({
            ...ext,
            available: ext.id === 'docsmsft.docs-authoring-pack',
        }));
        const tips = getCompanionTips(companions);
        assert.ok(tips.includes('Next steps with companion extensions'));
    });

    it('uses detectCompanions() when no argument is provided', () => {
        // The vscode mock returns undefined for all extensions, so result should be empty
        const tips = getCompanionTips();
        assert.strictEqual(tips, '');
    });
});

describe('getCompanionStatus', () => {
    it('returns a line for each companion extension', () => {
        const status = getCompanionStatus();
        const lines = status.split('\n');
        assert.strictEqual(lines.length, COMPANION_EXTENSIONS.length);
    });

    it('marks all as unavailable (❌) when vscode mock returns undefined', () => {
        const status = getCompanionStatus();
        assert.ok(!status.includes('✅'));
        assert.ok(status.includes('❌'));
    });

    it('includes scope labels (internal) and (public)', () => {
        const status = getCompanionStatus();
        assert.ok(status.includes('(internal)'));
        assert.ok(status.includes('(public)'));
    });
});
