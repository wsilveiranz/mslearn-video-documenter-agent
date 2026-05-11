import * as vscode from 'vscode';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager, DocumentMetadata } from '../utils/conversationState';
import { detectVideoPath } from '../utils/fileDetection';
import { DOC_TYPES } from '../constants/docTypes';
import { AZURE_SERVICE_ITEMS, AzureServiceItem } from '../constants/azureServices';

export async function handlePlan(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager
): Promise<vscode.ChatResult> {
    // Step 1: Video file
    stream.markdown('📋 **Let\'s plan your documentation!**\n\n');

    let videoPath = detectVideoPath(request.prompt);

    if (!videoPath) {
        const result = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            filters: { 'Video Files': ['mp4', 'avi', 'mov', 'mkv', 'webm'] },
            title: 'Select a video file to analyze',
        });
        if (result && result.length > 0) {
            videoPath = result[0].fsPath;
        }
    }

    if (!videoPath) {
        stream.markdown('📹 No video file selected. Please provide a path:\n\n```\n@video-documenter /plan C:\\path\\to\\video.mp4\n```');
        return { metadata: { command: 'plan' } };
    }

    // Step 2: Document type
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    const docTypeSelection = await vscode.window.showQuickPick(
        DOC_TYPES.map(dt => ({ label: dt.label, description: dt.description, value: dt.value })),
        { placeHolder: 'What type of MS Learn document should I generate?', title: 'Document Type' }
    );
    if (!docTypeSelection) {
        stream.markdown('📝 Planning cancelled.');
        return { metadata: { command: 'plan' } };
    }
    const docType = (docTypeSelection as { value: string }).value;

    // Step 3: Author (GitHub ID)
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    const config = vscode.workspace.getConfiguration('video-documenter');
    const defaultAuthor = config.get<string>('author', '');

    const author = await vscode.window.showInputBox({
        prompt: 'GitHub username that will appear as the article author in the byline',
        placeHolder: 'e.g., octocat',
        value: defaultAuthor,
        title: 'Document Author (author)',
    });
    if (author === undefined) {
        stream.markdown('📝 Planning cancelled.');
        return { metadata: { command: 'plan' } };
    }

    // Step 4: MS Author (Microsoft alias)
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    const defaultMsAuthor = config.get<string>('msAuthor', '');

    const msAuthor = await vscode.window.showInputBox({
        prompt: 'Microsoft alias (without @microsoft.com) — used for internal content tracking and review notifications',
        placeHolder: 'e.g., wsilveira',
        value: defaultMsAuthor,
        title: 'Microsoft Alias (ms.author)',
    });
    if (msAuthor === undefined) {
        stream.markdown('📝 Planning cancelled.');
        return { metadata: { command: 'plan' } };
    }

    // Step 5: MS Service (from list)
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    const serviceSelection = await vscode.window.showQuickPick(AZURE_SERVICE_ITEMS, {
        placeHolder: 'Which Azure service does this document cover?',
        title: 'Azure Service (ms.service)',
        matchOnDescription: true,
        matchOnDetail: true,
    });
    if (!serviceSelection) {
        stream.markdown('📝 Planning cancelled.');
        return { metadata: { command: 'plan' } };
    }

    let msService = (serviceSelection as AzureServiceItem).value;

    if (!msService) {
        const customService = await vscode.window.showInputBox({
            prompt: 'Enter a custom ms.service slug (e.g., azure-my-service)',
            placeHolder: 'azure-service-name',
            title: 'Custom Service Slug',
        });
        if (customService === undefined) {
            stream.markdown('📝 Planning cancelled.');
            return { metadata: { command: 'plan' } };
        }
        msService = customService;
    }

    // Step 6: Customer intent (optional)
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    const customerIntent = await vscode.window.showInputBox({
        prompt: '(Optional) Describe the customer intent — helps focus the document. Press Enter to skip.',
        placeHolder: 'As a <role>, I want <what> so that <why>',
        title: 'Customer Intent',
    }) ?? '';

    // Step 7: Supplementary docs (optional)
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    let supplementaryContext = '';
    const addDocs = await vscode.window.showQuickPick(
        [
            { label: '📎 Yes, select reference files', value: 'yes' },
            { label: '⏭️ No, skip', value: 'no' },
        ],
        { placeHolder: 'Do you have reference documentation to improve accuracy?', title: 'Supplementary Documentation' }
    );

    if (addDocs && (addDocs as { value: string }).value === 'yes') {
        const docFiles = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: true,
            filters: { 'Documentation': ['md', 'txt', 'json', 'yaml', 'yml', 'rst'] },
            title: 'Select reference documentation files',
        });
        if (docFiles && docFiles.length > 0) {
            const contents: string[] = [];
            for (const uri of docFiles) {
                try {
                    const bytes = await vscode.workspace.fs.readFile(uri);
                    const text = Buffer.from(bytes).toString('utf-8');
                    contents.push(`--- ${uri.fsPath} ---\n${text}`);
                } catch {
                    // Skip files that can't be read
                }
            }
            supplementaryContext = contents.join('\n\n');
        }
    }

    // Step 8: Check backend health + run analysis
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    try {
        await client.checkHealth();
    } catch {
        stream.markdown(
            '❌ **Backend not running.** Start the backend first:\n\n' +
            '```bash\ncd backend && python -m src.main\n```\n\nThen try `/plan` again.'
        );
        return { metadata: { command: 'plan' } };
    }

    try {
        stateManager.setStage('analyzing');
        stream.progress('Uploading video...');

        const ingestResult = await client.ingestVideoByPath(videoPath);
        const videoId = ingestResult.video_id;

        stateManager.setVideoId(videoId, videoPath);
        stream.progress('Video uploaded, starting analysis...');

        const progressDisposable = client.connectProgress(videoId, (msg) => {
            stream.progress(msg.detail || msg.stage);
        });

        let complete = false;
        const startTime = Date.now();
        const timeoutMs = 300000; // 5 minutes

        while (!complete && Date.now() - startTime < timeoutMs) {
            if (token.isCancellationRequested) {
                progressDisposable.dispose();
                stateManager.setStage('idle');
                return { metadata: { command: 'plan' } };
            }

            await new Promise(resolve => setTimeout(resolve, 2000));

            try {
                const status = await client.getVideoStatus(videoId);
                stream.progress(`${status.current_stage}`);

                if (status.current_stage === 'ingestion_complete') {
                    complete = true;
                } else if (status.status === 'failed') {
                    stateManager.setStage('idle');
                    stream.markdown('❌ **Analysis failed.** Please check the backend logs.');
                    progressDisposable.dispose();
                    return { metadata: { command: 'plan' } };
                }
            } catch (pollError) {
                if (pollError instanceof BackendError && pollError.statusCode === 404) {
                    stateManager.setStage('idle');
                    stream.markdown('❌ **Job not found.** The backend may have restarted. Please try `/plan` again.');
                    progressDisposable.dispose();
                    return { metadata: { command: 'plan' } };
                }
                // Ignore other transient polling errors
            }
        }

        progressDisposable.dispose();

        if (!complete) {
            stateManager.setStage('idle');
            stream.markdown('⚠️ **Analysis timed out.** Use `/status` to check progress.');
            return { metadata: { command: 'plan' } };
        }

        // Step 9: Store state + show summary
        const metadata: DocumentMetadata = {
            author: author || '',
            msAuthor: msAuthor || '',
            msService: msService,
            customerIntent: customerIntent || '',
        };

        stateManager.setMetadata(metadata);
        stateManager.setDocType(docType);
        stateManager.setStage('planned');

        if (supplementaryContext) {
            stateManager.setSupplementaryContext(supplementaryContext);
        }

        const refDocsInfo = supplementaryContext ? `${supplementaryContext.split('---').length - 1} file(s) attached` : 'None';

        stream.markdown(
            `✅ **Plan complete! Ready to generate documentation.**\n\n` +
            `| Field | Value |\n` +
            `|-------|-------|\n` +
            `| Video | \`${videoPath}\` |\n` +
            `| Video ID | \`${videoId}\` |\n` +
            `| Type | ${docType} |\n` +
            `| Author | ${author || '_(not set)_'} |\n` +
            `| ms.author | ${msAuthor || '_(not set)_'} |\n` +
            `| ms.service | ${msService || '_(not set)_'} |\n` +
            `| Customer intent | ${customerIntent || '_(not set)_'} |\n` +
            `| Reference docs | ${refDocsInfo} |\n\n` +
            '📝 Use `/generate` to create the document with these settings.\n'
        );

    } catch (error) {
        stateManager.setStage('idle');
        if (error instanceof BackendError) {
            stream.markdown(`❌ **Upload failed:** ${error.detail}`);
        } else {
            stream.markdown(`❌ **Error:** ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    return { metadata: { command: 'plan' } };
}
