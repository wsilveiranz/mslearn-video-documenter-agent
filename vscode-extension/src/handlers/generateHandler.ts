import * as vscode from 'vscode';
import * as path from 'path';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager, MediaFile, sanitizeFilename } from '../utils/outputManager';
import { extractChatReferences } from '../utils/chatReferences';
import { DOC_TYPES, DOC_TYPE_PATTERNS, fuzzyMatchDocType } from '../constants/docTypes';
import { BackendMetadata } from '../api/backendClient';
import { getProgressUpdateIntervalMs } from '../utils/config';
import { formatElapsed } from '../utils/progress';

export async function handleGenerate(
    request: vscode.ChatRequest,
    stream: vscode.ChatResponseStream,
    token: vscode.CancellationToken,
    client: BackendClient,
    stateManager: ConversationStateManager,
    outputManager: OutputManager
): Promise<vscode.ChatResult> {
    const state = stateManager.getState();

    // 1. Check that a video has been analyzed
    if (!state.currentVideoId || (state.currentStage !== 'analyzed' && state.currentStage !== 'generated' && state.currentStage !== 'planned')) {
        stream.markdown(
            '📝 No analyzed video found. Please analyze a video first:\n\n' +
            '```\n@video-documenter /analyze C:\\path\\to\\video.mp4\n```'
        );
        return { metadata: { command: 'generate' } };
    }

    // 2. Determine doc type — use pre-selected type from /plan, or detect/prompt
    let docType: string | undefined;

    if (state.currentStage === 'planned' && state.lastDocType) {
        // Coming from /plan — use the already-selected doc type, skip picker
        docType = state.lastDocType;
    } else {
        const promptLower = request.prompt.toLowerCase().trim();

        // Try to detect doc type from prompt text (flexible matching)
        for (const dt of DOC_TYPE_PATTERNS) {
            if (dt.patterns.some(p => p.test(promptLower))) {
                docType = dt.value;
                break;
            }
        }

        if (!docType) {
            docType = fuzzyMatchDocType(promptLower);
        }

        if (!docType) {
            // Show QuickPick for doc type selection
            const selection = await vscode.window.showQuickPick(
                DOC_TYPES.map(dt => ({
                    label: dt.label,
                    description: dt.description,
                    value: dt.value,
                })),
                {
                    placeHolder: 'What type of MS Learn document should I generate?',
                    title: 'Document Type',
                }
            );

            if (!selection) {
                stream.markdown('📝 Document generation cancelled. Use `/generate` to try again.');
                return { metadata: { command: 'generate' } };
            }

            docType = (selection as { label: string; description: string; value: string }).value;
        }
    }

    // 3. Extract supplementary context from prompt (everything that isn't the doc type keyword)
    let supplementaryContext = request.prompt.trim();
    // Remove the doc type keyword if present
    for (const dt of DOC_TYPE_PATTERNS) {
        for (const pattern of dt.patterns) {
            supplementaryContext = supplementaryContext.replace(new RegExp(pattern.source, 'gi'), '').trim();
        }
    }

    // 4. Extract desired filename — prefer /plan's saved filename if coming from planned state
    let desiredFilename: string | undefined;
    if (state.currentStage === 'planned' && state.savedFilename) {
        desiredFilename = state.savedFilename;
    } else {
        const filenameMatch = supplementaryContext.match(
            /(?:use|save\s+(?:as|to)|file\s*name\s*(?:should\s+be)?|name\s+(?:it|the\s+file))\s+(\S+\.md)\b/i
        ) ?? supplementaryContext.match(/\b([\w-]+\.md)\b/i);
        if (filenameMatch) {
            desiredFilename = filenameMatch[1].replace(/^["']+|["']+$/g, '');
        }
    }

    // 4. Check cancellation
    if (token.isCancellationRequested) {
        return { metadata: { command: 'generate' } };
    }

    // Capture the user's selected model to forward to the backend pipeline
    const selectedModel = request.model?.id;

    // 5. Trigger generation
    try {
        stateManager.setStage('generating');
        stateManager.setDocType(docType);

        stream.progress(`Generating ${docType} document...`);

        // Extract reference files from chat context (in addition to /plan state refs)
        const chatRefFiles = await extractChatReferences(request.references ?? [], client, stream);

        // Build metadata for the backend from plan state
        const backendMetadata: BackendMetadata | undefined = state.metadata ? {
            author: state.metadata.author,
            ms_author: state.metadata.msAuthor,
            ms_service: state.metadata.msService,
            customer_intent: state.metadata.customerIntent,
        } : undefined;

        // Load supplementary context from stored references on-demand
        const MAX_REF_FILE_BYTES = 100 * 1024;  // 100 KB per file
        const MAX_TOTAL_REF_BYTES = 500 * 1024; // 500 KB total
        // Extensions that need backend conversion (binary formats)
        const CONVERT_EXTENSIONS = new Set(['.docx', '.pdf', '.pptx', '.xlsx', '.html', '.csv', '.xml']);
        let refContext = '';
        const docRefs = stateManager.getSupplementaryDocRefs();
        if (docRefs.length > 0) {
            const contents: string[] = [];
            let totalBytes = 0;
            let totalCapReached = false;
            for (const refPath of docRefs) {
                try {
                    const basename = path.basename(refPath);
                    const ext = path.extname(refPath).toLowerCase();
                    let text: string;

                    if (CONVERT_EXTENSIONS.has(ext)) {
                        // Binary format — convert via backend MarkItDown service
                        stream.progress(`Converting reference doc: ${basename}...`);
                        const result = await client.convertDocument(refPath);
                        if ('error' in result) {
                            stream.progress(`⚠️ Could not convert ${basename}: ${result.error}`);
                            continue;
                        }
                        if (!result.markdown) {
                            stream.progress(`⚠️ Could not convert ${basename}: empty content returned`);
                            continue;
                        }
                        text = result.markdown;
                    } else {
                        // Plain text format — read directly
                        const uri = vscode.Uri.file(refPath);
                        const bytes = await vscode.workspace.fs.readFile(uri);
                        text = Buffer.from(bytes).toString('utf-8');
                    }

                    if (text.length > MAX_REF_FILE_BYTES) {
                        text = text.slice(0, MAX_REF_FILE_BYTES) + '\n[… truncated — file exceeds 100 KB limit]';
                        stream.progress(`Ref doc truncated (exceeds 100 KB): ${basename}`);
                    }
                    totalBytes += text.length;
                    contents.push(`--- ${basename} ---\n${text}`);
                    if (totalBytes >= MAX_TOTAL_REF_BYTES) {
                        contents.push('\n[… remaining ref docs skipped — total exceeds 500 KB limit]');
                        stream.progress('Some ref docs skipped — total ref doc size exceeds 500 KB limit.');
                        totalCapReached = true;
                        break;
                    }
                } catch {
                    // Skip files that can't be read (may have been moved/deleted)
                }
            }
            refContext = contents.join('\n\n');
        }

        // Also include chat-attached references
        if (chatRefFiles.length > 0) {
            const chatRefContents = chatRefFiles.map(rf => `--- ${rf.filename} ---\n${rf.content}`);
            const chatRefText = chatRefContents.join('\n\n');
            refContext = refContext ? `${refContext}\n\n${chatRefText}` : chatRefText;
        }

        const fullContext = [supplementaryContext, refContext].filter(Boolean).join('\n\n');

        // Trigger the pipeline
        await client.generateDocument(state.currentVideoId, docType, fullContext, backendMetadata, selectedModel);

        // 6. Connect WebSocket for progress
        let lastGenWsDetail = '';
        let lastGenProgressTime = 0;
        const progressIntervalMs = getProgressUpdateIntervalMs();
        const genStartTime = Date.now();
        const progressDisposable = client.connectProgress(state.currentVideoId, (msg) => {
            const text = msg.detail || `Step ${msg.step}/${msg.total_steps}: ${msg.stage}`;
            const now = Date.now();
            if (text !== lastGenWsDetail && now - lastGenProgressTime >= progressIntervalMs) {
                lastGenWsDetail = text;
                lastGenProgressTime = now;
                stream.progress(`${text} (${formatElapsed(genStartTime)})`);
            }
        });

        // 7. Poll for completion with elapsed-time heartbeat
        let documentId: string | undefined;
        const startTime = Date.now();
        const timeoutMs = 1800000; // 30 minutes — backend controls actual pipeline timeout
        let lastHeartbeatTime = Date.now();

        try {
            while (Date.now() - startTime < timeoutMs) {
                if (token.isCancellationRequested) {
                    break;
                }

                await new Promise(resolve => setTimeout(resolve, 3000));

                try {
                    const status = await client.getVideoStatus(state.currentVideoId);

                    if (status.status === 'completed' && status.document_id) {
                        documentId = status.document_id;
                        break;
                    } else if (status.status === 'failed') {
                        stateManager.setStage('analyzed');
                        stream.markdown('❌ **Document generation failed.** Please check the backend logs and try again.');
                        return { metadata: { command: 'generate' } };
                    }

                    // Heartbeat: if no WS message recently, show elapsed time
                    const now = Date.now();
                    if ((now - lastGenProgressTime) >= progressIntervalMs && (now - lastHeartbeatTime) >= progressIntervalMs) {
                        lastHeartbeatTime = now;
                        const detail = status.progress_detail || status.current_stage;
                        stream.progress(`${detail} (${formatElapsed(genStartTime)})`);
                    }
                } catch (pollError) {
                    if (pollError instanceof BackendError && pollError.statusCode === 404) {
                        stateManager.setStage('analyzed');
                        stream.markdown('❌ **Job not found.** The backend may have restarted. Please try `/analyze` again.');
                        return { metadata: { command: 'generate' } };
                    }
                    // Ignore other transient polling errors
                }
            }
        } finally {
            progressDisposable.dispose();
        }

        if (!documentId) {
            stateManager.setStage('analyzed');
            stream.markdown('⚠️ **Generation timed out.** Use `/status` to check progress.');
            return { metadata: { command: 'generate' } };
        }

        // 8. Fetch the generated document
        stream.progress('Fetching generated document...');
        const doc = await client.getDocument(documentId);

        // 9. Update state
        stateManager.setDocumentId(documentId);
        stateManager.setStage('generated');

        // 10. Save to workspace and open (with extracted screenshots)
        const mediaFiles: MediaFile[] = [];
        for (const mf of doc.media_files ?? []) {
            try {
                const data = await client.downloadMedia(documentId, mf.filename);
                mediaFiles.push({ filename: mf.filename, data, outputPath: mf.output_path });
            } catch {
                // Non-fatal: skip media that can't be downloaded
            }
        }
        try {
            const savedUri = await outputManager.saveAndOpen(
                documentId,
                doc.markdown_content,
                mediaFiles,
                desiredFilename,
            );
            stateManager.setSavedFilename(desiredFilename ? sanitizeFilename(desiredFilename) : `${documentId}.md`);

            // Build eval score row if available
            let evalRow = '';
            if (doc.eval_scores) {
                const s = doc.eval_scores;
                const pct = (v: number) => `${Math.round(v * 100)}%`;
                const icon = s.passed ? '✅' : '⚠️';
                evalRow =
                    `| Quality score | ${icon} **${pct(s.overall)}** overall |\n` +
                    `| | Completeness ${pct(s.completeness)} · Accuracy ${pct(s.accuracy)} · Style ${pct(s.style_compliance)} · Readability ${pct(s.readability)} · Grounding ${pct(s.grounding)} |\n`;
            }

            stream.markdown(
                `✅ **${docType.charAt(0).toUpperCase() + docType.slice(1)} document generated!**\n\n` +
                `| Field | Value |\n` +
                `|-------|-------|\n` +
                `| Document ID | \`${documentId}\` |\n` +
                `| Type | ${docType} |\n` +
                `| Word count | ${doc.word_count} |\n` +
                `| Revision | ${doc.revision_number} |\n` +
                `| Saved to | \`${savedUri.fsPath}\` |\n` +
                evalRow + '\n' +
                '💡 **Next steps:**\n' +
                '- Use `/polish` to run MS Learn style checks (writing style, metadata, formatting)\n' +
                '- Use `/edit` to make specific content changes\n' +
                '- For deeper Markdown, metadata, and SEO checks, use **Content Mentor** (`@content-mentor`) directly\n' +
                '- Or just type your feedback directly — I\'ll treat it as an edit request\n'
            );
        } catch (saveError) {
            // Document generated but save/preview failed — show content in chat as fallback
            stream.markdown(
                `✅ **Document generated** but could not save to workspace: ${saveError instanceof Error ? saveError.message : String(saveError)}\n\n` +
                '---\n\n' +
                '**Preview:**\n\n' +
                doc.markdown_content.substring(0, 3000) +
                (doc.markdown_content.length > 3000 ? '\n\n*... (truncated)*' : '') +
                '\n\n---\n\n' +
                '💡 Use `/save` to save the document manually.\n'
            );
        }

    } catch (error) {
        stateManager.setStage('analyzed');

        if (error instanceof BackendError) {
            stream.markdown(`❌ **Generation failed:** ${error.detail}`);
        } else {
            stream.markdown(`❌ **Error:** ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    return { metadata: { command: 'generate' } };
}
