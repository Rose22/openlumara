// =============================================================================
// Markdown Rendering
// =============================================================================

marked.setOptions({
    breaks: true,
    gfm: true
});

function renderMarkdown(text) {
    // handle undefined or null safely
    if (!text) return '';

    // parse markdown
    const rendered = marked.parse(text);

    // and protect against XSS
    const clean = DOMPurify.sanitize(rendered);

    return clean;
}
