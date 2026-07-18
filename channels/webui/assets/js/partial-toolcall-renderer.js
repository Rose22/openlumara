function partialToolcallRenderer(data, depth = 0) {
    /*
     * apparently HTML generation couldn't be avoided for this, and Alpine wasn't up to the task..
     * or at least so my AI said, but this is to be continued.
     * i hope i can replace this with a pure alpine HTML template at some point
     */

    if (data === null) return '<span class="null">null</span>';
    if (typeof data === 'string') return `<span class="string">${escapeHtml(data)}</span>`;
    if (typeof data === 'number') return `<span class="scalar number">${data}</span>`;
    if (typeof data === 'boolean') return `<span class="scalar boolean">${data}</span>`;

    if (Array.isArray(data)) {
        const maxItems = depth === 0 ? 8 : depth === 1 ? 6 : 4;
        const hasMore = data.length > maxItems;
        const visible = data.slice(0, maxItems);
        const remaining = data.length - maxItems;
        const depthClass = depth >= 2 ? ' depth-2' : depth === 1 ? ' depth-1' : '';
        const nestedClass = depth > 0 ? ' nested' : '';

        if (!hasMore) {
            const items = visible.map((item, i) =>
                (i > 0 ? ', ' : '') + partialToolcallRenderer(item, depth + 1)
            );
            return `<span class="preview-bracket">[</span> ${items.join('')} <span class="preview-bracket">]</span>`;
        }

        let html = `<div class="array-item${nestedClass.trim()}${depthClass.trim()}">`;
        visible.forEach((item, i) => {
            html += `<div class="array-item">`;
            html += `<span class="index">${i}</span>`;
            html += `<span class="value">${partialToolcallRenderer(item, depth + 1)}</span>`;
            html += `</div>`;
        });
        html += `<span class="truncated" onclick="showFullJsonModal(${JSON.stringify(data)}, 'Array[${data.length}]')" style="cursor:pointer;">+ ${remaining} more</span>`;
        html += `</div>`;
        return html;
    }

    if (typeof data === 'object') {
        const entries = Object.entries(data);
        const maxKeys = depth === 0 ? 10 : depth === 1 ? 8 : 5;
        const hasMore = entries.length > maxKeys;
        const visible = entries.slice(0, maxKeys);
        const remaining = entries.length - maxKeys;
        const depthClass = depth >= 2 ? ' depth-2' : depth === 1 ? ' depth-1' : '';
        const nestedClass = depth > 0 ? ' nested' : '';

        if (!hasMore) {
            const kvs = visible.map(([k, v]) =>
                `<div class="kv-row"><span class="key">${escapeHtml(k)}</span><span class="colon">: </span>${partialToolcallRenderer(v, depth + 1)}</div>`
            );
            return kvs.join('');
        }

        let html = `<div class="${nestedClass.trim()}${depthClass.trim()}">`;
        visible.forEach(([key, value]) => {
            html += `<div class="kv-row">`;
            html += `<span class="key">${escapeHtml(key)}</span>`;
            html += `<span class="colon">:</span>`;
            html += `<span class="value">${partialToolcallRenderer(value, depth + 1)}</span>`;
            html += `</div>`;
        });
        html += `<span class="truncated" onclick="showFullJsonModal(${JSON.stringify(data)}, 'Object[${entries.length} keys]')" style="cursor:pointer;">+ ${remaining} more keys</span>`;
        html += `</div>`;
        return html;
    }

    return `<span class="scalar">${escapeHtml(String(data))}</span>`;
}
