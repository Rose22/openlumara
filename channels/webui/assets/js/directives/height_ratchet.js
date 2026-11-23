/* alpine.js directive that ratchets a scroll container's height while the
 * watched expression is true: the container may grow with its content but
 * never shrink below its tallest so far; once the expression turns false it
 * releases to plain content height. The ratchet itself is capped by the
 * element's own CSS max-height and by the chat viewport, so an expanded
 * chain can never leave a taller-than-screen empty bubble behind.
 * usage: x-height-ratchet="$store.stream.state !== 'idle'"
 */
function heightRatchet(el, getActive, effect, cleanup) {
  let peak = 0;
  let ro = null;
  let onResize = null;

  const viewportCapPx = () => {
    const scroller = el.closest('#messages');
    if (scroller?.clientHeight) return scroller.clientHeight;
    return document.documentElement.clientHeight || window.innerHeight;
  };

  const capPx = () => {
    const cssCap = parseFloat(getComputedStyle(el).maxHeight);
    return Math.min(Number.isFinite(cssCap) ? cssCap : Infinity, viewportCapPx());
  };

  const apply = () => {
    const h = Math.min(peak, capPx());
    el.style.minHeight = h > 0 ? h + 'px' : '';
  };

  const record = () => {
    // Keep the stored peak itself viewport-capped. Otherwise a later resize
    // could resurrect a multi-screen pin from an old unbounded peak.
    peak = Math.min(Math.max(peak, el.clientHeight), capPx());
    apply();
  };

  const stop = () => {
    if (ro !== null) {
      ro.disconnect();
      ro = null;
    }
    if (onResize !== null) {
      window.removeEventListener('resize', onResize);
      onResize = null;
    }
    peak = 0;
    el.style.minHeight = '';
  };

  const start = () => {
    peak = 0;
    onResize = () => apply();
    window.addEventListener('resize', onResize);
    ro = new ResizeObserver(record);
    ro.observe(el);
    record();
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
