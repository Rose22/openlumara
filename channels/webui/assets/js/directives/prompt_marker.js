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
