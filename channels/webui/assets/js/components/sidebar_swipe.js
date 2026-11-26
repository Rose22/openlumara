/*
 * mobile edge-swipe for the sidebar: a rightward drag starting near the
 * left screen edge opens it, a leftward drag starting near the right edge
 * closes it. commit requires either dragging past 1/3 of the screen or
 * releasing with a horizontal flick (>0.45 px/ms over the newest stretch).
 * vertical scrolls and diagonal flukes are never hijacked (1.2x horizontal
 * dominance required before the gesture locks).
 *
 * the OS reserves roughly the first 20-24px of each screen edge for its own
 * back gesture, and touches starting in that strip get stolen (we receive a
 * touchcancel). the grab band therefore reaches well INSIDE the strip: a
 * swipe starting a finger's-width from the edge still reads as an edge
 * swipe, but the OS leaves it to us.
 */
(function () {
    var EDGE_ZONE = 96;
    var TRIP = 8;
    var FLICK_V = 0.45;

    var g = null;

    function isMobile() {
        try { return Alpine.store('ui').isMobile === true; } catch (e) { return false; }
    }

    function isOpen() {
        try { return Alpine.store('ui').showSidebar === true; } catch (e) { return false; }
    }

    function setOpen(open) {
        try { Alpine.store('ui').showSidebar = open; } catch (e) {}
    }

    // never hijack a swipe meant for a genuinely horizontally-scrollable area
    // (code blocks, the coder editor) sitting inside the edge band
    function inHScroller(node) {
        for (var el = node; el && el !== document.body; el = el.parentElement) {
            if (el.scrollWidth - el.clientWidth > 4 &&
                /(auto|scroll)/.test(getComputedStyle(el).overflowX)) return true;
        }
        return false;
    }

    document.addEventListener('touchstart', function (e) {
        g = null;
        var t = e.touches && e.touches[0];
        if (!t || !isMobile()) return;

        var dir = 0;
        if (t.clientX <= EDGE_ZONE && !isOpen()) dir = 1;
        else if (t.clientX >= window.innerWidth - EDGE_ZONE && isOpen()) dir = -1;
        if (!dir) return;
        if (dir > 0 && t.target && t.target.closest && t.target.closest('#sidebar')) return;
        if (inHScroller(t.target)) return;

        g = { dir: dir, sx: t.clientX, sy: t.clientY,
              lx: t.clientX, lt: e.timeStamp, vx: 0 };
    }, { passive: true });

    document.addEventListener('touchmove', function (e) {
        if (!g) return;
        var t = e.touches && e.touches[0];
        if (!t) return;

        var dx = t.clientX - g.sx, dy = t.clientY - g.sy;

        if (dy > 8 && dy > Math.abs(dx)) { g = null; return; }
        if (Math.abs(dx) < TRIP || Math.abs(dx) < Math.abs(dy) * 1.2) return;

        var dt = e.timeStamp - g.lt;
        if (dt > 0) {
            g.vx = (t.clientX - g.lx) / dt;
            g.lx = t.clientX;
            g.lt = e.timeStamp;
        }
    }, { passive: true });

    function finish() {
        if (!g) return;
        var dx = (g.lx - g.sx);
        var commit = g.dir > 0
            ? (dx > window.innerWidth / 3 || g.vx >= FLICK_V)
            : (dx < -window.innerWidth / 3 || g.vx <= -FLICK_V);

        if (commit) setOpen(g.dir > 0);
        g = null;
    }

    document.addEventListener('touchend', finish);
    document.addEventListener('touchcancel', function () { g = null; });
})();
