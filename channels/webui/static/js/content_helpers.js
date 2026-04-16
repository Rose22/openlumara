// =============================================================================
// Content Helpers
// =============================================================================

/**
 * Extracts plain text from a message content payload.
 * Content can be a string or an array of objects (multimodal).
 */
function extractTextContent(content) {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
        return content
        .map(part => {
            if (part.type === 'text') return part.text;
            if (part.type === 'file') return `File: ${part.filename}`;
            if (part.type === 'image_url') return `[Image]`;
            return '';
        })
        .filter(t => t.trim() !== '')
        .join('\n');
    }
    return '';
}

/**
 * Renders message content into HTML.
 * Handles multimodal arrays (images + text) and standard strings.
 */
function renderContentBody(content) {
    // Handle multi-modal content (images + text)
    if (Array.isArray(content)) {
        return content.map(part => {
            if (part.type === 'text') {
                // Check if this text part is actually a file upload
                // using the pattern "[File: filename]\ncontent"
                const filePattern = /^\[File: (.*?)\]\n([\s\S]*)$/;
                const fileMatch = part.text.match(filePattern);

                if (fileMatch) {
                    const filename = fileMatch[1];
                    // Return ONLY the icon and filename preview
                    return `
                    <div class="file-preview-container">
                    <div class="file-preview">
                    <span class="file-icon">📄</span>
                    <span class="file-name">${escapeHtml(filename)}</span>
                    </div>
                    </div>`;
                }

                return renderMarkdown(part.text);
            } else if (part.type === 'image_url') {
                const url = part.image_url?.url || '';
                if (url.startsWith('data:image') || url.startsWith('http')) {
                    return `
                    <div class="uploaded-image-container">
                    <img src="${escapeHtml(url)}" class="uploaded-image-preview" alt="Uploaded image">
                    </div>`;
                }
                return '';
            }
            return '';
        }).join('');
    }

    // Standard string content
    return renderMarkdown(content || '');
}

// Note: extractSnippet now expects 'content' to be a string because
// filterChats calls extractTextContent before passing it.
function extractSnippet(content, query, maxLength) {
    if (!content) return '';

    // content is now guaranteed to be a string from extractTextContent
    const lowerContent = content.toLowerCase();
    const queryLower = query.toLowerCase();
    const matchIndex = lowerContent.indexOf(queryLower);

    if (matchIndex === -1) return '';

    const contextChars = Math.floor((maxLength - query.length) / 2);
    let start = Math.max(0, matchIndex - contextChars);
    let end = Math.min(content.length, matchIndex + query.length + contextChars);

    // Adjust to not cut words
    if (start > 0) {
        const spaceIndex = content.lastIndexOf(' ', start);
        if (spaceIndex > matchIndex - contextChars - 10) {
            start = spaceIndex + 1;
        }
    }
    if (end < content.length) {
        const spaceIndex = content.indexOf(' ', end);
        if (spaceIndex !== -1 && spaceIndex < end + 10) {
            end = spaceIndex;
        }
    }

    let snippet = content.substring(start, end);

    if (start > 0) snippet = '...' + snippet;
    if (end < content.length) snippet = snippet + '...';

    snippet = escapeHtml(snippet);
    const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
    snippet = snippet.replace(regex, '<mark>$1</mark>');

    return snippet;
}
