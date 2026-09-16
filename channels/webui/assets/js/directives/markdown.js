/* alpine.js directive that renders markdown into an element, but only does
 * the actual work when it matters:
 *
 *   x-md="{ message: message, live: messageIndex === $store.stream.turn.messages.length - 1 }"
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
    let lastHtml = null;

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
    // streaming garbage control: each token carries the FULL accumulated
    // content, so intermediate renders are redundant - only the newest one
    // matters. live paints are coalesced per animation frame instead of per
    // token: on a 120hz display that's a 120fps ceiling, since paints
    // beyond one per frame cannot be seen and are pure garbage. the final
    // (live=false) render is immediate.
    let pendingHtml = null;
    let pendingLen = 0;
    let rafId = null;

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    // per-token fade via the shared timeline machinery (fade_tail.js):
    // everything streamed within the last window gets re-wrapped in
    // .token-fade spans with negative animation-delays, so fades continue
    // seamlessly across the wholesale innerHTML replacement of each paint.
    const timeline = new TailFadeTimeline();
    let lastLen = 0;

    const paint = (html, batches) => {
        if (html === lastHtml) return;
        lastHtml = html;

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

                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
                // record the content length so each paint frame becomes a
                // timeline sample for the fade continuation logic.
                pendingHtml = renderMarkdownFor(data.message, true, raw);
                pendingLen = (data.message.content || '').length;

                if (rafId === null) {
                    rafId = requestAnimationFrame(() => {
                        rafId = null;
                        const latest = pendingHtml;
                        const latestLen = pendingLen;
                        pendingHtml = null;
                        if (latest === null) return;

                        const now = performance.now();

                        // content shrank (regenerate/edit): no fade, reset
                        if (latestLen < lastLen) timeline.reset();
                        lastLen = latestLen;

                        paint(latest, timeline.record(latestLen, now));
                    });
                }
                return;
            }

            // final render: cancel any pending frame paint and replace it
            // immediately with the definitive (cached) version
            if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; pendingHtml = null; pendingLen = 0; }
            timeline.reset();
            lastLen = (data.message.content || '').length;
            paint(renderMarkdownFor(data.message, false, raw));
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
