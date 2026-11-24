const _interruptBound = new WeakSet();

window.isMobileViewport = () =>
    window.innerWidth <= 768 ||
    (window.matchMedia('(orientation: portrait)').matches && window.innerWidth <= 1024);

// pure JS lerp pump knobs; see directives/autoscroll.js for the full story
window.AUTOSCROLL_DAMP ??= 0.1;
window.AUTOSCROLL_PUMP_MS ??= 0;

UI_STORE = {
    scrollThreshold: 50,
    errors: [],
    currentModal: null,
    notice: null,

    shouldScroll: true,
    showScrollButton: false,
    scrollToTurnIndex: null,

    toastMsg: null,
    _toastTimer: null,

    toast(msg, ms = 2000) {
        this.toastMsg = msg;
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { this.toastMsg = null; }, ms);
    },

    _suppressScroll: false,
    _pumpRaf: null,
    _pumpEl: null,
    _pumpLast: 0,

    _updateShouldScroll(el) {
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        this.shouldScroll = distFromBottom < this.scrollThreshold;

        this.showScrollButton = distFromBottom > Math.max(el.clientHeight * 0.75, 400);
    },

    _stopPump() {
        if (this._pumpRaf !== null) cancelAnimationFrame(this._pumpRaf);
        this._pumpRaf = null;
        this._suppressScroll = false;
    },

    // one hop of the pure JS lerp pump: move scrollTop directly, DAMP of
    // the remaining gap closer. dt-normalized so frame starvation cannot
    // decay the scroll speed (the flaw that crawled the old lerp on long
    // agentic chains). returns false once the bottom is reached.
    _lerpHop(dt) {
        const el = this._pumpEl;
        if (!el) return false;

        const bottom = el.scrollHeight - el.clientHeight;
        const remaining = bottom - el.scrollTop;

        if (remaining <= 1) {
            el.scrollTo({ top: bottom, behavior: 'instant' });
            this._stopPump();
            this._updateShouldScroll(el);
            return false;
        }

        el.scrollTo({ top: el.scrollTop + remaining * this._lerpDamp(dt), behavior: 'instant' });
        return true;
    },

    // DAMP is a per-hop fraction at a 60Hz reference; converting by actual
    // frame time keeps the on-screen speed identical at any refresh rate
    _lerpDamp(dt) {
        const base = window.AUTOSCROLL_DAMP;
        if (base >= 1) return 1;
        return 1 - Math.pow(1 - base, Math.min(dt, 100) / (1000 / 60));
    },

    _pumpStep(now) {
        // dt from the rAF timestamps: hop size adapts to whatever refresh
        // rate - or hiccup - the display throws at it (see _lerpDamp)
        const dt = now - this._pumpLast;
        if (dt >= window.AUTOSCROLL_PUMP_MS) {
            this._pumpLast = now;
            if (!this._lerpHop(dt)) {
                this._pumpRaf = null;
                return;
            }
        }
        this._pumpRaf = requestAnimationFrame((t) => this._pumpStep(t));
    },

    _pumpScrollToBottom(el) {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            this._stopPump();
            // instant: global scroll-behavior:smooth would animate this jump
            el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
            return;
        }

        if (!_interruptBound.has(el)) {
            _interruptBound.add(el);
            const stop = () => {
                this._stopPump();
                this._updateShouldScroll(el);
            };
            el.addEventListener('wheel', stop, { passive: true });
            el.addEventListener('touchstart', stop, { passive: true });
        }

        this._suppressScroll = true;
        this._pumpEl = el;

        if (this._pumpRaf === null) {
            // seed with the current time so the very first hop sees a real
            // frame-sized dt instead of "time since page load"
            this._pumpLast = performance.now();
            this._pumpRaf = requestAnimationFrame((t) => this._pumpStep(t));
        }
    },

    windowWidth: window.innerWidth,
    isMobile: false,

    showSidebar: true,

    sidebarCollapsed: false,

    sidebarWidth: parseInt(localStorage.getItem('sidebarWidth')) || 288,
    sidebarResizing: false,

    startSidebarResize(e) {
        if (this._sidebarDrag) {
            e.preventDefault();
            return;
        }

        e.preventDefault();
        this.sidebarResizing = true;

        const startX = e.clientX;
        const startWidth = this.sidebarWidth;
        const pointerId = e.pointerId;
        const target = e.currentTarget || e.target;

        try {
            target.setPointerCapture(pointerId);
        } catch (err) {}

        const onMove = (ev) => {
            if (ev.pointerId !== undefined && ev.pointerId !== pointerId) return;
            this.sidebarWidth = Math.min(560, Math.max(220, startWidth + ev.clientX - startX));
        };

        let ended = false;
        const onEnd = (ev) => {
            if (ev && ev.pointerId !== undefined && ev.pointerId !== pointerId) return;
            if (ended) return;

            ended = true;
            this.sidebarResizing = false;
            this._sidebarDrag = null;
            localStorage.setItem('sidebarWidth', String(this.sidebarWidth));

            window.removeEventListener('pointermove', onMove);
            window.removeEventListener('pointerup', onEnd);
            window.removeEventListener('pointercancel', onEnd);
            window.removeEventListener('blur', onEnd);
            if (target) target.removeEventListener('lostpointercapture', onEnd);

            try {
                if (target.hasPointerCapture(pointerId)) target.releasePointerCapture(pointerId);
            } catch (err) {}
        };

        this._sidebarDrag = { pointerId, cleanup: onEnd };

        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onEnd);
        window.addEventListener('pointercancel', onEnd);
        window.addEventListener('blur', onEnd);
        if (target) target.addEventListener('lostpointercapture', onEnd);
    },

    resetSidebarWidth() {
        if (this._sidebarDrag) this._sidebarDrag.cleanup();
        this.sidebarWidth = 288;
        localStorage.setItem('sidebarWidth', '288');
    },

    expandReasoning: true,
    _floatingInputObserver: null,

    observeFloatingInput() {
        const input = document.getElementById('input');
        if (!input) return;

        let lastHeight = -1;
        let first = true;

        const update = () => {
            const height = input.offsetHeight;
            if (height === lastHeight) return;

            lastHeight = height;
            document.documentElement.style.setProperty('--floating-input-height', `${height}px`);

            if (!first && this.shouldScroll) {
                this.forceScrollToBottom('messages');
            }

            first = false;
        };

        update();

        if (!this._floatingInputObserver) {
            this._floatingInputObserver = new ResizeObserver(update);
        }

        this._floatingInputObserver.observe(input);
    },

    applySidebarViewport() {
        if (this.isMobile) { this.showSidebar = false; return; }

        this.showSidebar = localStorage.getItem('showSidebar') !== 'false';
    },

    async init() {
        // check if this is a phone
        this.windowWidth = window.innerWidth;
        this.isMobile = window.isMobileViewport();

        this.applySidebarViewport();

        // restore the collapsed-sidebar preference (default: expanded)
        this.sidebarCollapsed = localStorage.getItem("sidebarCollapsed") === 'true';

        this.expandReasoning = localStorage.getItem("expandReasoning") !== 'false';

        this.observeFloatingInput();
    },

    sidebarTab: localStorage.getItem('sidebarTab') || '',

    setSidebarCollapsed(collapsed) {
        this.sidebarCollapsed = Boolean(collapsed);
        localStorage.setItem('sidebarCollapsed', String(this.sidebarCollapsed));
    },

    sidebarTabs() {
        return [...document.querySelectorAll('.sidebar-tab-list .sidebar-tab[data-tab]')]
            .map(b => b.dataset.tab);
    },

    setSidebarTab(tab) {
        if (this.sidebarTab !== tab) {
            this.sidebarTab = tab;
            localStorage.setItem('sidebarTab', tab);
        }

        if (this.sidebarCollapsed) this.setSidebarCollapsed(false);
    },

    saveSidebarVisibility() {
        if (!this.isMobile) localStorage.setItem('showSidebar', String(this.showSidebar));
    },

    showSidebarPanel() {
        if (this.showSidebar) return;

        this.showSidebar = true;
        this.saveSidebarVisibility();
    },

    cycleSidebarTab(direction) {
        const tabs = this.sidebarTabs();
        if (tabs.length < 2) { this.toast('No sidebar tabs to cycle through'); return; }

        this.showSidebarPanel();

        const idx = tabs.indexOf(this.sidebarTab);
        if (idx === -1) {
            this.setSidebarTab(direction < 0 ? tabs[tabs.length - 1] : tabs[0]);
            return;
        }

        this.setSidebarTab(tabs[(idx + direction + tabs.length) % tabs.length]);
    },

    async toggleSidebar() {
        if (this._sidebarDrag) this._sidebarDrag.cleanup();
        this.showSidebar = !this.showSidebar;
        this.saveSidebarVisibility();
    },

    settingsCategory: null,

    async openModal(name, category = null) {
        if (this.currentModal === 'settings' && name !== 'settings') {
            const settings = Alpine.store('settings');
            if (settings.hasChanges &&
                !confirm('You have unsaved settings changes. Open the other dialog without saving?')) {
                return;
            }
        }

        this.settingsCategory = (name === 'settings') ? category : null;
        this.currentModal = name;

        /*
         * post-open actions
         */

        if (name === 'logs') {
            // scroll down to the bottom
            await Alpine.nextTick();

            const el = document.getElementById('log-container');
            if (el) el.scrollTop = el.scrollHeight;
        }
    },
    async closeModal() {
        this.currentModal = null;
    },

    /*
     * Called from @scroll on the messages container.
     * Toggles shouldScroll based on whether the user is near the bottom.
     */
    onScroll(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        if (this._suppressScroll) return;

        this._updateShouldScroll(el);

        Alpine.store('chat').schedulePromptPinRecompute();
    },

    async _jumpToBottom(el) {
        this._stopPump();

        // land on the bottom immediately, then keep chasing it for as long
        // as the content above keeps growing (markdown/code finishing render)
        el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });

        let lastHeight = -1;
        for (let i = 0; i < 24; i++) {
            await Alpine.nextTick();
            el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
            await new Promise(resolve => requestAnimationFrame(resolve));

            if (!this.shouldScroll) break;
            if (el.scrollHeight === lastHeight) break;
            lastHeight = el.scrollHeight;
        }
    },

    async scrollToBottom(containerId = 'messages', instant = false) {
        if (!this.shouldScroll) return;

        const el = document.getElementById(containerId);
        if (!el) return;

        if (instant) {
            await this._jumpToBottom(el);
            return;
        }

        // pump for the streaming follow; tokens arriving mid-glide just
        // extend it since every hop re-reads the bottom
        Alpine.nextTick(() => {
            this._pumpScrollToBottom(el);
        });
    },

    async forceScrollToBottom(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        this.shouldScroll = true;
        this.showScrollButton = false;

        await this._jumpToBottom(el);
    },

    async scrollToTurn(turnIndex) {
        if (turnIndex === null || turnIndex === undefined) return;

        const container = document.getElementById('messages');
        if (!container) return;

        this._stopPump();

        let lastTop = -1;
        for (let i = 0; i < 24; i++) {
            await Alpine.nextTick();

            const el = document.querySelector(`[data-turn-index="${turnIndex}"]`);
            if (!el) { break; }

            const containerRect = container.getBoundingClientRect();
            const elementRect = el.getBoundingClientRect();
            const offset = elementRect.top - containerRect.top - (containerRect.height / 2) + (elementRect.height / 2);
            container.scrollTo({ top: container.scrollTop + offset, behavior: 'instant' });

            await new Promise(resolve => requestAnimationFrame(resolve));
            if (container.scrollTop === lastTop) break;
            lastTop = container.scrollTop;
        }

        this.scrollToTurnIndex = null;
    }
}
