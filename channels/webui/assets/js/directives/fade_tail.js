// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
/* shared machinery for the streamed-token fade-in.

   every streaming paint replaces the element's content wholesale, which
   destroys any animating span mid-flight. to keep fades smooth across
   repaints, we keep a timeline of (paint time, rendered text length)
   samples: everything that appeared within the last TOKEN_FADE_MS gets
   re-wrapped in a .token-fade span with a negative animation-delay equal
   to the time already elapsed, so each batch resumes its fade instead of
   restarting or snapping opaque.

   used by the x-md directive (assistant content) and the x-fade-text /
   x-fade-html directives (reasoning, tool call args, tool responses). */

const TOKEN_FADE_DEFAULT_MS = 350;

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// user-configurable fade duration (settings modal -> appearance).
// read fresh on every paint so changes apply without a reload.
// 0 (or disabled) means no fade at all.
function tokenFadeDuration() {
    if (localStorage.getItem('tokenFadeEnabled') === 'false') return 0;
    const ms = parseInt(localStorage.getItem('tokenFadeMs'), 10);
    return Number.isNaN(ms) ? TOKEN_FADE_DEFAULT_MS : ms;
}

class TailFadeTimeline {
    constructor() {
        this.samples = [];
        this.lastLen = 0;
    }

    // record a paint of `len` text chars at `now`. returns the fade
    // batches still within the window, newest first: [{count, delay}]
    record(len, now) {
        // fade disabled (or duration set to 0): keep the timeline empty
        const fadeMs = tokenFadeDuration();
        if (fadeMs <= 0) {
            this.samples = [];
            this.lastLen = len;
            return [];
        }

        // content shrank (regenerate/edit/markdown reparse): drop the
        // timeline so stale lengths can't produce bogus batches
        if (len < this.lastLen) this.samples = [];
        this.lastLen = len;

        this.samples.push({ t: now, len });

        // find the newest sample whose fade has completed (older than the
        // window): everything up to its len is settled, everything after
        // it still fades
        const cutoff = now - fadeMs;
        let anchorIdx = -1;
        for (let i = this.samples.length - 1; i >= 0; i--) {
            if (this.samples[i].t <= cutoff) { anchorIdx = i; break; }
        }
        if (anchorIdx > 0) this.samples = this.samples.slice(anchorIdx);

        const batches = [];
        const start = this.samples[0].t <= cutoff ? 1 : 0;
        for (let i = this.samples.length - 1; i >= start; i--) {
            const prevLen = i > 0 ? this.samples[i - 1].len : 0;
            const count = this.samples[i].len - prevLen;
            if (count > 0) batches.push({ count, delay: now - this.samples[i].t });
        }
        return batches;
    }

    reset() {
        this.samples = [];
        this.lastLen = 0;
    }
}

// text nodes in document order, skipping copy buttons and any tail spans
// we already wrapped during this paint
function collectTextNodes(node) {
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let tn;
    while ((tn = walker.nextNode())) {
        const parent = tn.parentElement;
        if (!parent || parent.closest('.copy-btn') || parent.closest('.token-fade')) continue;
        nodes.push(tn);
    }
    return nodes;
}

// wrap the last `count` chars in a .token-fade span with the given elapsed
// delay. walks from the tail and skips already-wrapped nodes, so calling
// it repeatedly (newest batch first) peels successive older batches off
// the tail without double-wrapping.
function wrapTailChars(nodes, count, delayMs) {
    let remaining = count;
    for (let i = nodes.length - 1; i >= 0 && remaining > 0; i--) {
        const textNode = nodes[i];
        if (textNode.parentElement.closest('.token-fade')) continue;

        const len = textNode.nodeValue.length;

        let toWrap;
        if (remaining >= len) {
            toWrap = textNode;
            remaining -= len;
        } else {
            // only the tail of this node belongs to this batch: split it
            toWrap = textNode.splitText(len - remaining);
            remaining = 0;
        }

        const span = document.createElement('span');
        span.className = 'token-fade';
        if (delayMs > 0) span.style.animationDelay = '-' + Math.round(delayMs) + 'ms';
        toWrap.parentNode.insertBefore(span, toWrap);
        span.appendChild(toWrap);
    }
}
