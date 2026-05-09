import * as vscode from 'vscode';

export function registerAnalyzeFileCommand(context: vscode.ExtensionContext): void {
    const command = vscode.commands.registerCommand(
        'video-documenter.analyzeFile',
        async (uri?: vscode.Uri) => {
            let filePath: string | undefined;

            if (uri) {
                // Invoked from context menu
                filePath = uri.fsPath;
            } else {
                // Invoked from command palette — show file picker
                const result = await vscode.window.showOpenDialog({
                    canSelectFiles: true,
                    canSelectFolders: false,
                    canSelectMany: false,
                    filters: {
                        'Video Files': ['mp4', 'avi', 'mov', 'mkv', 'webm'],
                    },
                    title: 'Select a video file to analyze',
                });

                if (result && result.length > 0) {
                    filePath = result[0].fsPath;
                }
            }

            if (!filePath) {
                return;
            }

            // Open Copilot Chat with the analyze command
            await vscode.commands.executeCommand(
                'workbench.action.chat.open',
                {
                    query: `@video-documenter /analyze ${filePath}`,
                }
            );
        }
    );

    context.subscriptions.push(command);
}
