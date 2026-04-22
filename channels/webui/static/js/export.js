// =============================================================================
// Export
// =============================================================================

function showExportModal() {
    toggleModal('export');
}

async function exportChat(format) {
    try {
        const response = await fetch('/messages');
        const data = await response.json();
        const messages = data.messages || [];

        let content, filename, mimeType;

        if (format === 'json') {
            content = JSON.stringify(messages, null, 2);
            filename = 'chat-export.json';
            mimeType = 'application/json';
        } else if (format === 'markdown') {
            let md = '# Chat Export\n\n';
            md += 'Exported on ' + new Date().toLocaleString() + '\n\n---\n\n';

            messages.forEach(msg => {
                const role = getRoleDisplay(msg.role);
                md += '**' + role + '**:\n\n' + (msg.content || '') + '\n\n---\n\n';
            });

            content = md;
            filename = 'chat-export.md';
            mimeType = 'text/markdown';
        } else {
            let txt = 'Chat Export\n';
            txt += 'Exported on ' + new Date().toLocaleString() + '\n';
            txt += '================================\n\n';

            messages.forEach(msg => {
                const role = getRoleDisplay(msg.role);
                txt += '[' + role + ']:\n' + (msg.content || '') + '\n\n';
            });

            content = txt;
            filename = 'chat-export.txt';
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
