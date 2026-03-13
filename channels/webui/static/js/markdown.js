// =============================================================================
// Markdown Rendering
// =============================================================================

marked.setOptions({
    breaks: true,
    gfm: true
});

function renderMarkdown(text) {
    return marked.parse(text);
}

function highlightCode(element) {
    if (typeof hljs === 'undefined') return;

    element.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);

        const pre = block.parentElement;
        if (!pre.querySelector('.copy-btn')) {
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.textContent = 'Copy';
            btn.setAttribute('aria-label', 'Copy code');
            btn.onclick = () => {
                navigator.clipboard.writeText(block.textContent).then(() => {
                    btn.textContent = 'Copied!';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.textContent = 'Copy';
                        btn.classList.remove('copied');
                    }, 1500);
                });
            };
            pre.style.position = 'relative';
            pre.appendChild(btn);
        }
    });
}
