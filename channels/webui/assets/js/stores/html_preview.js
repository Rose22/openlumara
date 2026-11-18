/*
 * state for the docked HTML preview panel (right side of the webui).
 *
 * renderers/markdown.js detects fenced HTML code blocks and injects a
 * Preview button; the delegated listener in directives/markdown.js pushes
 * the raw code here via show().
 *
 * the panel renders the code in an iframe via srcdoc: the code's JavaScript
 * runs (deliberately bypassing DOMPurify for this feature), but the sandbox
 * omits allow-same-origin, so the previewed code executes against an opaque
 * origin and can never touch the app itself, its storage or its tokens.
 */
/*
 * guard script, prepended to the previewed document: blocks navigation via
 * links, form submits and window.open, so the preview can never leave itself
 * for an external site. in-page (#fragment) links and javascript: hrefs keep
 * working, and click handlers on anchors still fire - only the navigation
 * default is cancelled. (new-tab vectors are additionally blocked server-side
 * by leaving allow-popups out of the iframe sandbox.)
 */
/*
 * theme bridge: the iframe is opaque-origin, so it can't read the app's CSS
 * custom properties. we serialize them instead: every --var currently set on
 * <html> (the theme store writes them all inline, plus anything a theme's
 * sidecar css exposes via computed style) into a :root rule, alongside the
 * google-font <link>s when a custom font is active, plus a minimal base
 * styling so bare snippets pick up the app look. inserted BEFORE the code's
 * own styles, so content that styles itself still wins.
 */
function _themeStyleBlock() {
    const root = document.documentElement;

    const names = new Set();
    for (const name of root.style) names.add(name);
    // computed style enumeration may or may not include custom props
    // depending on the engine; whatever it adds is a bonus (sidecar themes)
    const cs = getComputedStyle(root);
    for (const name of cs) {
        if (name.startsWith('--')) names.add(name);
    }

    // read values via computed style: inline misses anything a theme's
    // sidecar stylesheet defines
    let vars = '';
    for (const name of names) {
        const value = cs.getPropertyValue(name);
        if (value) vars += `${name}:${value};`;
    }

    const mode = (Alpine.store('theme') && Alpine.store('theme').mode) || 'dark';

    let fontLinks = '';
    document.querySelectorAll('link[href*="fonts.googleapis"]').forEach((l) => {
        fontLinks += `<link rel="stylesheet" href="${l.href}">`;
    });

    return `<style>` +
        `:root{color-scheme:${mode};${vars}}` +
        `html{background:var(--bg-primary);color:var(--text-primary);` +
        `font-family:var(--font-primary,Arial,sans-serif);font-size:var(--font-size-base,16px);line-height:1.6}` +
        `::-webkit-scrollbar{width:6px;height:6px}` +
        `::-webkit-scrollbar-thumb{background:var(--scrollbar,transparent);border-radius:99px}` +
        `::-webkit-scrollbar-track{background:transparent}` +
        `*{scrollbar-width:thin;scrollbar-color:var(--scrollbar,transparent) transparent}` +
        `</style>` + fontLinks;
}

const HTML_PREVIEW_GUARD = '<script>' +
    'document.addEventListener("click", function (e) {' +
        'var a = e.target && e.target.closest ? e.target.closest("a") : null;' +
        'if (!a) return;' +
        'var href = a.getAttribute("href");' +
        'if (href === null) return;' +
        'if (href.charAt(0) === "#" || /^javascript:/i.test(href)) return;' +
        'e.preventDefault();' +
    '}, true);' +
    'document.addEventListener("submit", function (e) { e.preventDefault(); }, true);' +
    'window.open = function () { return null; };' +
'</scr' + 'ipt>';

HTML_PREVIEW_STORE = {
    open: false,
    html: '',

    // inject the app's theme vars into the preview, or render purely with
    // the html's own styling. remembered across sessions.
    useTheme: localStorage.getItem('htmlPreviewUseTheme') !== 'false',

    toggleTheme() {
        this.useTheme = !this.useTheme;
        localStorage.setItem('htmlPreviewUseTheme', this.useTheme);
        if (this.open) this.refresh();
    },

    // what the iframe actually loads: guard + theme bridge + the raw code.
    // the theme bridge is skipped when the toggle is off.
    // a leading <!DOCTYPE> must stay the very first thing in the document,
    // or the preview drops into quirks mode - so both go after it.
    get srcdoc() {
        if (!this.html) return '';

        const inject = HTML_PREVIEW_GUARD + (this.useTheme ? _themeStyleBlock() : '');

        const doctype = /^\s*<!DOCTYPE[^>]*>/i.exec(this.html);
        if (doctype) {
            const end = doctype.index + doctype[0].length;
            return this.html.slice(0, end) + inject + this.html.slice(end);
        }
        return inject + this.html;
    },

    // remembered across opens during the session
    width: Math.max(340, Math.min(720, Math.round(window.innerWidth * 0.42))),

    show(code) {
        this.html = code;
        this.open = true;
    },

    close() {
        if (this._resizeDrag) this._resizeDrag.cleanup();
        this.open = false;
        this.html = '';
    },

    // re-run the preview: blank the srcdoc for a tick, then restore it,
    // which forces the iframe to reload even on identical content
    refresh() {
        const content = this.html;
        this.html = '';
        Alpine.nextTick(() => { this.html = content; });
    },

    openInTab() {
        const url = URL.createObjectURL(new Blob([this.html], { type: 'text/html' }));
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    },

    // drag the handle on the panel's left edge to resize
    startResize(e) {
        if (this._resizeDrag) {
            e.preventDefault();
            return;
        }

        e.preventDefault();

        const pointerId = e.pointerId;
        const target = e.currentTarget || e.target;

        try {
            target.setPointerCapture(pointerId);
        } catch (err) {}

        const move = (ev) => {
            if (ev.pointerId !== undefined && ev.pointerId !== pointerId) return;
            this._setWidth(window.innerWidth - ev.clientX);
        };

        let ended = false;
        const stop = (ev) => {
            if (ev && ev.pointerId !== undefined && ev.pointerId !== pointerId) return;
            if (ended) return;

            ended = true;
            this._resizeDrag = null;

            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', stop);
            window.removeEventListener('pointercancel', stop);
            window.removeEventListener('blur', stop);
            if (target) target.removeEventListener('lostpointercapture', stop);
            document.body.style.userSelect = '';

            try {
                if (target.hasPointerCapture(pointerId)) target.releasePointerCapture(pointerId);
            } catch (err) {}
        };

        this._resizeDrag = { pointerId, cleanup: stop };

        document.body.style.userSelect = 'none';
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', stop);
        window.addEventListener('pointercancel', stop);
        window.addEventListener('blur', stop);
        if (target) target.addEventListener('lostpointercapture', stop);
    },

    _setWidth(px) {
        // leave at least a usable sliver of chat to the left
        const max = Math.max(340, window.innerWidth - 360);
        this.width = Math.max(300, Math.min(px, max));
    },
}

// the srcdoc's theme vars are baked in when it's (re)built, so a theme
// switch while the panel is open has to force a reload to restyle it
window.addEventListener('theme-changed', () => {
    const store = Alpine.store('htmlPreview');
    if (store && store.open && store.useTheme) store.refresh();
});
