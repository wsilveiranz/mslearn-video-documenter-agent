// Patch module resolution to redirect 'vscode' imports to the local mock.
// This file must be required before any module that transitively imports 'vscode'.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const Module = require('module') as {
    _resolveFilename: (request: string, ...args: unknown[]) => string;
};

const originalResolve = Module._resolveFilename;

Module._resolveFilename = function (request: string, ...args: unknown[]): string {
    if (request === 'vscode') {
        return require.resolve('./__mocks__/vscode');
    }
    // Redirect child_process to our mock for BackendProcessManager tests
    if (request === 'child_process' || request === 'node:child_process') {
        return require.resolve('./__mocks__/childProcess');
    }
    return originalResolve.apply(this, [request, ...args]);
};
