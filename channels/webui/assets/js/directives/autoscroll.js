/* alpine.js directive that adds autoscrolling to any element
 * by adding x-auto-scroll to your element
 */
function autoScroll(el) {
  let isAtBottom = true;
  // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:25)
  // while our own smooth animation is in flight, the intermediate scroll
  // positions would otherwise flip isAtBottom off and stall the follow;
  // the resting position is evaluated when the animation settles
  let suppressing = false;
  let settleTimer = null;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const checkBottom = () => {
    const threshold = 50; // px tolerance
    isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold;
  };

  const onScroll = () => {
    if (suppressing) return;
    checkBottom();
  };

  el.addEventListener('scroll', onScroll);

  const observer = new MutationObserver(() => {
    if (!isAtBottom) return;

    if (reducedMotion.matches) {
      el.scrollTop = el.scrollHeight;
      return;
    }

    suppressing = true;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });

    const settle = () => {
      suppressing = false;
      clearTimeout(settleTimer);
      el.removeEventListener('scrollend', settle);
      checkBottom();
    };

    el.addEventListener('scrollend', settle);
    clearTimeout(settleTimer);
    settleTimer = setTimeout(settle, 500);
  });

  observer.observe(el, { childList: true, subtree: true });

  return () => {
    el.removeEventListener('scroll', onScroll);
    observer.disconnect();
  };
}
