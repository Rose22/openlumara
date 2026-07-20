/* alpine.js directive that adds autoscrolling to any element
 * by adding x-auto-scroll to your element
 */
function autoScroll(el) {
  let isAtBottom = true;

  const checkBottom = () => {
    const threshold = 50; // px tolerance
    isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold;
  };

  el.addEventListener('scroll', checkBottom);

  const observer = new MutationObserver(() => {
    if (isAtBottom) {
      el.scrollTop = el.scrollHeight;
    }
  });

  observer.observe(el, { childList: true, subtree: true });

  return () => {
    el.removeEventListener('scroll', checkBottom);
    observer.disconnect();
  };
}
