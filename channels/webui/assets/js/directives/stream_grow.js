function streamGrow(el) {
    // Pinning is disabled for now. Clear any leftover inline height so cached
    // sessions do not keep old grow-only blank space after a reload.
    Alpine.mutateDom(() => {
        el.classList.remove('grow-pin-active', 'stream-grow-released');
        el.style.minHeight = '';
    });

    return () => {};
}
