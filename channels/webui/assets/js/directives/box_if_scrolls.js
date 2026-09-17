/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
 * alpine directive that toggles a .boxed class on an element whenever its
 * content overflows its max-height. used by tool call arg values so the
 * soft background container only appears for values that actually scroll,
 * while short values stay plain text.
 */
function boxIfScrolls(el) {
  const check = () => {
    el.classList.toggle('boxed', el.scrollHeight > el.clientHeight + 1);
  };

  const ro = new ResizeObserver(check);
  ro.observe(el);

  const mo = new MutationObserver(check);
  mo.observe(el, { childList: true, subtree: true, characterData: true });

  check();

  return () => {
    ro.disconnect();
    mo.disconnect();
  };
}
