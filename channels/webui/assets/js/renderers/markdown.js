// create a temporary div that gets used to syntax highlight
const _tempHighlightDiv = document.createElement('div');

const _hlCache = new Map();
let _hlCacheBytes = 0;
const _HL_CACHE_MAX_BYTES = 8 * 1024 * 1024;

function _hlCacheEntrySize(key, value) {
    return key.length + String(value || '').length;
}

function _hlCacheGet(key) {
    if (!_hlCache.has(key)) return undefined;
    const value = _hlCache.get(key);
    _hlCache.delete(key);
    _hlCache.set(key, value);
    return value;
}

function _hlCacheSet(key, value) {
    if (_hlCache.has(key)) {
        _hlCacheBytes -= _hlCacheEntrySize(key, _hlCache.get(key));
        _hlCache.delete(key);
    }

    const size = _hlCacheEntrySize(key, value);
    if (size > _HL_CACHE_MAX_BYTES) return;

    while (_hlCache.size > 0 && _hlCacheBytes + size > _HL_CACHE_MAX_BYTES) {
        const oldestKey = _hlCache.keys().next().value;
        const oldest = _hlCache.get(oldestKey);
        _hlCacheBytes -= _hlCacheEntrySize(oldestKey, oldest);
        _hlCache.delete(oldestKey);
    }

    _hlCache.set(key, value);
    _hlCacheBytes += size;
}

// fence languages that always get the HTML preview button
const _HTML_LANGS = new Set(['html', 'htm', 'xml', 'xhtml', 'svg', 'vue']);

// decide whether a fenced code block holds HTML
function _isHtmlCode(lang, code) {
    if (lang) return _HTML_LANGS.has(lang.toLowerCase());

    const trimmed = code.trim();
    if (!trimmed.startsWith('<')) return false;

    // a doctype alone is a strong html signal (match any casing)
    if (/^<!doctype\s/i.test(trimmed)) return true;

    // must OPEN with a lowercase tag...
    if (!/^<[a-z][a-z0-9:-]*(?=[\s/>])/.test(trimmed)) return false;

    // ..and actually look like markup
    return /<\/[a-z][a-z0-9:-]*\s*>/i.test(trimmed)
        || /<[a-z][a-z0-9:-]*(?:\s[^<>]*[=/>])/.test(trimmed);
}

function renderMarkdown(text, live = false) {
    if (!text) return '';

    // parse the markdown to HTML
    let html = marked.parse(text);

    // protect against XSS
    html = DOMPurify.sanitize(html);

    _tempHighlightDiv.innerHTML = html;

    // syntax highlighting
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15) status:reviewed
    // per-block highlight cache. during streaming the whole message is
    // re-rendered per paint, which used to re-highlight every code block
    // from scratch - including finished ones. with the cache, only the
    // block that is still growing actually pays for hljs; everything else
    // is a map lookup. (keyed by lang+code, so identical blocks across
    // the whole app share the result too.)
    if (typeof hljs !== 'undefined') {
        const blocks = _tempHighlightDiv.querySelectorAll('pre code');

        blocks.forEach((block, i) => {
            const lang = block.className.replace('language-', '') || undefined;
            const code = block.textContent;
            const key = (lang || 'auto') + '\0' + code;

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15) status:reviewed
            // during live renders, the LAST code block is the one still being
            // streamed: its content is new every frame, so caching it would
            // retain a full highlighted copy of every intermediate state
            // (= ram climbing during streams). skip the cache for it; its
            // final state gets cached on the final (live=false) render.
            const cacheable = !(live && i === blocks.length - 1);

            let highlighted = cacheable ? _hlCacheGet(key) : undefined;
            if (highlighted === undefined) {
                highlighted = (lang && hljs.getLanguage(lang))
                    ? hljs.highlight(code, { language: lang }).value
                    : hljs.highlightAuto(code).value;

                if (cacheable) _hlCacheSet(key, highlighted);
            }

            block.innerHTML = highlighted;
            block.classList.add('hljs');
        });
    }

    // add the buttons to all code blocks.
    _tempHighlightDiv.querySelectorAll('pre').forEach((pre) => {
        const codeEl = pre.querySelector(':scope > code');
        if (!codeEl) return;

        let buttons = '';

        if (!live) {
            const langMatch = codeEl.className.match(/(?:^|\s)language-([\w+#-]+)/);
            if (_isHtmlCode(langMatch ? langMatch[1] : undefined, codeEl.textContent)) {
                buttons += '<button class="preview-btn" type="button">Preview</button>';
            }
        }

        buttons += '<button class="copy-btn" type="button">Copy</button>';

        pre.insertAdjacentHTML('afterbegin', `<div class="code-actions">${buttons}</div>`);
    });

    const out = _tempHighlightDiv.innerHTML;
    _tempHighlightDiv.innerHTML = '';
    return out;
}

// cache of rendered markdown, keyed by the message object itself.
// only messages that are no longer the live one at the end of a streaming
// turn ever get cached, since their content can't change anymore.
const _mdCache = new WeakMap();

const LIVE_SPLIT_MIN_CHARS = 20000;
const LIVE_SPLIT_MIN_STEP = 8192;

const _liveSplitCache = new WeakMap();

function _countFenceLines(text, from, to) {
    let count = 0;
    const re = /^ {0,3}(?:`{3,}|~{3,})/gm;
    re.lastIndex = from;
    let m;
    while ((m = re.exec(text)) !== null && m.index < to) count++;
    return count;
}

function renderMarkdownStream(message) {
    const content = message.content || '';
    if (content.length < LIVE_SPLIT_MIN_CHARS) return renderMarkdown(content, true);

    let st = _liveSplitCache.get(message);

    // reset on shrink (regenerate/edit) or whenever the already-rendered
    // prefix no longer matches
    if (st && (content.length < st.cut ||
        content.slice(Math.max(0, st.cut - 32), st.cut) !== st.marker)) {
        st = null;
    }
    if (!st) st = { cut: 0, html: '', parity: 0, marker: '' };
    _liveSplitCache.set(message, st);

    // walk blank-line boundaries back from the end; accept the newest one
    // that is far enough ahead and lands outside any code fence
    let p = content.lastIndexOf('\n\n');
    while (p > 0) {
        const cut = p + 2;
        if (cut - st.cut < LIVE_SPLIT_MIN_STEP) break;

        const fences = _countFenceLines(content, st.cut, cut);
        if ((st.parity + fences) % 2 === 0) {
            st.html += renderMarkdown(content.slice(st.cut, cut), false);
            st.cut = cut;
            st.parity = 0;
            st.marker = content.slice(Math.max(0, cut - 32), cut);
            break;
        }

        p = content.lastIndexOf('\n\n', p - 1);
    }

    return st.html + renderMarkdown(content.slice(st.cut), true);
}

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

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
    // raw mode: plain escaped text, no markdown pipeline at all.
    // live mode: full pipeline including hljs - affordable now that the
    // per-block cache means only the still-growing block gets highlighted,
    // long messages additionally use the cached-prefix stream split, and
    // the directive coalesces live paints to one per frame.
    const html = raw ? escapeHtml(content)
        : (live ? renderMarkdownStream(message) : renderMarkdown(content, false));

    if (!live && content && html.length <= 2 * 1024 * 1024) {
        _mdCache.set(message, { source: content, html, raw: Boolean(raw) });
    }

    return html;
}
