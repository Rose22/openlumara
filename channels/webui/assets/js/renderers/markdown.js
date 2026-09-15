// create a temporary div that gets used to syntax highlight
const _tempHighlightDiv = document.createElement('div');

function renderMarkdown(text) {
    if (!text) return '';

    // parse the markdown to HTML
    let html = marked.parse(text);

    // protect against XSS
    html = DOMPurify.sanitize(html);

    // syntax highlighting
    if (typeof hljs !== 'undefined') {
        _tempHighlightDiv.innerHTML = html;

        _tempHighlightDiv.querySelectorAll('pre code').forEach((block) => {
            const lang = block.className.replace('language-', '') || undefined;
            hljs.highlightElement(block);
        });

        html = _tempHighlightDiv.innerHTML;
    }

    // add the copy button to all pre statements.
    // this used to inject an `x-copy-code` alpine directive, but that forced
    // alpine to walk and re-initialize the entire rendered subtree on every
    // update. it's plain markup now, handled by a single delegated listener
    // (see directives/markdown.js)
    html = html.replace(/<pre><code/g, '<pre><button class="copy-btn" type="button">Copy</button><code');

    return html;
}

// cache of rendered markdown, keyed by the message object itself.
// only messages that are no longer the live one at the end of a streaming
// turn ever get cached, since their content can't change anymore.
const _mdCache = new WeakMap();

/*
 * renderMarkdown, but smart about when it actually does the work.
 *
 * `live` == this message is the one currently being streamed into, so its
 * content grows with every token and genuinely has to be re-rendered
 * (syntax highlighting included, so code highlights as it streams in).
 *
 * once a message is no longer the last one in its turn, its content is final,
 * so it gets rendered exactly once and served from cache after that.
 */
function renderMarkdownFor(message, live) {
    if (!message) return '';

    const content = message.content || '';

    if (!live) {
        const cached = _mdCache.get(message);
        if (cached && cached.source === content) return cached.html;
    }

    const html = renderMarkdown(content);

    if (!live && content) _mdCache.set(message, { source: content, html });

    return html;
}
