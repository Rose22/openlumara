// =============================================================================
// Export
// =============================================================================

function showExportModal() {
    toggleModal('export');
}

async function exportChat(format) {
    try {
        // Fetch chat title for filename
        let chatTitle = 'chat-export';
        try {
            const chatId = await getCurrentChatId();
            if (chatId) {
                const chatResponse = await fetch(`/chat/load?id=${chatId}`);
                const chatData = await chatResponse.json();
                if (chatData.success && chatData.chat && chatData.chat.title) {
                    chatTitle = chatData.chat.title;
                }
            }
        } catch (e) {
            console.error('Failed to get chat title for export:', e);
        }
        
        // Sanitize title for filename
        const safeTitle = (chatTitle || 'chat-export').replace(/[\/\\:*?"<>|]/g, '_');

        const response = await fetch('/messages');
        const data = await response.json();
        const messages = data.messages || [];

        // Group messages into turns to respect the new message format
        const turns = [];
        let i = 0;
        while (i < messages.length) {
            const msg = messages[i];
            if (msg.role === 'assistant') {
                // Collect assistant turn
                const collected = [];
                let j = i;
                while (j < messages.length) {
                    const current = messages[j];
                    if (current.role === 'assistant') {
                        // Check if it's an announcement or command output (separate from turn)
                        const parsed = parseMessageContent(current.content || '');
                        if (parsed.isAnnouncement || parsed.isCommandOutput) {
                            break;
                        }
                        collected.push(current);
                        j++;
                        // If tool calls, collect tool responses
                        if (current.tool_calls && current.tool_calls.length > 0) {
                            while (j < messages.length && messages[j].role === 'tool') {
                                collected.push(messages[j]);
                                j++;
                            }
                        }
                    } else if (current.role === 'tool') {
                        // Orphaned tool at start
                        collected.push(current);
                        j++;
                    } else {
                        break;
                    }
                }
                turns.push({ type: 'assistant', messages: collected });
                i = j;
            } else {
                // User or other single message
                turns.push({ type: 'single', messages: [msg] });
                i++;
            }
        }

        // Helper to format tool responses human-readably
        function formatToolResponse(m) {
            const toolName = m.name || m.tool_name || 'Tool';
            const respContent = m.content || m.result;
            let formatted = `> **${toolName}**\n\n`;

            if (respContent === null || respContent === undefined) {
                formatted += '*No response content*\n\n';
            } else if (typeof respContent === 'string') {
                let parsed;
                try { parsed = JSON.parse(respContent); } catch(e) { parsed = null; }

                if (parsed !== null) {
                    formatted += '```json\n' + JSON.stringify(parsed, null, 2).replace(/\\n/g, '\n') + '\n```\n\n';
                } else {
                    formatted += respContent + '\n\n';
                }
            } else if (typeof respContent === 'object') {
                formatted += '```json\n' + JSON.stringify(respContent, null, 2).replace(/\\n/g, '\n') + '\n```\n\n';
            } else {
                formatted += String(respContent) + '\n\n';
            }
            return formatted;
        }

        let content, filename, mimeType;

        if (format === 'json') {
            content = JSON.stringify(messages, null, 2);
            filename = `${safeTitle}.json`;
            mimeType = 'application/json';
        } else if (format === 'markdown') {
            let md = '# Chat Export\n\n';
            md += 'Exported on ' + new Date().toLocaleString() + '\n\n---\n\n';

            turns.forEach(turn => {
                if (turn.type === 'assistant') {
                    md += '**AI Response**\n\n';
                    turn.messages.forEach(m => {
                        if (m.role === 'assistant') {
                            if (m.reasoning_content) {
                                md += '*Reasoning*\n\n' + m.reasoning_content + '\n\n';
                            }
                            if (m.content) {
                                md += m.content + '\n';
                            }
                        } else if (m.role === 'tool') {
                            md += formatToolResponse(m);
                        }
                    });
                    md += '---\n\n';
                } else {
                    const m = turn.messages[0];
                    const role = getRoleDisplay(m.role, m.content);
                    md += '**' + role + '**:\n\n' + (m.content || '') + '\n\n---\n\n';
                }
            });

            content = md;
            filename = `${safeTitle}.md`;
            mimeType = 'text/markdown';
        } else {
            let txt = 'Chat Export\n';
            txt += 'Exported on ' + new Date().toLocaleString() + '\n';
            txt += '================================\n\n';

            turns.forEach(turn => {
                if (turn.type === 'assistant') {
                    txt += '[AI Response]:\n';
                    turn.messages.forEach(m => {
                        if (m.role === 'assistant') {
                            if (m.reasoning_content) {
                                txt += '[Reasoning]:\n' + m.reasoning_content + '\n\n';
                            }
                            if (m.content) {
                                txt += m.content + '\n';
                            }
                        } else if (m.role === 'tool') {
                            const toolName = m.name || m.tool_name || 'Tool';
                            const respContent = m.content || m.result;
                            txt += `[${toolName}]:\n`;
                            if (respContent === null || respContent === undefined) {
                                txt += '*No response content*\n\n';
                            } else if (typeof respContent === 'string') {
                                let parsed;
                                try { parsed = JSON.parse(respContent); } catch(e) { parsed = null; }
                                if (parsed !== null) {
                                    txt += JSON.stringify(parsed, null, 2).replace(/\\n/g, '\n') + '\n\n';
                                } else {
                                    txt += respContent + '\n\n';
                                }
                            } else if (typeof respContent === 'object') {
                                txt += JSON.stringify(respContent, null, 2).replace(/\\n/g, '\n') + '\n\n';
                            } else {
                                txt += String(respContent) + '\n\n';
                            }
                        }
                    });
                    txt += '\n';
                } else {
                    const m = turn.messages[0];
                    const role = getRoleDisplay(m.role, m.content);
                    txt += '[' + role + ']:\n' + (m.content || '') + '\n\n';
                }
            });

            content = txt;
            filename = `${safeTitle}.txt`;
            mimeType = 'text/plain';
        }

        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        toggleModal('export');
    } catch (err) {
        console.error('Export failed:', err);
    }
}
