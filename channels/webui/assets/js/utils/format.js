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

    // hour12: false forces 24-hour time regardless of locale
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

    const today = new Date();
    if (localDayKey(date) === localDayKey(today)) return time;

    // -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: (2026-10-02)
    // day labels mirror day_label_from_key in channels/webui.py (the
    // sidebar's vocabulary): Yesterday, weekday name within the past
    // week, then 'October 26' / 'October 26, 2025'. en-US is pinned so
    // the labels match the backend's English strings exactly.
    const startOfDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const diffDays = Math.round((startOfToday - startOfDay) / 86400000);

    if (diffDays === 1) return `Yesterday ${time}`;
    if (diffDays > 1 && diffDays < 7) {
        return `${date.toLocaleDateString('en-US', { weekday: 'long' })} ${time}`;
    }
    if (date.getFullYear() === today.getFullYear()) {
        return `${date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })} ${time}`;
    }
    return `${date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })} ${time}`;
}



