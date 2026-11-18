/*
 * mobile edge-swipe for the sidebar: a rightward drag starting against the
 * left screen edge opens it, a leftward drag starting at the right edge
 * closes it. commit requires either dragging past 1/3 of the screen or
 * releasing with a horizontal flick (>0.45 px/ms over the newest stretch).
 * vertical scrolls and diagonal flukes are never hijacked (1.2x horizontal
 * dominance required before the gesture locks).
 */
(function () {
    var EDGE_ZONE = 28;
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

    document.addEventListener('touchstart', function (e) {
        g = null;
        var t = e.touches && e.touches[0];
        if (!t || !isMobile()) return;

        var dir = 0;
        if (t.clientX <= EDGE_ZONE && !isOpen()) dir = 1;
        else if (t.clientX >= window.innerWidth - EDGE_ZONE && isOpen()) dir = -1;
        if (!dir) return;
        if (dir > 0 && t.target && t.target.closest && t.target.closest('#sidebar')) return;

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
