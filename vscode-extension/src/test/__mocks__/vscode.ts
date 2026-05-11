// Minimal vscode mock for unit testing outside the extension host.
// Only the APIs actually used by tested modules are implemented here.

export const workspace = {
    getConfiguration: (_section: string) => ({
        get: <T>(_key: string, defaultValue?: T): T | undefined => defaultValue,
    }),
    workspaceFolders: undefined as unknown,
    openTextDocument: async () => ({}),
};

export const window = {
    showTextDocument: async () => ({}),
    showOpenDialog: async () => undefined,
    showQuickPick: async () => undefined,
    showErrorMessage: async (..._args: unknown[]): Promise<unknown> => undefined,
    createOutputChannel: (_name: string) => ({
        appendLine: (_msg: string) => {},
        append: (_msg: string) => {},
        show: () => {},
        dispose: () => {},
        clear: () => {},
    }),
};

export const commands = {
    executeCommand: async () => undefined,
};

export const Uri = {
    file: (path: string) => ({ fsPath: path, scheme: 'file' }),
    joinPath: (...args: unknown[]) => ({ fsPath: args.join('/') }),
};

export const ViewColumn = { One: 1, Two: 2 };

export const LanguageModelChatMessage = {
    User: (text: string) => ({ role: 'user', content: text }),
};

export const chat = {
    createChatParticipant: () => ({ iconPath: null }),
};

export const extensions = {
    getExtension: (_id: string) => undefined as unknown,
};
