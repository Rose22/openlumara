/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-11-11) harness:openlumara
   stable_diffusion :: {{sd|token}} inline generated-art.

   The generate_image tool returns a short tag like {{sd|ab12cd3}} instead of
   pushing the picture; this extension resolves those tags into real <img>s
   in EVERY chat (and inside adventure passages, where it reuses the adv-img
   frame styling). The token -> file mapping lives server-side in the image
   folder's filenames themselves, so tags keep working across restarts.
   A marked inline extension handles the complete tag (plus a partial form,
   so mid-stream braces never flash raw); anything rendered before its token
   is known gets a data-sd placeholder that sdFillImgs patches in once the
   map lands (boot + sd_new_image broadcasts + a refetch on unknown
   tokens - all events, no polling). Frames render with their true width
   and height from the manifest, so lazy loads never reflow the page. */
(function () {
    var SD_IMG_URLS = {};   // token -> {url, name, prompt, seed, date}
    var SD_GALLERY = [];    // newest-first array of the same entries (+ token)
    var SD_CATEGORIES = []; // category names, from the server's scan
    var fetching = false;
    var unknownSeen = {};   // token -> ts, for the debounced map refetch
    var SD_FRESH = "";      // token of a just-arrived image: it slides in

    function sdBuildGallery() {
        // newest first; manifest dates are 'YYYY-MM-DD HH:MM:SS', so a plain
        // string compare orders them. entries without a (manifest-less) date
        // sink to the bottom of the wall.
        var list = [];
        for (var token in SD_IMG_URLS) {
            var m = SD_IMG_URLS[token] || {};
            var row = { token: token };
            for (var k in m) row[k] = m[k];
            list.push(row);
        }
        list.sort(function (a, b) {
            var da = String(a.date || ""), db = String(b.date || "");
            if (da === db) return a.token < b.token ? -1 : 1;
            if (!da) return 1;
            if (!db) return -1;
            return da < db ? 1 : -1;
        });
        SD_GALLERY = list;
        // hand the fresh arrays to the gallery store (once Alpine exists):
        // swapping the references re-renders the wall and both dropdowns
        try {
            var st = window.Alpine && Alpine.store("sdgallery");
            if (st) {
                st.images = SD_GALLERY; st.categories = SD_CATEGORIES;
                // a live arrival wears the slide-in class for a beat
                if (SD_FRESH && SD_GALLERY.length && SD_GALLERY[0].token === SD_FRESH) {
                    st.freshToken = SD_FRESH;
                    (function (fresh) {
                        setTimeout(function () {
                            try {
                                var s = Alpine.store("sdgallery");
                                if (s.freshToken === fresh) s.freshToken = "";
                            } catch (e) { /* the show goes on */ }
                        }, 900);
                    })(SD_FRESH);
                }
                SD_FRESH = "";
            }
        } catch (e) { /* the show goes on */ }
    }

    function sdMeta(token) {
        return SD_IMG_URLS[String(token || "").trim().toLowerCase()] || null;
    }
    window.sdImgSrc = function (token) {
        var m = sdMeta(token);
        return m ? (m.url || "") : "";
    };
    window.sdImgName = function (token) {
        var m = sdMeta(token);
        if (!m) return "generated image";
        return m.name || m.prompt || "generated image";
    };

    function sdNoteUnknown(token) {
        // a token the (fresh) map does not hold: the map may simply predate
        // the generation - refetch, debounced across a whole passage
        var now = Date.now();
        if (unknownSeen[token] && now - unknownSeen[token] < 4000) return;
        unknownSeen[token] = now;
        setTimeout(sdLoadMap, 1200);
    }

    // fetching holds the in-flight promise (null when idle), so a gallery
    // refresh can await the fetch it triggered instead of racing it.
    function sdLoadMap() {
        if (fetching) return fetching;
        // simpleApiFetch is a core global that may not exist this early
        // (classic scripts run at parse time) - retry until it shows up.
        if (typeof simpleApiFetch !== "function") { setTimeout(sdLoadMap, 300); return Promise.resolve(); }
        fetching = simpleApiFetch("/api/ext/stable_diffusion/images")
            .then(function (d) {
                fetching = null;
                SD_IMG_URLS = (d && d.images) || {};
                SD_CATEGORIES = (d && d.categories) || [];
                sdBuildGallery();
                sdFillImgs();
            })
            .catch(function () { fetching = null; });
        return fetching;
    }

    /* patch every placeholder whose pixels are now known. mirrors the
       adventure module's advFillImgs approach. */
    function sdFillImgs() {
        var box = document.getElementById("messages");
        if (!box) return;
        var imgs = box.querySelectorAll("img.sd-img[data-sd]");
        var filled = 0;
        for (var i = 0; i < imgs.length; i++) {
            var el = imgs[i];
            var token = String(el.getAttribute("data-sd") || "");
            var m = sdMeta(token);
            if (!m) { sdNoteUnknown(token); continue; }
            el.setAttribute("src", m.url);
            el.removeAttribute("data-sd");
            if (m.name) el.setAttribute("alt", m.name);
            if (m.width && m.height && !el.getAttribute("width")) {
                // the render may predate the map: reserve the box now,
                // still before the lazy pixels arrive
                el.setAttribute("width", m.width);
                el.setAttribute("height", m.height);
            }
            var cap = el.parentNode && el.parentNode.querySelector(".sd-img-pending");
            if (cap) cap.remove();
            filled++;
        }
        // inside a campaign the ceremony may be holding this frame shut,
        // waiting for these pixels (advRevealImg's stalled -> resume path):
        // hand straight to the adventure scanner instead of its poll
        if (filled) {
            var advOn = false;
            try { advOn = !!(window.Alpine && Alpine.store("adv") && Alpine.store("adv").active); } catch (e) {}
            if (advOn && window.advScanNewImgs) { try { window.advScanNewImgs(); } catch (e) {} }
        }
    }
    window.sdFillImgs = sdFillImgs;

    /* -------------------------
     * marked inline extension
     * ------------------------- */
    // the current syntax is {{sd|token}}; the old {{sd:token}} form is still
    // accepted so passages written before the switch keep rendering.
    var SD_RE = /^\{\{sd[:|]([a-z0-9]{7})(?:\|([^{}]*))?\}\}/;
    // mid-type form: the token is still streaming in. matched so the
    // placeholder frame appears from the first character instead of raw
    // braces flashing past.
    var SD_PARTIAL_RE = /^\{\{sd[:|]([a-z0-9]{0,6})$/;

    function esc(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }

    function registerMarkedExtensions() {
        if (typeof window.marked === "undefined" || !window.marked.use) {
            setTimeout(registerMarkedExtensions, 250);
            return;
        }
        window.marked.use({ extensions: [{
            name: "sdImage",
            level: "inline",
            start: function (src) {
                var i = src.indexOf("{{sd|");
                var j = src.indexOf("{{sd:");   // legacy form
                if (i === -1) return j === -1 ? undefined : j;
                return j === -1 || i < j ? i : j;
            },
            tokenizer: function (src) {
                var m = SD_RE.exec(src);
                if (m) return { type: "sdImage", raw: m[0], token: m[1], side: m[2] || "" };
                m = SD_PARTIAL_RE.exec(src);
                if (m) return { type: "sdImage", raw: m[0], token: m[1], partial: true };
                return undefined;
            },
            renderer: function (token) {
                if (token.partial) return "";
                // the adv-img classes ride along always: inside a campaign
                // they dress the frame exactly like scene art and hand it to
                // the arrival ceremony (floats, the top-to-bottom wipe, the
                // insertion cue); outside one they're inert and sd's own
                // css styles the picture
                var cls = "sd-img-wrap adv-img-wrap";
                var imgCls = "sd-img adv-img";
                var side = String(token.side || "").trim().toLowerCase();
                if (side === "left" || side === "right") {
                    cls += " sd-img-" + side + " adv-img-" + side;
                }
                var label = esc(window.sdImgName(token.token));
                var meta = sdMeta(token.token);
                // the reserved box: width/height attrs give the img its
                // true aspect before a single pixel loads, so the lazy
                // fetch on scroll can no longer grow the frame from zero
                // and reflow the page
                var dims = (meta && meta.width && meta.height)
                    ? ' width="' + meta.width + '" height="' + meta.height + '"' : "";
                var src = meta ? (meta.url || "") : "";
                if (src) {
                    return '<span class="' + cls + '">' +
                        '<img class="' + imgCls + '" src="' + esc(src) + '" alt="' + label +
                        '" loading="lazy"' + dims + '></span>';
                }
                sdNoteUnknown(token.token);
                return '<span class="' + cls + '">' +
                    '<img class="' + imgCls + '" data-sd="' + esc(token.token) + '" alt="' + label +
                    '" loading="lazy"' + dims + '>' +
                    '<span class="sd-img-pending adv-img-pending">\u{1F5BC} ' + label + "</span></span>";
            }
        }] });
    }
    registerMarkedExtensions();

    /* -------------------------
     * live wiring: broadcast poke + observer + safety polls
     * ------------------------- */
    function wrapSocket() {
        if (typeof window.handleWebSocketMessage !== "function") {
            setTimeout(wrapSocket, 200);
            return;
        }
        if (window.handleWebSocketMessage.sdHooked) return;
        var orig = window.handleWebSocketMessage;
        window.handleWebSocketMessage = function (data) {
            try {
                if (data && data.type === "sd_new_image") {
                    if (data.token && data.meta) {
                        SD_IMG_URLS[data.token] = data.meta;
                        if (!SD_IMG_URLS[data.token].url)
                            SD_IMG_URLS[data.token].url =
                                "/ext-assets/stable_diffusion/gen/" + data.token + ".png";
                        // a brand-new category appears in the dropdowns now
                        var cat = data.meta.category;
                        if (cat && SD_CATEGORIES.indexOf(cat) === -1) SD_CATEGORIES.push(cat);
                        SD_FRESH = data.token; // this tile gets the slide-in
                        sdBuildGallery();   // the wall grows right away,
                    }                       // ahead of the map refetch
                    sdFillImgs();
                    sdLoadMap();
                }
                if (data && data.type === "sd_image_meta") {
                    // a name or category was edited: merge the decorated
                    // entry and let every open view repaint
                    if (data.token && data.meta) {
                        var nm = data.meta;
                        if (!nm.url)
                            nm.url = (SD_IMG_URLS[data.token] || {}).url ||
                                "/ext-assets/stable_diffusion/gen/" + data.token + ".png";
                        SD_IMG_URLS[data.token] = nm;
                        var nc = nm.category;
                        if (nc && SD_CATEGORIES.indexOf(nc) === -1) SD_CATEGORIES.push(nc);
                        sdBuildGallery();
                    }
                }
                if (data && data.type === "sd_image_gone") {
                    // an image was deleted: prune it from the wall, and if
                    // the lightbox is showing exactly that one, close it
                    if (data.token && SD_IMG_URLS[data.token]) {
                        delete SD_IMG_URLS[data.token];
                        sdBuildGallery();
                        try {
                            var ui = Alpine.store("ui");
                            if (ui.currentModal === "sd_gallery_image" &&
                                Alpine.store("sdgallery").selectedToken === data.token)
                                ui.closeModal();
                        } catch (e) { /* the show goes on */ }
                    }
                }
            } catch (e) { /* the show goes on */ }
            return orig.apply(this, arguments);
        };
        window.handleWebSocketMessage.sdHooked = true;
    }
    wrapSocket();

    /* -------------------------
     * float lift + paragraph clearing (plain chats)
     * a browser can only ever start a float on the line where its markup
     * sits, so a tag written mid-paragraph would drop the picture in
     * mid-air. this mirrors the adventure module's proven approach OUTSIDE
     * campaigns: lift each floated frame to the top of its host paragraph,
     * stamp the host and its container, and let the css clear every block
     * that follows. inside a campaign the adventure module's own lift
     * (advPlaceImgFloats) owns this work; we stay entirely out of it.
     * ------------------------- */
    // the root class, not the Alpine store, is the truth about being in a
    // game: it is applied on boot/reload and flipped exactly with the mode.
    // the store's `active` lags (it only refreshes on the heartbeat, which
    // polls while streaming) - gating on it let the lift stamp its clearing
    // classes into live passages during those windows.
    function advGameOn() {
        if (document.documentElement.classList.contains("adv-on")) return true;
        try { return !!(window.Alpine && Alpine.store("adv") && Alpine.store("adv").active); } catch (e) { return false; }
    }

    // inside a campaign the adventure module owns all float work: strip any
    // stamp our lift may have left behind during a detection window (its
    // `~ *` clear would rob the game's floated art of its side text)
    function sdHealGameStamps() {
        var box = document.getElementById("messages");
        if (!box) return;
        var hosts = box.querySelectorAll(".sd-float-host");
        if (!hosts.length) return;
        for (var i = 0; i < hosts.length; i++) {
            hosts[i].classList.remove("sd-float-host");
            if (hosts[i].parentElement) hosts[i].parentElement.classList.remove("sd-float-root");
        }
    }

    function sdLiftFloats() {
        var box = document.getElementById("messages");
        if (!box) return;
        if (advGameOn()) { sdHealGameStamps(); return; }
        var wraps = box.querySelectorAll(".sd-img-wrap.sd-img-left, .sd-img-wrap.sd-img-right");
        if (!wraps.length) return;
        /* one floated frame per paragraph, always (mirroring the adventure
           module's advPlaceImgFloats): two frames sharing a host would
           sandwich the prose between a left and a right float. a
           paragraph holding more than one is split: every frame past the
           first opens a fresh paragraph (same tag, same classes) that
           takes it and everything that followed in source, so each
           picture keeps its own stretch of prose and the clearing rules
           stack those sections one below the other. */
        var seenHosts = [];
        for (var s = 0; s < wraps.length; s++) {
            var h = wraps[s].parentElement;
            if (!h || seenHosts.indexOf(h) !== -1) continue;
            seenHosts.push(h);
            var kids = [];
            for (var c0 = h.firstChild; c0; c0 = c0.nextSibling) kids.push(c0);
            var frames = 0, cur = h;
            for (var s2 = 0; s2 < kids.length; s2++) {
                var nd = kids[s2];
                if (!(nd.nodeType === 1 && nd.classList && nd.classList.contains("sd-img-wrap") &&
                      (nd.classList.contains("sd-img-left") || nd.classList.contains("sd-img-right")))) continue;
                if (frames > 0) {
                    var np = document.createElement(h.tagName);
                    np.className = h.className.replace(/\s*\bsd-float-host\b/, "");
                    cur.parentNode.insertBefore(np, cur.nextSibling);
                    while (nd) { var nx = nd.nextSibling; np.appendChild(nd); nd = nx; }
                    cur = np;
                    frames = 0;
                }
                frames++;
            }
        }
        var hosts = [], groups = [];
        for (var i = 0; i < wraps.length; i++) {
            var p = wraps[i].parentElement;
            if (!p) continue;
            // a paragraph the adventure module already claimed belongs to
            // its lift and its clearing - never double-stamp it
            if (p.classList.contains("adv-float-host")) continue;
            var g = hosts.indexOf(p);
            if (g === -1) { g = hosts.length; hosts.push(p); groups.push([]); }
            groups[g].push(wraps[i]);
        }
        for (var q = 0; q < groups.length; q++) {
            var list = groups[q], host = hosts[q];
            // the slot the LAST floated frame belongs in: right before the
            // first piece of real content hugging the paragraph top (our
            // own lifted frames are not content, everything else is)
            var tail = null;
            for (var c = host.firstChild; c; c = c.nextSibling) {
                if (c.nodeType === 1 && c.classList && c.classList.contains("sd-img-wrap")) continue;
                tail = c;
                break;
            }
            // walk backwards so each frame lines up behind the one after
            // it: the stack at the top ends in the very source order
            for (var k = list.length - 1; k >= 0; k--) {
                var w = list[k];
                var slot = (k === list.length - 1) ? tail : list[k + 1];
                if (slot === null) {
                    if (w !== host.lastChild) host.appendChild(w);
                    continue;
                }
                if (w.nextSibling !== slot) host.insertBefore(w, slot);
            }
            // attribute writes on an already-stamped element are no-ops, so
            // the observer never echoes this pass
            host.classList.add("sd-float-host");
            if (host.parentElement) host.parentElement.classList.add("sd-float-root");
        }
    }

    // leaving a campaign: hand our floats back (old passages usually
    // re-render fresh anyway, this just keeps the handover clean) and let
    // the game's own lift take over for whatever renders next.
    function sdUnliftFloats() {
        var box = document.getElementById("messages");
        if (!box) return;
        var hosts = box.querySelectorAll(".sd-float-host");
        for (var i = 0; i < hosts.length; i++) {
            var host = hosts[i];
            host.classList.remove("sd-float-host");
            if (host.parentElement) host.parentElement.classList.remove("sd-float-root");
            var kids = host.children;
            for (var j = kids.length - 1; j >= 0; j--) {
                var el = kids[j];
                if (el.classList && el.classList.contains("sd-img-wrap") && el.nextSibling)
                    host.appendChild(el);
            }
        }
    }
    window.addEventListener("adv:state", function () {
        var d = (window.event && window.event.detail) || {};
        if (d.active) sdHealGameStamps();   // the game lifts and clears: only strip ours
        else { sdUnliftFloats(); scheduleLift(); }
    });

    var liftQueued = false;
    function scheduleLift() {
        if (liftQueued) return;
        liftQueued = true;
        requestAnimationFrame(function () {
            liftQueued = false;
            sdLiftFloats();
        });
    }

    var moPending = null;
    function boot(retries) {
        var messages = document.getElementById("messages");
        if (!messages) {
            if (retries > 0) setTimeout(function () { boot(retries - 1); }, 300);
            return;
        }
        new MutationObserver(function () {
            if (moPending) return;
            moPending = setTimeout(function () {
                moPending = null;
                sdFillImgs();
                scheduleLift();
            }, 80);
        }).observe(messages, { childList: true, subtree: true, characterData: true });
        sdLoadMap();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { boot(40); });
    } else {
        boot(40);
    }
    // no polling: everything is event-driven - the boot map load, the
    // sd_new_image broadcast, the messages MutationObserver (which also
    // drives the lift), and the debounced refetch for unknown tokens.

    /* -------------------------
     * gallery store: the sidebar tab and its lightbox modal share it
     * (registered on alpine:init, the house pattern - the store is a
     * guaranteed presence by the time any component first evaluates)
     * ------------------------- */
    // enable_gallery off: the head slot shipped window.SD_GALLERY_DISABLED.
    // the tab button is core-auto-discovered, so it gets pulled out of the
    // DOM right here - at parse time Alpine has not initialized yet, and
    // the tabbar's :has(.sidebar-tab.ext) rule then hides the whole strip
    // if the gallery was the only extension tab.
    if (window.SD_GALLERY_DISABLED) {
        var killGalleryTab = function (tries) {
            var tab = document.querySelector('.sidebar-tab[data-tab="stable_diffusion/gallery"]');
            if (tab) tab.remove();
            else if (tries > 0) setTimeout(function () { killGalleryTab(tries - 1); }, 150);
        };
        killGalleryTab(20);
    }

    function startStore() {
        Alpine.store("sdgallery", {
            images: SD_GALLERY,        // newest first, swapped by sdBuildGallery
            categories: SD_CATEGORIES, // for the form datalist + wall filter
            freshToken: "",            // just-arrived image: gets the slide-in
            loading: false,
            selectedToken: "",         // the image the modal is showing
            // the sidebar's manual generation form
            formPrompt: "",
            formNegative: "",
            formCategory: "",          // category for the next manual image
            formOrientation: "portrait", // tall or wide, toggled in the header
            toggleOrientation: function () {
                this.formOrientation =
                    this.formOrientation === "portrait" ? "landscape" : "portrait";
            },
            // header quick-setting: cycles the module's resolution tier
            resolution: "HD",
            resTiers: ["LOW", "SD", "HD", "QHD", "3K", "4K"],
            loadResolution: async function () {
                try {
                    var r = await simpleApiFetch("/api/ext/stable_diffusion/resolution");
                    if (r && r.resolution) this.resolution = r.resolution;
                } catch (e) {}
            },
            cycleResolution: async function () {
                var i = this.resTiers.indexOf(this.resolution);
                var next = this.resTiers[(i + 1) % this.resTiers.length];
                try {
                    var r = await simpleApiPost("/api/ext/stable_diffusion/resolution_set",
                        { tier: next });
                    if (r && r.resolution) this.resolution = r.resolution;
                } catch (e) {
                    this.noteOk = false;
                    this.note = String((e && (e.data || e.message)) || e || "could not set resolution");
                }
            },
            wallFilter: "all",         // wall modal's category filter
            busy: false,
            fromWall: false,           // the lightbox was opened from the wall
            wallScroll: 0,             // wall scroll, saved for the back trip
            note: "",                  // last error / cancelled message
            noteOk: false,             // note is informational, not an error
            // lightbox metadata editing: name and category only - the
            // generation recipe stays the engraved, un-editable truth
            editOpen: false,
            editSaving: false,
            editName: "",
            editCategory: "",
            editErr: "",
            refresh: async function () {
                this.loading = true;
                try { await sdLoadMap(); } catch (e) {}
                this.loading = false;
            },
            syncBusy: async function () {
                // a reloaded page cannot know a generation is mid-flight:
                // ask the server whenever the wall is revealed
                try {
                    var st = await simpleApiFetch("/api/ext/stable_diffusion/generate_status");
                    this.busy = !!(st && st.running);
                } catch (e) {}
            },
            generate: async function () {
                if (this.busy) return;
                if (!String(this.formPrompt).trim()) {
                    this.noteOk = false;
                    this.note = "write a prompt first ✍️";
                    return;
                }
                this.busy = true;
                this.note = "";
                try {
                    var res = await simpleApiPost("/api/ext/stable_diffusion/generate", {
                        prompt: this.formPrompt,
                        negative_prompt: this.formNegative,
                        category: this.formCategory,
                        orientation: this.formOrientation
                    });
                    if (res && res.cancelled) {
                        this.noteOk = true;
                        this.note = "generation cancelled.";
                    } else {
                        // no success note: the sd_new_image broadcast already
                        // grew the wall, so the picture speaks for itself
                        this.noteOk = true;
                        this.note = "";
                    }
                } catch (e) {
                    this.noteOk = false;
                    this.note = String((e && (e.data || e.message)) || e || "generation failed");
                }
                this.busy = false;
            },
            cancel: async function () {
                // just the poke: the pending generate() await resolves with
                // the cancellation and clears busy there
                try { await simpleApiPost("/api/ext/stable_diffusion/generate_cancel", {}); } catch (e) {}
            },
            updateFade: function (el) {
                // edge fades for the wall, but only when it reads as a
                // single column: with two or more columns abreast the
                // scroll already has a visible shape and the masks would
                // just eat into the pictures
                if (!el) return;
                var tracks = getComputedStyle(el).gridTemplateColumns;
                var cols = tracks ? tracks.split(" ").filter(Boolean).length : 1;
                var single = cols <= 1;
                el.classList.toggle("fade-top", single && el.scrollTop > 1);
                el.classList.toggle("fade-bottom", single &&
                    el.scrollTop + el.clientHeight < el.scrollHeight - 1);
            },
            open: function (token) {
                // sidebar tiles open the lightbox on its own
                this.fromWall = false;
                this.editOpen = false;
                this.selectedToken = String(token || "");
                Alpine.store("ui").openModal("sd_gallery_image");
            },
            openFromWall: function (token) {
                // same lightbox, but its back button returns to the wall
                this.fromWall = true;
                this.editOpen = false;
                this.selectedToken = String(token || "");
                Alpine.store("ui").openModal("sd_gallery_image");
            },
            openWall: function () {
                // a fresh open starts unfiltered at the top; the back
                // trip from the lightbox restores position instead
                this.wallScroll = 0;
                this.wallFilter = "all";
                this.setWallCols();
                Alpine.store("ui").openModal("sd_gallery_wall");
            },
            wallCols: 4,
            setWallCols: function () {
                // the column count lives in JS (the tiles are bucketed per
                // column): phones get a real 3-column wall instead of one
                // endless stack, and only wide screens earn the fourth
                var w = window.innerWidth;
                this.wallCols = w <= 1280 ? 3 : 4;
            },
            wallColumns: function () {
                // newest-first, row-major: each tile (in date order) is dealt
                // into the currently shortest column, so the latest pictures
                // line up along the top row - plain CSS columns read
                // top-to-bottom and bury second-to-newest deep in column one
                var n = this.wallCols || 4;
                var cols = [], heights = [], i;
                for (i = 0; i < n; i++) { cols.push([]); heights.push(0); }
                var imgs = this.wallImages();
                for (i = 0; i < imgs.length; i++) {
                    var m = imgs[i], best = 0;
                    for (var c = 1; c < n; c++) if (heights[c] < heights[best]) best = c;
                    cols[best].push(m);
                    heights[best] += (m.width && m.height) ? m.height / m.width : 0.667;
                }
                return cols;
            },
            wallImages: function () {
                // the wall's tiles, narrowed by the category dropdown.
                // images predating the category field count as 'general'
                if (!this.wallFilter || this.wallFilter === "all") return this.images;
                var f = String(this.wallFilter).toLowerCase();
                return this.images.filter(function (m) {
                    return String(m.category || "general").toLowerCase() === f;
                });
            },
            leaveLightbox: function () {
                // back (or Esc) from a wall-opened lightbox: the wall
                // template remounts and restores the saved scroll itself
                if (this.fromWall) Alpine.store("ui").openModal("sd_gallery_wall");
                else Alpine.store("ui").closeModal();
            },
            openChat: function (id) {
                Alpine.store("ui").closeModal();
                Alpine.store("chat").loadChat(String(id));
            },
            close: function () { Alpine.store("ui").closeModal(); },
            startEdit: function () {
                var m = this.selected();
                if (!m) return;
                this.editName = String(m.name || "");
                this.editCategory = String(m.category || "general");
                this.editErr = "";
                this.editOpen = true;
            },
            deleteImage: async function () {
                var m = this.selected();
                if (!m) return;
                // the browser's own gate: no accidental picture deaths
                if (!window.confirm("Delete \"" + (m.name || m.token) +
                    "\" for good? This cannot be undone.")) return;
                try {
                    await simpleApiPost("/api/ext/stable_diffusion/delete_image", {
                        token: this.selectedToken
                    });
                    // the sd_image_gone broadcast prunes the wall and closes
                    // this lightbox all by itself
                } catch (e) {
                    window.alert(String((e && (e.data || e.message)) || e || "could not delete"));
                }
            },
            saveEdit: async function () {
                var t = this.selectedToken;
                if (!t || this.editSaving) return;
                this.editSaving = true;
                this.editErr = "";
                try {
                    await simpleApiPost("/api/ext/stable_diffusion/meta_update", {
                        token: t,
                        name: this.editName,
                        category: this.editCategory
                    });
                    // the sd_image_meta broadcast repaints modal, wall and
                    // dropdowns live; a filtered wall may drop the tile now
                    this.editOpen = false;
                } catch (e) {
                    this.editErr = String((e && (e.data || e.message)) || e || "could not save");
                }
                this.editSaving = false;
            },
            selected: function () {
                var t = String(this.selectedToken || "");
                for (var i = 0; i < this.images.length; i++)
                    if (this.images[i].token === t) return this.images[i];
                return null;
            },
            excerpt: function (img, n) {
                // the hover caption's one-line prompt excerpt: collapsed
                // whitespace, hard-cut with '...' well before the CSS
                // ellipsis ever needs to kick in
                var p = String((img && (img.prompt || img.name)) || (img && img.token) || "");
                p = p.replace(/\s+/g, " ").trim();
                n = n || 110;
                return p.length > n ? p.slice(0, n).replace(/\s+$/, "") + "..." : p;
            },
            metaRows: function () {
                // the modal's metadata column: one {k, v} row per field
                // this image actually carries, in a fixed reading order
                var m = this.selected();
                if (!m) return [];
                var rows = [];
                function add(k, v) {
                    if (v !== undefined && v !== null && String(v).trim() !== "")
                        rows.push({ k: k, v: String(v) });
                }
                add("name", m.name);
                add("category", m.category);
                add("negative prompt", m.negative_prompt);
                add("seed", m.seed);
                if (m.width && m.height) add("size", m.width + "\u00d7" + m.height);
                add("orientation", m.orientation);
                add("aspect ratio", m.aspect_ratio);
                add("cfg scale", m.cfg_scale);
                add("steps", m.steps);
                // only sidecar-era images carry the field at all; an empty
                // one means the server's own default sampler was used
                if (m.sampler !== undefined) add("sampler", String(m.sampler).trim() || "server default");
                add("backend", m.backend);
                // the chat this picture was born in: a row that loads it
                if (m.chat_id) rows.push({ k: "chat", v: String(m.chat_id), chat: true });
                add("date", m.date);
                add("token", m.token);
                return rows;
            }
        });
        // map may have landed while Alpine was still loading: resync, and
        // keep the store's reference on the very latest array
        sdBuildGallery();
        // keep the wall's bucket count matched to the viewport, and let
        // the sidebar's edge fades re-judge themselves at the new width
        var gst = Alpine.store("sdgallery");
        gst.setWallCols();
        window.addEventListener("resize", function () {
            gst.setWallCols();
            gst.updateFade(document.querySelector(".sd-gal-grid"));
        });
    }
    if (window.Alpine) startStore();
    else document.addEventListener("alpine:init", startStore);
})();
