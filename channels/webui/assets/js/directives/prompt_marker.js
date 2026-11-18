/* alpine directive for the pinned-prompt feature. watches a zero-height
   marker sitting in the normal flow just above a user turn and evaluates
   the expression whenever the marker's real flow position enters or leaves
   the messages viewport, with an `intersecting` boolean in scope.

   the turn itself can't be observed: while pinned it is sticky, so an
   observer on it always reports it as visible and the pin toggles in a
   loop. the marker never moves from its flow position, so its intersection
   is the turn's true position. */
function promptMarker(el, evaluate) {
    const root = document.getElementById('messages');
    if (!root) return () => {};

    const observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            evaluate(entry.isIntersecting);
        }
    }, { root });

    observer.observe(el);

    return () => observer.disconnect();
}
