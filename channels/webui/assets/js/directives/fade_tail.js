// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16) status:reviewed
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

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16) status:reviewed
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

// -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
// the LAST text nodes in document order - walked backwards from the
// element's end and stopped once needChars are covered, so a streamed
// paint pays for the fade window (a few hundred chars) instead of the
// whole message. skipping rules match the old full-subtree walk:
// code-block buttons and already-wrapped spans.
function collectTailTextNodes(root, needChars) {
    const out = [];
    let collected = 0;

    const visit = (node) => {
        if (collected >= needChars) return true;

        if (node.nodeType === Node.TEXT_NODE) {
            const parent = node.parentElement;
            if (!parent || parent.closest('.copy-btn, .preview-btn') || parent.closest('.token-fade')) return false;
            out.push(node);
            collected += node.nodeValue.length;
            return collected >= needChars;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return false;
        if (node.classList.contains('copy-btn') || node.classList.contains('preview-btn') || node.classList.contains('token-fade')) return false;

        for (let i = node.childNodes.length - 1; i >= 0; i--) {
            if (visit(node.childNodes[i])) return true;
        }
        return false;
    };

    visit(root);
    out.reverse();
    return out;
}

// total chars of the batches that still have to be wrapped
function batchCharCount(batches) {
    let need = 0;
    for (const b of batches) need += b.count;
    return need;
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
