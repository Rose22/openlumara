/* alpine.js directive that adds autoscrolling to any element
 * by adding x-auto-scroll to your element
 */
// autoscroll is a pure JS lerp pump: every animation frame the loop moves
// scrollTop itself, closing a fraction of the remaining gap to the bottom.
// the browser is only ever told "be here now" (behavior: instant) - all
// easing is our own exponential decay.
//
// knobs, read fresh per hop so they can be tweaked live from the devtools
// console (shared with stores/ui.js; first file to load initialises):
//   window.AUTOSCROLL_DAMP     gap fraction closed per hop at a 60Hz
//                              reference (converted by actual frame time,
//                              see dampFor). 1 = teleport,
//                              0.1 = the locked-in feel, higher = snappier
//   window.AUTOSCROLL_PUMP_MS  throttle: 0 = every frame; raise it only to
//                              deliberately cut hop frequency (DAMP then
//                              needs raising to keep the overall speed)
window.AUTOSCROLL_DAMP ??= 0.1;
window.AUTOSCROLL_PUMP_MS ??= 0;

/*
 * one-way height while streaming: the live agent chain only ever grows (up
 * to its CSS max-height), never shrinks back when content re-syncs shorter.
 * without the ratchet, a mid-stream retract yanks the whole message list
 * upward - exactly the jump the pump below refuses to chase. when
 * .is-streaming is gone the floor is released (just after the end-of-turn
 * fold animation) and the body collapses to its content size again.
 *
 * syncs from two places: the MutationObserver below (content changes), and
 * the Alpine effect hook in init.js (every morph - that is when
 * .is-streaming flips, and when the directive element first lands in the
 * DOM, since setup itself runs on a detached placeholder).
 */
const AUTOSCROLL_PEAKS = new WeakMap();

function autoscrollSyncStreaming(el) {
    // a live chain: ratchet the floor upward. null peak means the floor was
    // already released, so growth starts fresh instead of re-arming an old
    // (possibly reused) element's stale peak
    if (el.closest && el.closest('.agent-chain.is-streaming')) {
        // a release timer may still be pending when a reused node goes live
        // again: disarm it, its clear must not fire mid-stream
        clearTimeout(el._autoscrollClearTimer);

        const peak = AUTOSCROLL_PEAKS.get(el);
        if (peak === null) AUTOSCROLL_PEAKS.set(el, 0);

        const h = el.scrollHeight;
        if (h > (peak ?? 0)) {
            AUTOSCROLL_PEAKS.set(el, h);
            el.style.minHeight = h + 'px';
        }
        return;
    }

    if (AUTOSCROLL_PEAKS.get(el) && el.style.minHeight) {
        AUTOSCROLL_PEAKS.set(el, null);
        // give the stream_complete fold animation room to play before the
        // floor is removed, so releasing never fights the collapse. if the
        // element morphed back into a live chain by then (instant regenerate
        // reusing the node), leave the floor to the growth path above
        clearTimeout(el._autoscrollClearTimer);
        el._autoscrollClearTimer = setTimeout(() => {
            if (!el.closest || !el.closest('.agent-chain.is-streaming')) el.style.minHeight = '';
        }, 400);
    }
}

function autoScroll(el) {
  let isAtBottom = true;
  let pumpRaf = null;
  let pumpLast = 0;
  let lastScrollHeight = el.scrollHeight;
  let pumpTarget = 0;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');



  const checkBottom = () => {
    const threshold = 50; // px tolerance
    isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold;
  };

  const stopPump = () => {
    if (pumpRaf !== null) {
      cancelAnimationFrame(pumpRaf);
      pumpRaf = null;
    }
  };

  // DAMP is a per-hop fraction at a 60Hz reference, but rAF fires at the
  // display's real refresh rate - so convert by elapsed frame time:
  // 1 - (1-DAMP)^(dt/16.67ms). mathematically identical at 60Hz, and on a
  // 120Hz panel each hop automatically shrinks so the follow runs at the
  // same on-screen speed instead of compounding double-fast. dt is capped
  // so a backgrounded tab or long stall converges in one big hop instead
  // of chasing stale time.
  const dampFor = (dt) => {
    const base = window.AUTOSCROLL_DAMP;
    if (base >= 1) return 1;
    return 1 - Math.pow(1 - base, Math.min(dt, 100) / (1000 / 60));
  };

  // one hop: move scrollTop directly, dampFor(dt) of the remaining gap
  // closer. returns false once the bottom is reached (1px + final snap),
  // which stops the loop and re-evaluates the resting position.
  const pumpHop = (dt) => {
    const bottom = el.scrollHeight - el.clientHeight;

    // Collapsing content lowers the bottom. Do not chase it: that is the jump
    // we are trying to avoid. Let native scroll anchoring hold the visual point.
    if (bottom < pumpTarget - 1) {
      lastScrollHeight = el.scrollHeight;
      stopPump();
      checkBottom();
      return false;
    }

    pumpTarget = Math.max(pumpTarget, bottom);
    const remaining = bottom - el.scrollTop;

    if (remaining <= 1) {
      if (bottom < el.scrollTop - 1) {
        lastScrollHeight = el.scrollHeight;
        stopPump();
        checkBottom();
        return false;
      }

      el.scrollTo({ top: bottom, behavior: 'instant' });
      lastScrollHeight = el.scrollHeight;
      stopPump();
      checkBottom();
      return false;
    }

    el.scrollTo({ top: el.scrollTop + remaining * dampFor(dt), behavior: 'instant' });
    return true;
  };

  // rAF driver: hop every animation frame (throttled by AUTOSCROLL_PUMP_MS).
  // dt comes from the rAF timestamps, so hop size adapts to whatever
  // refresh rate - or hiccup - the display throws at it.
  const pumpStep = (now) => {
    const dt = now - pumpLast;
    if (dt >= window.AUTOSCROLL_PUMP_MS) {
      pumpLast = now;
      if (!pumpHop(dt)) {
        pumpRaf = null;
        return;
      }
    }
    pumpRaf = requestAnimationFrame(pumpStep);
  };

  // user input wins: give up the pump; onScroll resumes bottom-tracking
  const giveUp = () => {
    stopPump();
    el.removeEventListener('wheel', giveUp);
    el.removeEventListener('touchstart', giveUp);
  };

  const onScroll = () => {
    // ignore the intermediate positions of our own pump; the resting
    // position is checked when the pump stops
    if (pumpRaf !== null) return;
    checkBottom();
  };

  el.addEventListener('scroll', onScroll);

  const observer = new MutationObserver(() => {
    autoscrollSyncStreaming(el);

    const height = el.scrollHeight;

    // A collapse is a height decrease. Follow growth only; shrinking content
    // must not pull the user toward the new bottom.
    if (height < lastScrollHeight - 1) {
      lastScrollHeight = height;
      stopPump();
      checkBottom();
      return;
    }

    lastScrollHeight = height;

    if (!isAtBottom) return;

    const bottom = Math.max(0, height - el.clientHeight);
    if (bottom <= el.scrollTop + 1) {
      checkBottom();
      return;
    }

    if (reducedMotion.matches) {
      el.scrollTo({ top: bottom, behavior: 'instant' });
      checkBottom();
      return;
    }

    if (pumpRaf === null) {
      pumpTarget = bottom;
      el.addEventListener('wheel', giveUp, { passive: true });
      el.addEventListener('touchstart', giveUp, { passive: true });
      // seed with the current time so the very first hop sees a real
      // frame-sized dt instead of "time since page load"
      pumpLast = performance.now();
      pumpRaf = requestAnimationFrame(pumpStep);
    }
  });

  observer.observe(el, { childList: true, subtree: true });

  return () => {
    stopPump();
    el.removeEventListener('wheel', giveUp);
    el.removeEventListener('touchstart', giveUp);
    el.removeEventListener('scroll', onScroll);
    observer.disconnect();
  };
}


