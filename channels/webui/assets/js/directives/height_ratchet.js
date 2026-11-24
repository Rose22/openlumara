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
