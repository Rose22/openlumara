// create a temporary div that gets used to syntax highlight
const _tempHighlightDiv = document.createElement('div');

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
// cache of highlighted code blocks, keyed by language + code content.
// keeps live-streaming re-renders cheap (only the growing block re-highlights).
const _hlCache = new Map();

function renderMarkdown(text, live = false) {
    if (!text) return '';

    // parse the markdown to HTML
    let html = marked.parse(text);

    // protect against XSS
    html = DOMPurify.sanitize(html);

    // syntax highlighting
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
    // per-block highlight cache. during streaming the whole message is
    // re-rendered per paint, which used to re-highlight every code block
    // from scratch - including finished ones. with the cache, only the
    // block that is still growing actually pays for hljs; everything else
    // is a map lookup. (keyed by lang+code, so identical blocks across
    // the whole app share the result too.)
    if (typeof hljs !== 'undefined') {
        _tempHighlightDiv.innerHTML = html;

        const blocks = _tempHighlightDiv.querySelectorAll('pre code');

        blocks.forEach((block, i) => {
            const lang = block.className.replace('language-', '') || undefined;
            const code = block.textContent;
            const key = (lang || 'auto') + '\0' + code;

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
            // during live renders, the LAST code block is the one still being
            // streamed: its content is new every frame, so caching it would
            // retain a full highlighted copy of every intermediate state
            // (= ram climbing during streams). skip the cache for it; its
            // final state gets cached on the final (live=false) render.
            const cacheable = !(live && i === blocks.length - 1);

            let highlighted = cacheable ? _hlCache.get(key) : undefined;
            if (highlighted === undefined) {
                highlighted = (lang && hljs.getLanguage(lang))
                    ? hljs.highlight(code, { language: lang }).value
                    : hljs.highlightAuto(code).value;

                // simple bound so a long session can't grow it forever
                if (_hlCache.size > 400) _hlCache.clear();
                if (cacheable) _hlCache.set(key, highlighted);
            }

            block.innerHTML = highlighted;
            block.classList.add('hljs');
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
function renderMarkdownFor(message, live, raw) {
    if (!message) return '';

    const content = message.content || '';

    if (!live) {
        const cached = _mdCache.get(message);
        if (cached && cached.source === content && Boolean(raw) === Boolean(cached.raw)) return cached.html;
    }

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
    // raw mode: plain escaped text, no markdown pipeline at all.
    // live mode: full pipeline including hljs - affordable now that the
    // per-block cache means only the still-growing block gets highlighted,
    // and the directive throttles live paints to ~8fps.
    const html = raw ? escapeHtml(content) : renderMarkdown(content, Boolean(live));

    if (!live && content) _mdCache.set(message, { source: content, html, raw: Boolean(raw) });

    return html;
}
