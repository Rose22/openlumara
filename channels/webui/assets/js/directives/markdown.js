/* alpine.js directive that renders markdown into an element, but only does
 * the actual work when it matters:
 *
 *   x-md="{ message: message, live: messageIndex === $store.stream.turn.messages.length - 1 }"
 *
 * for the live message (the last one in a streaming turn), every token
 * re-renders - that's the typewriter, and it keeps syntax highlighting the
 * code as it streams in.
 *
 * for every other message in the turn the content is final, so
 * renderMarkdownFor() serves a cached string and we never touch the dom.
 *
 * unlike x-html, this deliberately does NOT run Alpine's initTree() over the
 * injected subtree. there are no alpine directives left inside rendered
 * markdown (the code copy button is handled by the delegated listener at the
 * bottom of this file), so walking the whole subtree on every single token
 * was pure overhead.
 */
function markdownRender(el, { expression }, { evaluateLater, effect }) {
    let lastHtml = null;

    const getData = evaluateLater(expression);

    effect(() => {
        getData((data) => {
            if (!data || !data.message) return;

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
            // raw flag: escape instead of markdown-render (for is_cmd messages),
            // so history templates can all use this directive instead of x-html.
            const html = renderMarkdownFor(data.message, Boolean(data.live), Boolean(data.raw));

            // nothing changed (or this message is cached and already rendered),
            // so don't touch the dom at all
            if (html === lastHtml) return;
            lastHtml = html;

            Alpine.mutateDom(() => {
                el.innerHTML = html;
            });
        });
    });
}

/*
 * one delegated listener for every copy button that renderMarkdown injects.
 * replaces the per-code-block listeners that x-copy-code used to attach.
 */
document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;

    const code = btn.parentElement?.querySelector('code')?.textContent
        || btn.parentElement?.textContent;

    try {
        await navigator.clipboard.writeText(code);
        btn.textContent = '✓ Copied';
    } catch (err) {
        btn.textContent = '✗ Failed';
    }

    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
});
