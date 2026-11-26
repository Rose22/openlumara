/* -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: 2026-11-26 harness:openlumara */
/*
 * Marks the input wrapper as multiline when the textarea is taller than the
 * default single-line input height.
 */
function initMultilineInput() {
    const wrapper = document.querySelector('.input-wrapper');
    const textarea = wrapper?.querySelector('#user-input');
    if (!wrapper || !textarea) return;

    const update = () => wrapper.classList.toggle('is-multiline', textarea.offsetHeight > 56);
    const observer = new ResizeObserver(update);

    observer.observe(textarea);
    update();
}

initMultilineInput();
