// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// full rewrite: arrays always render as index->value rows (never inline
// [a, b] previews), objects as nested key/value rows; adds the missing
// toolResponseRenderer (content field first, keyless, full width).

function isStructured(v) {
    return v !== null && typeof v === 'object';
}

function valueCell(value, depth) {
    // structured values render their own nested rows (no scroll box);
    // scalars get the capped scroll cell with the x-box treatment
    if (isStructured(value)) {
        return `<div class="value">${toolResultsRenderer(value, depth + 1)}</div>`;
    }
    return `<div class="value" x-box x-auto-scroll>${toolResultsRenderer(value, depth + 1)}</div>`;
}

function toolResultsRenderer(data, depth = 0) {
    if (data === null) return '<span class="null">null</span>';
    if (typeof data === 'string') return `<span class="string">${escapeHtml(data)}</span>`;
    if (typeof data === 'number') return `<span class="scalar number">${data}</span>`;
    if (typeof data === 'boolean') return `<span class="scalar boolean">${data}</span>`;
    if (data === '') return '<span class="empty">empty</span>';

    if (Array.isArray(data)) {
        if (data.length === 0) return '<span class="empty">empty</span>';
        const maxItems = depth === 0 ? 12 : 8;
        const visible = data.slice(0, maxItems);
        const remaining = data.length - maxItems;
        let html = `<div class="array-rows${depth > 0 ? ' nested' : ''}">`;
        visible.forEach((item, i) => {
            html += `<div class="kv-row"><span class="key index">${i}</span>${valueCell(item, depth)}</div>`;
        });
        if (remaining > 0) html += `<span class="truncated">+ ${remaining} more</span>`;
        html += `</div>`;
        return html;
    }

    if (typeof data === 'object') {
        const entries = Object.entries(data);
        if (entries.length === 0) return '<span class="empty">empty</span>';
        const maxKeys = depth === 0 ? 12 : 8;
        const visible = entries.slice(0, maxKeys);
        const remaining = entries.length - maxKeys;
        let html = `<div class="kv-rows${depth > 0 ? ' nested' : ''}">`;
        visible.forEach(([key, value]) => {
            html += `<div class="kv-row"><span class="key">${escapeHtml(key)}</span>${valueCell(value, depth)}</div>`;
        });
        if (remaining > 0) html += `<span class="truncated">+ ${remaining} more keys</span>`;
        html += `</div>`;
        return html;
    }

    return `<span class="scalar">${escapeHtml(String(data))}</span>`;
}

function toolResponseRenderer(parsed) {
    if (!isStructured(parsed) || Array.isArray(parsed)) return toolResultsRenderer(parsed);

    let html = '';
    if ('content' in parsed) {
        const c = parsed.content;
        if (isStructured(c)) {
            // object/array content: plain top-level rows, keyless
            html += toolResultsRenderer(c, 0);
        } else {
            html += `<div class="content-row"><div class="value" x-box x-auto-scroll>${toolResultsRenderer(c, 1)}</div></div>`;
        }
    }
    const rest = { ...parsed };
    delete rest.content;
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // wrap the remaining fields so css can draw a hairline between
    // the content block and the rest of the response
    if (Object.keys(rest).length > 0) {
        const sep = 'content' in parsed ? ' response-rest' : '';
        html += `<div class="${sep.trim()}">${toolResultsRenderer(rest, 0)}</div>`;
    }
    return html;
}
