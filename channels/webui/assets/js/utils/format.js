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

/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
   relative-day helpers for the sidebar date grouping. parsing mirrors
   formatDate (naive timestamps are treated as UTC), but grouping and
   labelling happen in the user's local calendar day. day keys are
   local 'YYYY-MM-DD' strings, matching the /api/chats/days endpoint. */
const _dayWeekdayFmt = new Intl.DateTimeFormat('en', { weekday: 'long' });
const _dayMonthDayFmt = new Intl.DateTimeFormat('en', { month: 'long', day: 'numeric' });
const _dayFullFmt = new Intl.DateTimeFormat('en', { month: 'long', day: 'numeric', year: 'numeric' });
const _monthFmt = new Intl.DateTimeFormat('en', { month: 'long' });
const _monthYearFmt = new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric' });

function parseChatDate(dateString) {
    if (!dateString) { return null; }

    const cleanDate = dateString.endsWith('Z') || dateString.endsWith('+00:00')
        ? dateString
        : dateString + 'Z';

    const date = new Date(cleanDate);
    return isNaN(date.getTime()) ? null : date;
}

function localDayKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function dayKeyOf(dateString) {
    const date = parseChatDate(dateString);
    return date ? localDayKey(date) : '';
}

function startOfDayMs(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

// relative day label, no clock time: Today / Yesterday / weekday name
// for the past week / 'September 12' (year appended when not this year)
function dayLabelFromKey(key) {
    if (!key) { return 'Undated'; }

    // parsed as LOCAL midnight (component ctor), unlike new Date('YYYY-MM-DD')
    // which would parse as UTC and shift the day
    const parts = key.split('-').map(Number);
    const date = new Date(parts[0], parts[1] - 1, parts[2] ?? 1);
    if (isNaN(date.getTime())) { return 'Undated'; }

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // month group keys are 'YYYY-MM' (everything older than the past
    // week, mirroring the backend's grouping cutoff)
    if (parts.length === 2) {
        const monthFmt = date.getFullYear() === new Date().getFullYear()
            ? _monthFmt : _monthYearFmt;
        return monthFmt.format(date);
    }

    const diffDays = Math.round((startOfDayMs(new Date()) - startOfDayMs(date)) / 86400000);

    if (diffDays === 0) { return 'Today'; }
    if (diffDays === 1) { return 'Yesterday'; }
    if (diffDays > 1 && diffDays < 7) { return _dayWeekdayFmt.format(date); }
    if (date.getFullYear() === new Date().getFullYear()) { return _dayMonthDayFmt.format(date); }

    return _dayFullFmt.format(date);
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// client-side mirror of the backend's grouping cutoff: the past week
// (incl. today) groups by day ('YYYY-MM-DD'), older chats by month
// ('YYYY-MM'). used for search results, which are grouped in the
// browser; the backend applies the same rule for the day list.
function groupKeyOf(dateString) {
    const date = parseChatDate(dateString);
    if (!date) { return ''; }

    const diffDays = Math.round((startOfDayMs(new Date()) - startOfDayMs(date)) / 86400000);
    if (diffDays < 7) { return localDayKey(date); }

    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function dayLabelOf(dateString) {
    return dayLabelFromKey(dayKeyOf(dateString));
}

function formatLabel(key) {
    if (typeof key !== 'string') return key;
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

