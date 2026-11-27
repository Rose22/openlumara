/* -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: 2026-11-27 harness:openlumara */
function initMultilineInput() {
    const wrapper = document.querySelector('.input-wrapper');
    const textarea = wrapper?.querySelector('#user-input');
    if (!wrapper || !textarea) return;

    // offsetHeight threshold from the original logic: 48px single-line height
    // plus borders minus 2; clone height excludes borders, so the line-count
    // verdict is identical to the old live-height check.
    const MIN_MULTILINE_HEIGHT = 54;
    const CLONE_PROPS = [
        'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
        'fontFamily', 'lineHeight', 'letterSpacing', 'wordSpacing',
        'textRendering', 'paddingTop', 'paddingRight', 'paddingBottom',
        'paddingLeft', 'boxSizing', 'wordBreak', 'overflowWrap', 'whiteSpace',
    ];

    let clone = null;

    // width the textarea has with all action buttons visible (the single-line
    // layout), so the wrap point never moves with the class. Read by briefly
    // removing the class: both class flips happen inside one synchronous
    // block, so no frame ever renders the intermediate state.
    const referenceWidth = () => {
        const wasMultiline = wrapper.classList.contains('is-multiline');
        if (wasMultiline) wrapper.classList.remove('is-multiline');
        const width = textarea.clientWidth;
        if (wasMultiline) wrapper.classList.add('is-multiline');
        return width;
    };

    const measure = () => {
        if (!clone) {
            clone = document.createElement('div');
            clone.setAttribute('aria-hidden', 'true');
            clone.style.position = 'absolute';
            clone.style.top = '0';
            clone.style.left = '-9999px';
            clone.style.visibility = 'hidden';
            clone.style.pointerEvents = 'none';
            clone.style.overflow = 'hidden';
            clone.style.height = 'auto';
            document.body.appendChild(clone);
        }
        const styles = getComputedStyle(textarea);
        for (const prop of CLONE_PROPS) clone.style[prop] = styles[prop];
        // mirror the scrollbar the textarea may show at max-height, so both
        // the reference width and the clone width exclude it consistently.
        const hasScrollbar = textarea.scrollHeight > textarea.clientHeight;
        clone.style.overflowY = hasScrollbar ? 'scroll' : 'hidden';
        clone.style.width = referenceWidth() + 'px';
        clone.textContent = textarea.value;
        return clone.offsetHeight;
    };

    const update = () => wrapper.classList.toggle('is-multiline', measure() > MIN_MULTILINE_HEIGHT);

    textarea.addEventListener('input', update);
    // fires after autosize finishes a reflow whose height changed
    textarea.addEventListener('autosize:resized', update);
    // container width changes (window resize, sidebar toggles) move the wrap
    // point; safe now that measurement no longer depends on the class state.
    const observer = new ResizeObserver(update);
    observer.observe(textarea);

    update();
}

initMultilineInput();
