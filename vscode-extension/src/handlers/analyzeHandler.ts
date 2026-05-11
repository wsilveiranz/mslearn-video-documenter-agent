import * as vscode from 'vscode';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { detectVideoPath } from '../utils/fileDetection';

export async function handleAnalyze(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager
): Promise<vscode.ChatResult> {
    // 1. Detect video path from prompt
    let videoPath = detectVideoPath(request.prompt);

    // 2. If no path detected, show file picker
    if (!videoPath) {
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
            videoPath = result[0].fsPath;
        }
    }

    // 3. If still no path, show help
    if (!videoPath) {
        stream.markdown(
            '📹 No video file selected. Please provide a path to a video file:\n\n' +
            '```\n@video-documenter /analyze C:\\path\\to\\video.mp4\n```\n\n' +
            'Or right-click a video file in the Explorer and select **"Analyze with Video Documenter"**.'
        );
        return { metadata: { command: 'analyze' } };
    }

    // 4. Check if cancelled
    if (token.isCancellationRequested) {
        return { metadata: { command: 'analyze' } };
    }

    // 5. Check backend health
    try {
        await client.checkHealth();
    } catch {
        stream.markdown(
            '❌ **Backend not running.** Start the backend first:\n\n' +
            '```bash\ncd backend && python -m src.main\n```\n\n' +
            'Then try `/analyze` again.'
        );
        return { metadata: { command: 'analyze' } };
    }

    // 6. Upload video and poll for ingestion completion
    try {
        stateManager.setStage('analyzing');
        stream.progress('Uploading video...');

        // Use path-based ingestion — backend reads the file directly, avoiding HTTP upload overhead.
        // NOTE: This assumes backend shares the local filesystem. For remote backends,
        // use client.ingestVideo() (multipart upload) instead.
        // TODO(Phase 3): Auto-detect remote backend and switch to upload mode.
        const ingestResult = await client.ingestVideoByPath(videoPath);
        const videoId = ingestResult.video_id;

        stateManager.setVideoId(videoId, videoPath);
        stream.progress('Video uploaded, starting analysis...');

        // 7. Connect WebSocket for real-time progress updates (best-effort)
        let lastWsDetail = '';
        const progressDisposable = client.connectProgress(videoId, (msg) => {
            const text = msg.detail || msg.stage;
            if (text !== lastWsDetail) {
                lastWsDetail = text;
                stream.progress(text);
            }
        });

        // 8. Poll until ingestion_complete (step 1 of 6)
        // pollForCompletion waits for status === 'completed', but ingestion only sets
        // current_stage = 'ingestion_complete' with status still 'queued'. Use a custom loop.
        let complete = false;
        const startTime = Date.now();
        const timeoutMs = 300000; // 5 minutes
        let lastPollStage = '';

        while (!complete && Date.now() - startTime < timeoutMs) {
            if (token.isCancellationRequested) {
                progressDisposable.dispose();
                stateManager.setStage('idle');
                return { metadata: { command: 'analyze' } };
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
                    return { metadata: { command: 'analyze' } };
                }
            } catch (pollError) {
                if (pollError instanceof BackendError && pollError.statusCode === 404) {
                    stateManager.setStage('idle');
                    stream.markdown('❌ **Job not found.** The backend may have restarted. Please try `/analyze` again.');
                    progressDisposable.dispose();
                    return { metadata: { command: 'analyze' } };
                }
                // Ignore other transient polling errors
            }
        }

        progressDisposable.dispose();

        if (!complete) {
            stateManager.setStage('idle');
            stream.markdown('⚠️ **Analysis timed out.** Use `/status` to check progress.');
            return { metadata: { command: 'analyze' } };
        }

        // Step 3: Run extraction
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
        const extractTimeoutMs = 600000; // 10 minutes
        let lastExtractPollStage = '';

        while (!extractionComplete && Date.now() - extractStartTime < extractTimeoutMs) {
            if (token.isCancellationRequested) {
                extractProgressDisposable.dispose();
                stateManager.setStage('idle');
                return { metadata: { command: 'analyze' } };
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
                    return { metadata: { command: 'analyze' } };
                }
            } catch (pollError) {
                if (pollError instanceof BackendError && pollError.statusCode === 404) {
                    stateManager.setStage('idle');
                    stream.markdown('❌ **Job not found.** The backend may have restarted. Please try `/analyze` again.');
                    extractProgressDisposable.dispose();
                    return { metadata: { command: 'analyze' } };
                }
            }
        }

        extractProgressDisposable.dispose();

        if (!extractionComplete) {
            stateManager.setStage('idle');
            stream.markdown('⚠️ **Extraction timed out.** Use `/status` to check progress.');
            return { metadata: { command: 'analyze' } };
        }

        // Ingestion + Extraction complete — update state
        stateManager.setStage('analyzed');

        // Fetch extraction summary and quality assessment
        let extractionRows = '';
        let qualityWarning = '';
        try {
            const finalStatus = await client.getVideoStatus(videoId);
            if (finalStatus.extraction_summary) {
                const es = finalStatus.extraction_summary;
                extractionRows = 
                    `| Transcript | ${es.transcript_segments} segment(s) |\n` +
                    `| Scenes | ${es.scenes} detected |\n` +
                    `| Keyframes | ${es.keyframes} captured |\n` +
                    `| Vision analysis | ${es.has_vision_descriptions ? '✓' : '✗ (no descriptions)'} |\n`;
            }

            // Run quality assessment
            try {
                const quality = await client.assessQuality(videoId);
                const confidence = Math.round(quality.grounding_confidence * 100);
                extractionRows += `| Data quality | **${quality.quality_level}** (${confidence}% grounding confidence) |\n`;

                if (quality.quality_level === 'minimal' || quality.quality_level === 'thin') {
                    const warnings = quality.warnings.map(w => `> - ${w}`).join('\n');
                    const recommendations = quality.recommendations.map(r => `> - ${r}`).join('\n');
                    qualityWarning = 
                        `\n⚠️ **Data quality: ${quality.quality_level}** — ` +
                        `The extraction data may be insufficient for fully grounded documentation.\n\n` +
                        (quality.warnings.length > 0 ? `> **Warnings:**\n${warnings}\n\n` : '') +
                        (quality.recommendations.length > 0 ? `> **Recommendations:**\n${recommendations}\n\n` : '');
                } else if (quality.quality_level === 'adequate') {
                    const recommendations = quality.recommendations.map(r => `> - ${r}`).join('\n');
                    qualityWarning = quality.recommendations.length > 0
                        ? `\n💡 **Tips to improve quality:**\n${recommendations}\n\n`
                        : '';
                }
            } catch {
                // Quality assessment failed — non-fatal, continue without it
            }
        } catch {
            // Non-fatal
        }

        stream.markdown(
            `✅ **Video analyzed successfully!**\n\n` +
            `| Field | Value |\n` +
            `|-------|-------|\n` +
            `| Video | \`${videoPath}\` |\n` +
            `| Video ID | \`${videoId}\` |\n` +
            extractionRows +
            `\n` +
            `📝 Ready to generate documentation. Choose a document type:\n\n` +
            '```\n@video-documenter /generate\n```\n\n' +
            'Available types: **Quickstart**, **Tutorial**, **How-to**, **Concept**, **Overview**' +
            qualityWarning
        );

    } catch (error) {
        stateManager.setStage('idle');

        if (error instanceof BackendError) {
            stream.markdown(`❌ **Upload failed:** ${error.detail}`);
        } else {
            stream.markdown(`❌ **Error:** ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    return { metadata: { command: 'analyze' } };
}
