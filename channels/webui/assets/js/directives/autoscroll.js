/* alpine.js directive that adds autoscrolling to any element
 * by adding x-auto-scroll to your element
 */
// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
// lerp-chase autoscroll (mirrors ui._chaseScrollToBottom): each frame moves
// scrollTop a fraction of the remaining distance toward the bottom, target
// re-read per frame so streamed content folds into the same glide.
// knob: 0.2 = glidey, 0.5 = snappy, 1 = instant.
const AUTO_SCROLL_SPEED = 0.2;

function autoScroll(el) {
  let isAtBottom = true;
  let raf = null;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const checkBottom = () => {
    const threshold = 50; // px tolerance
    isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold;
  };

  const stopChase = () => {
    if (raf !== null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
    el.removeEventListener('wheel', stopChase);
    el.removeEventListener('touchstart', stopChase);
  };

  const step = () => {
    const target = el.scrollHeight - el.clientHeight;
    const remaining = target - el.scrollTop;
    if (Math.abs(remaining) < 1) {
      el.scrollTop = target;
      stopChase();
      checkBottom();
      return;
    }
    el.scrollTop += remaining * AUTO_SCROLL_SPEED;
    raf = requestAnimationFrame(step);
  };

  const onScroll = () => {
    // ignore the intermediate positions of our own chase; the resting
    // position is checked when the chase stops
    if (raf !== null) return;
    checkBottom();
  };

  el.addEventListener('scroll', onScroll);

  const observer = new MutationObserver(() => {
    if (!isAtBottom) return;

    if (reducedMotion.matches) {
      el.scrollTop = el.scrollHeight;
      return;
    }

    if (raf === null) {
      // user input wins: give up the chase, onScroll resumes tracking
      el.addEventListener('wheel', stopChase, { passive: true });
      el.addEventListener('touchstart', stopChase, { passive: true });
      raf = requestAnimationFrame(step);
    }
  });

  observer.observe(el, { childList: true, subtree: true });

  return () => {
    stopChase();
    el.removeEventListener('scroll', onScroll);
    observer.disconnect();
  };
}
