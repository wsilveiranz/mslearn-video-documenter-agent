import * as vscode from 'vscode';
import { BackendClient, BackendError } from '../api/backendClient';
import { ConversationStateManager } from '../utils/conversationState';
import { OutputManager, sanitizeFilename } from '../utils/outputManager';
import { DOC_TYPES, DOC_TYPE_PATTERNS, fuzzyMatchDocType } from '../constants/docTypes';

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
    if (!state.currentVideoId || (state.currentStage !== 'analyzed' && state.currentStage !== 'generated')) {
        stream.markdown(
            '📝 No analyzed video found. Please analyze a video first:\n\n' +
            '```\n@video-documenter /analyze C:\\path\\to\\video.mp4\n```'
        );
        return { metadata: { command: 'generate' } };
    }

    // 2. Determine doc type — check if specified in prompt, otherwise show QuickPick
    let docType: string | undefined;
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

    // 3. Extract supplementary context from prompt (everything that isn't the doc type keyword)
    let supplementaryContext = request.prompt.trim();
    // Remove the doc type keyword if present
    for (const dt of DOC_TYPE_PATTERNS) {
        for (const pattern of dt.patterns) {
            supplementaryContext = supplementaryContext.replace(new RegExp(pattern.source, 'gi'), '').trim();
        }
    }

    // 4. Extract desired filename from prompt (e.g., "use foo.md as the file name")
    let desiredFilename: string | undefined;
    const filenameMatch = supplementaryContext.match(
        /(?:use|save\s+(?:as|to)|file\s*name\s*(?:should\s+be)?|name\s+(?:it|the\s+file))\s+(\S+\.md)\b/i
    ) ?? supplementaryContext.match(/\b([\w-]+\.md)\b/i);
    if (filenameMatch) {
        desiredFilename = filenameMatch[1].replace(/^["']+|["']+$/g, '');
    }

    // 4. Check cancellation
    if (token.isCancellationRequested) {
        return { metadata: { command: 'generate' } };
    }

    // 5. Trigger generation
    try {
        stateManager.setStage('generating');
        stateManager.setDocType(docType);

        stream.progress(`Generating ${docType} document...`);

        // Trigger the pipeline
        await client.generateDocument(state.currentVideoId, docType, supplementaryContext);

        // 6. Connect WebSocket for progress
        const progressDisposable = client.connectProgress(state.currentVideoId, (msg) => {
            stream.progress(msg.detail || `Step ${msg.step}/${msg.total_steps}: ${msg.stage}`);
        });

        // 7. Poll for completion (no progress display — WebSocket handles that)
        let documentId: string | undefined;
        const startTime = Date.now();
        const timeoutMs = 600000; // 10 minutes for full pipeline

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

        // 10. Save to workspace and open
        // TODO(Phase 3): Pass media files from extraction results once the
        // /documents/{id} response includes referenced image paths.
        try {
            const savedUri = await outputManager.saveAndOpen(
                documentId,
                doc.markdown_content,
                [],
                desiredFilename,
            );
            stateManager.setSavedFilename(desiredFilename ? sanitizeFilename(desiredFilename) : `${documentId}.md`);
            stream.markdown(
                `✅ **${docType.charAt(0).toUpperCase() + docType.slice(1)} document generated!**\n\n` +
                `| Field | Value |\n` +
                `|-------|-------|\n` +
                `| Document ID | \`${documentId}\` |\n` +
                `| Type | ${docType} |\n` +
                `| Word count | ${doc.word_count} |\n` +
                `| Revision | ${doc.revision_number} |\n` +
                `| Saved to | \`${savedUri.fsPath}\` |\n\n` +
                '💡 **Next steps:**\n' +
                '- Use `/refine` to improve specific sections\n' +
                '- Or just type your feedback directly — I\'ll treat it as a refinement request\n'
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
