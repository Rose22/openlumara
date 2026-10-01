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

/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
   the sidebar date-grouping mirror (groupKeyOf/dayLabelFromKey and
   friends) is gone: the backend stamps group_key/group_label onto day
   listings and search results, so there's nothing to keep in sync here.
   localDayKey stays: it's purely client-side (which local day is
   "today" for the expand-by-default rule). */
function localDayKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function formatLabel(key) {
    if (typeof key !== 'string') return key;
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-02)
   timestamp label for message turns: reads the epoch seconds stamped by
   core/messages.py add() onto _metadata.timestamp. shows just the clock
   time for today, and prepends the date on older turns. */
function formatMessageTimestamp(turn) {
    const messages = turn && turn.messages ? turn.messages : [];
    const ts = (messages[0]?._metadata ?? {}).timestamp;
    if (!ts) return '';

    const date = new Date(ts * 1000);
    if (isNaN(date.getTime())) return '';

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-02)
    // hour12: false forces 24-hour time regardless of locale
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    const isToday = localDayKey(date) === localDayKey(new Date());
    const label = isToday ? time : `${date.toLocaleDateString()} ${time}`;
    return label;
}



