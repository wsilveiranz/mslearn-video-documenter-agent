import * as assert from 'assert';
import { ConversationStateManager } from '../utils/conversationState';

// Minimal mock of vscode.Memento (workspaceState)
class MockMemento {
    private store: Record<string, unknown> = {};

    get<T>(key: string): T | undefined;
    get<T>(key: string, defaultValue: T): T;
    get<T>(key: string, defaultValue?: T): T | undefined {
        const val = this.store[key] as T | undefined;
        return val !== undefined ? val : defaultValue;
    }

    async update(key: string, value: unknown): Promise<void> {
        this.store[key] = value;
    }

    keys(): readonly string[] {
        return Object.keys(this.store);
    }
}

function createMockContext(): { workspaceState: MockMemento } {
    return { workspaceState: new MockMemento() };
}

describe('ConversationStateManager', () => {
    it('should start with idle state', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        const state = manager.getState();
        assert.strictEqual(state.currentStage, 'idle');
        assert.strictEqual(state.currentVideoId, undefined);
    });

    it('should set video ID and path', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        manager.setVideoId('vid123', '/path/to/video.mp4');
        const state = manager.getState();
        assert.strictEqual(state.currentVideoId, 'vid123');
        assert.strictEqual(state.currentVideoPath, '/path/to/video.mp4');
    });

    it('should set document ID', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        manager.setDocumentId('doc456');
        assert.strictEqual(manager.getState().currentDocumentId, 'doc456');
    });

    it('should set stage', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        manager.setStage('analyzing');
        assert.strictEqual(manager.getState().currentStage, 'analyzing');
        manager.setStage('generated');
        assert.strictEqual(manager.getState().currentStage, 'generated');
    });

    it('should set doc type', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        manager.setDocType('tutorial');
        assert.strictEqual(manager.getState().lastDocType, 'tutorial');
    });

    it('should reset to defaults', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        manager.setVideoId('vid', '/path');
        manager.setDocumentId('doc');
        manager.setStage('generated');
        manager.reset();
        const state = manager.getState();
        assert.strictEqual(state.currentStage, 'idle');
        assert.strictEqual(state.currentVideoId, undefined);
        assert.strictEqual(state.currentDocumentId, undefined);
    });

    it('should return a copy from getState (not a reference)', () => {
        const ctx = createMockContext();
        const manager = new ConversationStateManager(ctx as any);
        const state1 = manager.getState();
        manager.setStage('analyzing');
        const state2 = manager.getState();
        assert.strictEqual(state1.currentStage, 'idle');
        assert.strictEqual(state2.currentStage, 'analyzing');
    });
});
