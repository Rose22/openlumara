// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-11-07 status:unreviewed
/*
 * marked extension: raw <svg> / HTML container blocks may span blank lines.
 * (fix for github issue #122)
 *
 * In CommonMark an HTML block always ends at its first blank line, so raw
 * SVG or HTML written inline by a model (which loves blank lines for
 * readability) gets torn apart: the element is closed early and everything
 * after the blank line turns into an indented code block.
 *
 * This extension tokenizes a block-level container tag (<svg>, <div>,
 * <table>, ...) from its opening tag through its *matching* closing tag,
 * blank lines included, so the whole block survives as one HTML token and
 * renders as one element.
 *
 * notes:
 * - only container tags trigger this; inline tags (<b>, <span>, ...) keep
 *   normal markdown behavior, so inline html inside prose is untouched.
 * - the closing tag is found by counting nesting of the container tag
 *   itself, so nested <div>s work. comments/CDATA are skipped whole, so a
 *   stray '<div' inside one can't throw the count off.
 * - an unclosed container (typo, or still streaming) consumes the rest of
 *   the source: a growing SVG renders as one block instead of split halves.
 * - pre/code/script/style/textarea are deliberately left to marked: its own
 *   html block rule already allows blank lines inside those.
 * - this only changes TOKENIZING. DOMPurify still sanitizes the final html
 *   (see renderers/markdown.js and modules/docs/webui/assets/js/docs.js),
 *   so nothing here bypasses the XSS protection.
 */
(function () {
    if (typeof marked === 'undefined' || !marked.use) return;

    // block-level containers that models write with blank lines inside.
    // tags with optional closing tags (p, li, td, tr, ...) are excluded on
    // purpose: an unclosed one of those would swallow the whole message.
    const CONTAINER_TAGS = new Set([
        'svg', 'html', 'body', 'div', 'table', 'thead', 'tbody', 'tfoot',
        'section', 'article', 'aside', 'header', 'footer', 'nav', 'main',
        'figure', 'details', 'summary', 'form', 'fieldset', 'blockquote',
        'ul', 'ol', 'dl', 'center', 'video', 'audio', 'canvas', 'picture',
        'iframe', 'object', 'select', 'template'
    ]);

    const OPEN_TAG = /^ {0,3}<([A-Za-z][A-Za-z0-9:-]*)(?=[\s/>])/;
    const ANY_OPEN_TAG = /(?:^|\n) {0,3}<([A-Za-z][A-Za-z0-9:-]*)(?=[\s/>])/g;

    function escapeRegex(value) {
        return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // walks forward from the opening tag and returns the index just past
    // the matching closing tag, or -1 when the container never closes.
    function findClosingTag(src, tag, from) {
        const scanner = new RegExp(
            '<!--[\\s\\S]*?(?:-->|$)' +
            '|<!\\[CDATA\\[[\\s\\S]*?(?:\\]\\]>|$)' +
            '|</?' + escapeRegex(tag) + '(?=[\\s/>])[^>]*?>',
            'gi'
        );
        scanner.lastIndex = from;

        let depth = 0;
        let match;
        while ((match = scanner.exec(src)) !== null) {
            // comment or CDATA: contents don't count
            if (match[0][1] === '!') continue;

            if (match[0][1] === '/') {
                depth--;
            } else if (match[0].slice(-2) !== '/>') {
                depth++;
            }

            if (depth <= 0) return scanner.lastIndex;
        }
        return -1;
    }

    marked.use({
        extensions: [{
            name: 'rawHtmlContainer',
            level: 'block',

            // tells the lexer a paragraph can end at a line starting a
            // container tag, so '<svg>' after a text line still gets its
            // own block instead of being absorbed into the paragraph.
            start(src) {
                ANY_OPEN_TAG.lastIndex = 0;
                let match;
                while ((match = ANY_OPEN_TAG.exec(src)) !== null) {
                    if (CONTAINER_TAGS.has(match[1].toLowerCase())) {
                        return match.index;
                    }
                }
                return undefined;
            },

            tokenizer(src) {
                const open = OPEN_TAG.exec(src);
                if (!open) return undefined;

                const tag = open[1].toLowerCase();
                if (!CONTAINER_TAGS.has(tag)) return undefined;

                const end = findClosingTag(src, tag, open[0].indexOf('<'));

                let raw;
                if (end === -1) {
                    // never closed: take everything, so a still-streaming
                    // block renders whole instead of splitting at the first
                    // blank line (DOMPurify closes the element for us).
                    raw = src;
                } else {
                    // also take the rest of the line after the close tag,
                    // so '</svg> trailing text' doesn't confuse the lexer
                    const nl = src.indexOf('\n', end);
                    raw = (nl === -1) ? src : src.slice(0, nl + 1);
                }

                return {
                    type: 'rawHtmlContainer',
                    raw,
                    text: raw.trim(),
                    block: true
                };
            },

            renderer(token) {
                return token.raw;
            }
        }]
    });
})();
