/*
 * --- formatting stuff
 */
// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// this used to create a throwaway <div> per call and round-trip through the
// parser. it's called recursively for every key/value of every tool result
// (tool_results.js) and for every raw-mode message, which made it a very
// hot allocator. a plain regex replacer is ~10x faster and allocation-free
// for the common already-escaped case.
const _escapeReplacements = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
};

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => _escapeReplacements[c]);
}

const _rtfCache = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function formatDate(dateString) {
    if (!dateString) return '';

    // Ensure UTC parsing by appending 'Z' if missing
    const cleanDate = dateString.endsWith('Z') || dateString.endsWith('+00:00')
        ? dateString
        : dateString + 'Z';

    const date = new Date(cleanDate);
    const now = new Date();
    const diffMs = date - now;

    if (Math.abs(diffMs) < 60000) return _rtfCache.format(0, 'second');
    if (Math.abs(diffMs) < 3600000) return _rtfCache.format(Math.round(diffMs / 60000), 'minute');
    if (Math.abs(diffMs) < 86400000) return _rtfCache.format(Math.round(diffMs / 3600000), 'hour');
    if (Math.abs(diffMs) < 604800000) return _rtfCache.format(Math.round(diffMs / 86400000), 'day');

    return date.toLocaleDateString();
}

function formatLabel(key) {
    if (typeof key !== 'string') return key;
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

