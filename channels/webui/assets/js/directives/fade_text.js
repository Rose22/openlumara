// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16) status:reviewed
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
    const exactMax = 65536;
    let lastValue = null;
    let lastLen = -1;
    let lastHash = -1;
    let pending = null;
    let rafId = null;

    const hashValue = (value) => {
        let h = 2166136261;
        for (let i = 0; i < value.length; i++) {
            h ^= value.charCodeAt(i);
            h = Math.imul(h, 16777619) >>> 0;
        }
        return h;
    };

    const matchesLast = (value) => {
        if (value === lastValue) return true;
        if (lastLen !== value.length) return false;
        if (lastLen <= exactMax) return false;
        if (lastHash === -1) return false;
        return hashValue(value) === lastHash;
    };

    const noteValue = (value) => {
        lastLen = value.length;
        if (value.length <= exactMax) {
            lastValue = value;
            lastHash = -1;
        } else {
            lastValue = null;
            lastHash = hashValue(value);
        }
    };

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
                timeline.record(asHtml ? el.textContent.length : value.length, performance.now());
                return;
            }

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
            // total rendered chars: plain text is the source string itself
            // (textContent was just assigned); html uses one native
            // textContent read instead of a per-node JS walk
            const total = asHtml ? el.textContent.length : value.length;

            const now = performance.now();

            // shrinking text (regenerate, partial-json escape resolution)
            // is not a stream continuation: repaint clean, no fade
            const shrank = total < timeline.lastLen;
            if (shrank) timeline.reset();

            const batches = timeline.record(total, now);
            if (!shrank && batches.length) {
                // only the tail nodes the batches actually reach
                const nodes = collectTailTextNodes(el, batchCharCount(batches) + 64);
                for (const b of batches) wrapTailChars(nodes, b.count, b.delay);
            }
        });
    };

    cleanup(() => {
        if (rafId) cancelAnimationFrame(rafId);
        rafId = null;
        pending = null;
        lastValue = null;
        lastLen = -1;
        lastHash = -1;
    });

    const getData = evaluateLater(expression);

    effect(() => {
        getData((value) => {
            value = String(value ?? '');
            if (matchesLast(value)) return;
            noteValue(value);
            pending = value;

            if (rafId === null) rafId = requestAnimationFrame(frame);
        });
    });
}
