/* alpine.js directive that renders markdown into an element, but only does
 * the actual work when it matters:
 *
 *   x-md="{ message: message, live: message.is_tail === true }"
 *
 * for the live message (the last one in a streaming turn), paints are
 * coalesced to one per animation frame (vsync-synced, ~120fps ceiling).
 * highlighting runs live; it's cheap because renderMarkdown caches
 * highlighted code blocks and only the still-growing one re-highlights.
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
function markdownRender(el, { expression }, { evaluateLater, effect, cleanup }) {
    let paintedMessage = null;
    let paintedLive = null;
    let paintedRaw = null;
    let paintedLen = -1;

    let pendingHtml = null;
    let pendingLen = 0;
    let pendingMessage = null;
    let pendingRaw = false;
    let rafId = null;

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16) status:reviewed
    // per-token fade via the shared timeline machinery (fade_tail.js):
    // everything streamed within the last window gets re-wrapped in
    // .token-fade spans with negative animation-delays, so fades continue
    // seamlessly across the wholesale innerHTML replacement of each paint.
    const timeline = new TailFadeTimeline();
    let lastLen = 0;

    const paint = (html, batches, message, live, raw) => {
        const len = message && message.content ? message.content.length : 0;
        if (paintedMessage === message && paintedLive === live && paintedRaw === raw && paintedLen === len) return;

        paintedMessage = message;
        paintedLive = live;
        paintedRaw = raw;
        paintedLen = len;

        Alpine.mutateDom(() => {
            el.innerHTML = html;
            // NOTE: [] is truthy, must check length - otherwise a disabled
            // fade still pays for the full subtree walk every frame
            if (batches && batches.length) {
                const nodes = collectTextNodes(el);
                // newest batch first; wrapTailChars skips already-wrapped
                // nodes, so successive calls peel further back from the tail
                for (const b of batches) wrapTailChars(nodes, b.count, b.delay);
            }
        });
    };

    cleanup(() => {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = null;
        pendingHtml = null;
        pendingMessage = null;
        paintedMessage = null;
    });

    const getData = evaluateLater(expression);

    effect(() => {
        getData((data) => {
            if (!data || !data.message) return;

            const live = Boolean(data.live);
            const raw = Boolean(data.raw);

            if (live) {
                // keep only the newest html; one paint per frame, at vsync.
                // worst-case latency is a single frame (~8ms on 120hz),
                // which is far below perception.

                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16) status:reviewed
                // record the content length so each paint frame becomes a
                // timeline sample for the fade continuation logic.
                pendingHtml = renderMarkdownFor(data.message, true, raw);
                pendingLen = (data.message.content || '').length;
                pendingMessage = data.message;
                pendingRaw = raw;

                if (rafId === null) {
                    rafId = requestAnimationFrame(() => {
                        rafId = null;
                        const latest = pendingHtml;
                        const latestLen = pendingLen;
                        const latestMessage = pendingMessage;
                        const latestRaw = pendingRaw;
                        pendingHtml = null;
                        pendingMessage = null;
                        if (latest === null) return;

                        const now = performance.now();

                        // content shrank (regenerate/edit): no fade, reset
                        if (latestLen < lastLen) timeline.reset();
                        lastLen = latestLen;

                        paint(latest, timeline.record(latestLen, now), latestMessage, true, latestRaw);
                    });
                }
                return;
            }

            // final render: cancel any pending frame paint and replace it
            // immediately with the definitive (cached) version
            if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; pendingHtml = null; pendingLen = 0; pendingMessage = null; }

            const finalLen = (data.message.content || '').length;
            if (paintedMessage === data.message && paintedLive === false &&
                paintedRaw === raw && paintedLen === finalLen) return;

            timeline.reset();
            lastLen = finalLen;
            paint(renderMarkdownFor(data.message, false, raw), [], data.message, false, raw);
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

    // buttons live in a .code-actions wrapper inside the pre, so walk up to
    // the pre itself before looking for the code element
    const pre = btn.closest('pre');
    const code = pre?.querySelector('code')?.textContent || pre?.textContent;

    try {
        await navigator.clipboard.writeText(code);
        btn.textContent = '✓ Copied';
    } catch (err) {
        btn.textContent = '✗ Failed';
    }

    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
});

/*
 * one delegated listener for the Preview button that renderMarkdown injects
 * on HTML code blocks: pushes the raw code into the docked preview panel
 * (see stores/html_preview.js + templates/chat/html_preview.html).
 */
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.preview-btn');
    if (!btn) return;

    const code = btn.closest('pre')?.querySelector('code')?.textContent;
    if (code) Alpine.store('htmlPreview').show(code);
});
