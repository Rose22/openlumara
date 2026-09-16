// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
/* drop-in replacements for x-text / x-html that fade newly streamed
   content in instead of popping it into existence. used for reasoning
   text, tool call arguments and tool responses.

   like x-md, live paints are coalesced to one per animation frame, and
   the fade survives the wholesale content replacement via the shared
   timeline in fade_tail.js (negative animation-delays continue each
   batch's fade across repaints).

   usage:
     x-fade-text="message.reasoning_content"
     x-fade-html="toolResultsRenderer(...)"
*/
function fadeTextRender(el, { expression }, { evaluateLater, effect, cleanup }, asHtml = false) {
    const timeline = new TailFadeTimeline();
    let lastValue = null;
    let pending = null;
    let rafId = null;

    const frame = () => {
        rafId = null;
        if (pending === null) return;
        const value = pending;
        pending = null;

        Alpine.mutateDom(() => {
            if (asHtml) el.innerHTML = value;
            else el.textContent = value;

            // fade disabled: skip the subtree walk + counting entirely,
            // the timeline would just clear itself anyway. record keeps
            // lastLen roughly synced so re-enabling mid-stream doesn't
            // produce one giant bogus batch off a stale length.
            if (tokenFadeDuration() <= 0) {
                timeline.record(value.length, performance.now());
                return;
            }

            // count the actually rendered text chars (skipping copy
            // buttons), so the fade window tracks what's on screen rather
            // than raw source length
            const nodes = collectTextNodes(el);
            let total = 0;
            for (const n of nodes) total += n.nodeValue.length;

            const now = performance.now();

            // shrinking text (regenerate, partial-json escape resolution)
            // is not a stream continuation: repaint clean, no fade
            const shrank = total < timeline.lastLen;
            if (shrank) timeline.reset();

            const batches = timeline.record(total, now);
            if (!shrank) {
                for (const b of batches) wrapTailChars(nodes, b.count, b.delay);
            }
        });
    };

    cleanup(() => {
        if (rafId) cancelAnimationFrame(rafId);
    });

    const getData = evaluateLater(expression);

    effect(() => {
        getData((value) => {
            value = value ?? '';
            if (value === lastValue) return;
            lastValue = value;
            pending = value;

            if (rafId === null) rafId = requestAnimationFrame(frame);
        });
    });
}
