import * as vscode from 'vscode';
import { detectVideoPath } from './utils/fileDetection';

export function createChatHandler(
    _extensionContext: vscode.ExtensionContext
): vscode.ChatRequestHandler {
    return async (
        request: vscode.ChatRequest,
        context: vscode.ChatContext,
        stream: vscode.ChatResponseStream,
        token: vscode.CancellationToken
    ): Promise<vscode.ChatResult> => {
        const command = request.command;

        if (command === 'analyze') {
            return handleAnalyze(request, stream, token);
        } else if (command === 'generate') {
            return handleGenerate(request, stream, token);
        } else if (command === 'refine') {
            return handleRefine(request, stream, token);
        } else if (command === 'status') {
            return handleStatus(stream);
        }

        // Default: conversational mode
        return handleConversation(request, stream, token);
    };
}

async function handleAnalyze(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    _token: vscode.CancellationToken
): Promise<vscode.ChatResult> {
    const videoPath = detectVideoPath(request.prompt);

    if (!videoPath) {
        stream.markdown(
            '📹 No video path detected. Please provide a path to a video file:\n\n' +
            '```\n@video-documenter /analyze C:\\path\\to\\video.mp4\n```\n\n' +
            'Or right-click a video file in the Explorer and select **"Analyze with Video Documenter"**.'
        );
        return { metadata: { command: 'analyze' } };
    }

    // TODO: Send to backend for processing
    stream.markdown(
        `📹 **Analyzing video:** \`${videoPath}\`\n\n` +
        '⏳ This is a scaffold — backend integration coming in Phase 2.\n\n' +
        '**Pipeline stages:**\n' +
        '1. ⬜ Ingestion\n' +
        '2. ⬜ Extraction\n' +
        '3. ⬜ Structure Analysis\n' +
        '4. ⬜ Document Generation\n' +
        '5. ⬜ Style Editing\n' +
        '6. ⬜ Quality Evaluation\n'
    );

    return { metadata: { command: 'analyze' } };
}

async function handleGenerate(
    _request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    _token: vscode.CancellationToken
): Promise<vscode.ChatResult> {
    stream.markdown(
        '📝 **Generate** command received.\n\n' +
        '⏳ This is a scaffold — document generation coming in Phase 2.\n\n' +
        'Once a video is analyzed, this command will generate MS Learn documentation ' +
        'in your chosen format (Quickstart, Tutorial, How-to, Concept, or Overview).'
    );
    return { metadata: { command: 'generate' } };
}

async function handleRefine(
    _request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    _token: vscode.CancellationToken
): Promise<vscode.ChatResult> {
    stream.markdown(
        '✏️ **Refine** command received.\n\n' +
        '⏳ This is a scaffold — refinement coming in Phase 2.\n\n' +
        'Use this command to iteratively improve specific sections of generated documentation.'
    );
    return { metadata: { command: 'refine' } };
}

async function handleStatus(
    stream: vscode.ChatResponseStream
): Promise<vscode.ChatResult> {
    stream.markdown(
        '📊 **Status:** No active processing jobs.\n\n' +
        '⏳ This is a scaffold — status tracking coming in Phase 2.'
    );
    return { metadata: { command: 'status' } };
}

async function handleConversation(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken
): Promise<vscode.ChatResult> {
    const messages = [
        vscode.LanguageModelChatMessage.User(
            'You are the MS Learn Video Documenter agent. You help users create ' +
            'Microsoft Learn-style documentation from screen recording videos. ' +
            'You can analyze videos, generate documentation in various MS Learn formats ' +
            '(Quickstart, Tutorial, How-to, Concept, Overview), and refine generated content. ' +
            'Available commands: /analyze, /generate, /refine, /status. ' +
            'Keep responses concise and helpful.'
        ),
        vscode.LanguageModelChatMessage.User(request.prompt),
    ];

    const chatResponse = await request.model.sendRequest(messages, {}, token);

    for await (const fragment of chatResponse.text) {
        stream.markdown(fragment);
    }

    return { metadata: { command: '' } };
}
