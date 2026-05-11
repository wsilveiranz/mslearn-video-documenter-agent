import * as vscode from 'vscode';

export type ProcessingStage = 
    | 'idle' 
    | 'analyzing' 
    | 'analyzed'
    | 'planned'
    | 'generating' 
    | 'generated' 
    | 'refining';

export interface DocumentMetadata {
    author: string;
    msAuthor: string;
    msService: string;
    customerIntent: string;
}

export interface ConversationState {
    currentVideoId?: string;
    currentVideoPath?: string;
    currentDocumentId?: string;
    currentStage: ProcessingStage;
    lastDocType?: string;
    savedFilename?: string;
    metadata?: DocumentMetadata;
    supplementaryContext?: string;
}

const STATE_KEY = 'videoDocumenter.conversationState';

const DEFAULT_STATE: ConversationState = {
    currentStage: 'idle',
};

export class ConversationStateManager {
    private state: ConversationState;

    constructor(private readonly context: vscode.ExtensionContext) {
        this.state = this.context.workspaceState.get<ConversationState>(STATE_KEY) ?? { ...DEFAULT_STATE };
    }

    getState(): Readonly<ConversationState> {
        return { ...this.state };
    }

    setVideoId(videoId: string, videoPath: string): void {
        this.state.currentVideoId = videoId;
        this.state.currentVideoPath = videoPath;
        this.persist();
    }

    setDocumentId(documentId: string): void {
        this.state.currentDocumentId = documentId;
        this.persist();
    }

    setStage(stage: ProcessingStage): void {
        this.state.currentStage = stage;
        this.persist();
    }

    setDocType(docType: string): void {
        this.state.lastDocType = docType;
        this.persist();
    }

    setSavedFilename(filename: string): void {
        this.state.savedFilename = filename;
        this.persist();
    }

    setMetadata(metadata: DocumentMetadata): void {
        this.state.metadata = metadata;
        this.persist();
    }

    setSupplementaryContext(context: string): void {
        this.state.supplementaryContext = context;
        this.persist();
    }

    reset(): void {
        this.state = { ...DEFAULT_STATE };
        this.persist();
    }

    private persist(): void {
        this.context.workspaceState.update(STATE_KEY, this.state);
    }
}

export function createStateManager(context: vscode.ExtensionContext): ConversationStateManager {
    return new ConversationStateManager(context);
}
