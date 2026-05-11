import * as vscode from 'vscode';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager, DocumentMetadata } from '../utils/conversationState';
import { detectVideoPath } from '../utils/fileDetection';
import { DOC_TYPES, DOC_TYPE_PATTERNS, fuzzyMatchDocType } from '../constants/docTypes';
import { AZURE_SERVICE_ITEMS, AzureServiceItem } from '../constants/azureServices';

/**
 * Attempt to detect a doc type from the user's prompt text.
 * Returns the matched value (e.g., 'tutorial') or undefined.
 */
function detectDocType(prompt: string): string | undefined {
    const lower = prompt.toLowerCase().trim();
    for (const dt of DOC_TYPE_PATTERNS) {
        if (dt.patterns.some(p => p.test(lower))) {
            return dt.value;
        }
    }
    return fuzzyMatchDocType(lower);
}

/**
 * Attempt to detect an ms.service slug from the user's prompt text
 * by matching against known service slugs and display names.
 */
function detectService(prompt: string): string | undefined {
    const lower = prompt.toLowerCase();
    // Check service slugs and display names (skip the last "Other" entry)
    for (const item of AZURE_SERVICE_ITEMS) {
        if (!item.value) { continue; } // skip "Other"
        if (lower.includes(item.value)) { return item.value; }
        // Also match display name without the emoji prefix
        const displayLower = item.label.replace(/^[^\w]+/, '').toLowerCase().trim();
        if (displayLower && lower.includes(displayLower)) { return item.value; }
    }
    return undefined;
}

/**
 * Attempt to detect a desired output filename (*.md) from the prompt.
 */
function detectFilename(prompt: string): string | undefined {
    const match = prompt.match(
        /(?:use|save\s+(?:as|to)|file\s*name\s*(?:should\s+be)?|name\s+(?:it|the\s+file))\s+(\S+\.md)\b/i
    ) ?? prompt.match(/\b([\w-]+\.md)\b/i);
    return match ? match[1].replace(/^["']+|["']+$/g, '') : undefined;
}

export async function handlePlan(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager
): Promise<vscode.ChatResult> {
    const promptText = request.prompt;

    // Step 1: Video file
    stream.markdown('📋 **Let\'s plan your documentation!**\n\n');

    let videoPath = detectVideoPath(promptText);

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

    // Step 2: Document type — try to infer from prompt, fall back to picker
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    let docType = detectDocType(promptText);
    if (!docType) {
        const docTypeSelection = await vscode.window.showQuickPick(
            DOC_TYPES.map(dt => ({ label: dt.label, description: dt.description, value: dt.value })),
            { placeHolder: 'What type of MS Learn document should I generate?', title: 'Document Type' }
        );
        if (!docTypeSelection) {
            stream.markdown('📝 Planning cancelled.');
            return { metadata: { command: 'plan' } };
        }
        docType = (docTypeSelection as { value: string }).value;
    }

    // Step 3: Output filename
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    let desiredFilename = detectFilename(promptText);
    if (!desiredFilename) {
        desiredFilename = await vscode.window.showInputBox({
            prompt: 'Output filename for the generated document (e.g., deploy-web-app.md)',
            placeHolder: 'my-article.md',
            title: 'Output Filename',
            validateInput: (value) => {
                if (value && !value.endsWith('.md')) {
                    return 'Filename must end with .md';
                }
                return undefined;
            },
        }) ?? '';
    }

    // Step 4: Author (GitHub ID)
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

    // Step 5: MS Author (Microsoft alias)
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

    // Step 6: MS Service — try to infer from prompt, fall back to picker
    if (token.isCancellationRequested) { return { metadata: { command: 'plan' } }; }

    let msService = detectService(promptText);
    if (!msService) {
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

        msService = (serviceSelection as AzureServiceItem).value;

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
    }

    // Step 7: Customer intent (optional)
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

        let lastWsDetail = '';
        const progressDisposable = client.connectProgress(videoId, (msg) => {
            const text = msg.detail || msg.stage;
            if (text !== lastWsDetail) {
                lastWsDetail = text;
                stream.progress(text);
            }
        });

        let complete = false;
        const startTime = Date.now();
        const timeoutMs = 300000; // 5 minutes
        let lastPollStage = '';

        while (!complete && Date.now() - startTime < timeoutMs) {
            if (token.isCancellationRequested) {
                progressDisposable.dispose();
                stateManager.setStage('idle');
                return { metadata: { command: 'plan' } };
            }

            await new Promise(resolve => setTimeout(resolve, 2000));

            try {
                const status = await client.getVideoStatus(videoId);
                if (status.current_stage !== lastPollStage) {
                    lastPollStage = status.current_stage;
                    stream.progress(`${status.current_stage}`);
                }

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

        // Step 9: Run extraction
        stream.progress('Analyzing video content...');

        try {
            await client.extractVideo(videoId);
        } catch (extractError) {
            if (extractError instanceof BackendError) {
                stream.markdown(`⚠️ **Extraction could not be started:** ${extractError.detail}\n\n`);
            }
        }

        let lastExtractWsDetail = '';
        const extractProgressDisposable = client.connectProgress(videoId, (msg) => {
            const text = msg.detail || msg.stage;
            if (text !== lastExtractWsDetail) {
                lastExtractWsDetail = text;
                stream.progress(text);
            }
        });

        let extractionComplete = false;
        const extractStartTime = Date.now();
        const extractTimeoutMs = 600000; // 10 minutes for extraction (includes transcription + vision)
        let lastExtractPollStage = '';

        while (!extractionComplete && Date.now() - extractStartTime < extractTimeoutMs) {
            if (token.isCancellationRequested) {
                extractProgressDisposable.dispose();
                stateManager.setStage('idle');
                return { metadata: { command: 'plan' } };
            }

            await new Promise(resolve => setTimeout(resolve, 2000));

            try {
                const status = await client.getVideoStatus(videoId);
                if (status.current_stage !== lastExtractPollStage) {
                    lastExtractPollStage = status.current_stage;
                    stream.progress(`${status.current_stage}`);
                }

                if (status.current_stage === 'extraction_complete') {
                    extractionComplete = true;
                } else if (status.status === 'failed') {
                    stateManager.setStage('idle');
                    stream.markdown('❌ **Extraction failed.** Please check the backend logs.');
                    extractProgressDisposable.dispose();
                    return { metadata: { command: 'plan' } };
                }
            } catch (pollError) {
                if (pollError instanceof BackendError && pollError.statusCode === 404) {
                    stateManager.setStage('idle');
                    stream.markdown('❌ **Job not found.** The backend may have restarted. Please try `/plan` again.');
                    extractProgressDisposable.dispose();
                    return { metadata: { command: 'plan' } };
                }
            }
        }

        extractProgressDisposable.dispose();

        if (!extractionComplete) {
            stateManager.setStage('idle');
            stream.markdown('⚠️ **Extraction timed out.** Use `/status` to check progress.');
            return { metadata: { command: 'plan' } };
        }

        // Fetch extraction summary for display
        let extractionInfo = '';
        let finalStatus: Awaited<ReturnType<typeof client.getVideoStatus>> | null = null;
        try {
            finalStatus = await client.getVideoStatus(videoId);
            if (finalStatus.extraction_summary) {
                const es = finalStatus.extraction_summary;
                extractionInfo =
                    `| Transcript | ${es.transcript_segments} segment(s) |\n` +
                    `| Scenes | ${es.scenes} detected |\n` +
                    `| Keyframes | ${es.keyframes} captured |\n` +
                    `| Vision analysis | ${es.has_vision_descriptions ? '✓' : '✗ (no descriptions)'} |\n`;
            }
        } catch {
            // Non-fatal — just skip extraction info in summary
        }

        const thinDataWarning = (finalStatus?.extraction_summary &&
            finalStatus.extraction_summary.transcript_segments === 0 &&
            !finalStatus.extraction_summary.has_vision_descriptions)
            ? '\n\n⚠️ **Limited extraction data:** No transcript was found and vision analysis produced no descriptions. ' +
              'The video may be silent or the vision model may not be available. ' +
              'Consider providing supplementary documentation to improve document quality.\n'
            : '';

        // Step 10: Store state + show summary
        const metadata: DocumentMetadata = {
            author: author || '',
            msAuthor: msAuthor || '',
            msService: msService,
            customerIntent: customerIntent || '',
        };

        stateManager.setMetadata(metadata);
        stateManager.setDocType(docType);
        stateManager.setStage('planned');

        if (desiredFilename) {
            stateManager.setSavedFilename(desiredFilename);
        }

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
            extractionInfo +
            `| Type | ${docType} |\n` +
            `| Filename | ${desiredFilename ? `\`${desiredFilename}\`` : '_(auto-generated)_'} |\n` +
            `| Author | ${author || '_(not set)_'} |\n` +
            `| ms.author | ${msAuthor || '_(not set)_'} |\n` +
            `| ms.service | ${msService || '_(not set)_'} |\n` +
            `| Customer intent | ${customerIntent || '_(not set)_'} |\n` +
            `| Reference docs | ${refDocsInfo} |\n\n` +
            '📝 Use `/generate` to create the document with these settings.\n' + thinDataWarning
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
