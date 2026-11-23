/* alpine.js directive that ratchets a scroll container's height while the
 * watched expression is true: the container may grow with its content but
 * never shrink back down; once the expression turns false it releases to
 * plain content height. The height always stays capped by the element's own
 * CSS max-height, so it remains a scrolling container.
 * usage: x-height-ratchet="$store.stream.state !== 'idle'"
 */
function heightRatchet(el, getActive, effect, cleanup) {
  let peak = 0;
  let ro = null;

  const capPx = () => {
    const cap = parseFloat(getComputedStyle(el).maxHeight);
    return Number.isFinite(cap) ? cap : Infinity;
  };

  const apply = () => {
    // clientHeight already respects the CSS cap, so peak can never exceed
    // it; clamping at apply time also handles the cap shrinking (e.g. a
    // window resize lowering 60vh) under an old peak
    const h = Math.min(peak, capPx());
    el.style.minHeight = h > 0 ? h + 'px' : '';
  };

  const stop = () => {
    if (ro !== null) {
      ro.disconnect();
      ro = null;
    }
    peak = 0;
    el.style.minHeight = '';
  };

  const start = () => {
    peak = el.clientHeight;
    ro = new ResizeObserver(() => {
      peak = Math.max(peak, el.clientHeight);
      apply();
    });
    ro.observe(el);
    apply();
  };

  // evaluateLater returns a getter that delivers its value through a
  // callback - calling it INSIDE the effect is also what tracks the store
  effect(() => {
    getActive((active) => {
      if (active) {
        if (ro === null) start();
      } else if (ro !== null) {
        stop();
      }
    });
  });

  cleanup(stop);
}
