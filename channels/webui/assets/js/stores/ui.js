/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
 * real rendered heights of lazy-mounted turns, keyed by the turn object
 * (which mergeTurnHistory keeps identity-stable). lives outside the alpine
 * store on purpose: no reactivity needed on it, and it keeps the proxy
 * from ever wrapping the WeakMap.
 */
const _turnHeights = new WeakMap();

UI_STORE = {
    scrollThreshold: 50,
    errors: [],
    currentModal: null,
    notice: null,

    shouldScroll: true,
    scrollToTurnIndex: null,

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:25)
     * bottom-detection suppression for smooth streaming autoscroll: while
     * our own smooth animation is in flight, the intermediate positions
     * would otherwise flip shouldScroll off and stall the follow. when the
     * animation settles (including when the user hijacks it mid-flight -
     * scrollend fires wherever they land) the resting position is
     * re-evaluated. falls back to instant for reduced motion.
     */
    _suppressScroll: false,
    _suppressTimer: null,

    _updateShouldScroll(el) {
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        this.shouldScroll = distFromBottom < this.scrollThreshold;
    },

    _smoothScrollToBottom(el) {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            el.scrollTop = el.scrollHeight;
            return;
        }

        this._suppressScroll = true;
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });

        const settle = () => {
            this._suppressScroll = false;
            el.removeEventListener('scrollend', settle);
            // evaluate the resting position: covers both a natural finish at
            // the bottom AND a user interrupting the animation with their
            // wheel/touch (scrollend fires wherever they stopped)
            this._updateShouldScroll(el);
        };

        el.addEventListener('scrollend', settle);

        // scrollend isn't universally supported; timeout as a safety net
        clearTimeout(this._suppressTimer);
        this._suppressTimer = setTimeout(settle, 500);
    },

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
     * lazy-mount scroll stability:
     * - _turnHeights remembers the real rendered height of a turn so its
     *   placeholder is exact when it remounts (WeakMap keyed by the turn
     *   object, which mergeTurnHistory keeps identity-stable).
     * - adjustScroll() manually compensates scrollTop when a turn's height
     *   changes above the viewport, replacing chrome's scroll anchoring
     *   (disabled via overflow-anchor: none), which fights user scroll and
     *   causes the "skipping past messages" jump.
     */
    captureTurnHeight(turn, el) {
        _turnHeights.set(turn, el.offsetHeight);
    },

    turnPlaceholderHeight(turn) {
        const cached = _turnHeights.get(turn);
        if (cached) return cached;

        // rough first-visit estimate; adjustScroll() compensates the error
        const chars = (turn.messages || []).reduce(
            (n, m) => n + (typeof m.content === 'string' ? m.content.length : 200), 0
        );
        return Math.min(400, Math.max(40, Math.round(chars / 6)));
    },

    async adjustScroll(el, toggle) {
        const container = document.getElementById('messages');

        const prev = el.offsetHeight;
        const above = container
            ? el.getBoundingClientRect().top <= container.getBoundingClientRect().top + 1
            : false;

        toggle();

        await Alpine.nextTick();

        if (container && above) {
            const delta = el.offsetHeight - prev;
            // instant: a smooth-animated compensation would visibly drift
            if (delta) container.scrollTo({ top: container.scrollTop + delta, behavior: 'instant' });
        }
    },

    windowWidth: window.innerWidth,
    isMobile: false,

    showSidebar: true,

    expandReasoning: true,

    async init() {
        // check if this is a phone
        this.windowWidth = window.innerWidth;
        this.isMobile = window.innerWidth <= 768;

        // hide sidebar on mobile (in favor of a hamburger button)
        this.showSidebar = !this.isMobile;

        this.expandReasoning = localStorage.getItem("expandReasoning") !== 'false';
    },

    async toggleSidebar() {
        this.showSidebar = !this.showSidebar;
    },

    async openModal(name) {
        if (this.currentModal === 'settings') {
            // auto-save the settings when switching to a different modal
            await Alpine.store('settings').saveSettings();
        }

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

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:25)
        // ignore the intermediate positions of our own smooth autoscroll;
        // the resting position is evaluated when the animation settles.
        if (this._suppressScroll) return;

        this._updateShouldScroll(el);
    },

    async scrollToBottom(containerId = 'messages') {
        if (!this.shouldScroll) return;

        const el = document.getElementById(containerId);
        if (!el) return;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:25)
        // smooth glide for the streaming follow; each incoming token
        // retargets the in-flight animation, so it reads as one continuous
        // drift instead of a jump per token
        Alpine.nextTick(() => {
            this._smoothScrollToBottom(el);
        });
    },

    async forceScrollToBottom(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        this.shouldScroll = true;

        /*
         * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
         * lazy-mounted turns change scrollHeight asynchronously: the
         * intersectionobserver only mounts placeholders into real dom a
         * frame *after* we scroll, so a single nextTick scroll lands above
         * the true bottom. iterate (scroll -> wait a frame -> check if the
         * height changed) until it settles, so mounting near the bottom is
         * always followed by another scroll to the new bottom.
         * aborts if the user grabs the scrollbar mid-flight.
         */
        let lastHeight = -1;
        for (let i = 0; i < 24; i++) {
            await Alpine.nextTick();
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
            // scrollTo with behavior:'instant' overrides the global
            // scroll-behavior:smooth. with smooth, each jump animated through
            // the whole chat and the lazy-mount zone mounted everything along
            // the way down. instant jumps land at the bottom directly.
            el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
            await new Promise(resolve => requestAnimationFrame(resolve));

            if (!this.shouldScroll) break;
            if (el.scrollHeight === lastHeight) break;
            lastHeight = el.scrollHeight;
        }
    },

    async scrollToTurn(turnIndex) {
        if (turnIndex === null || turnIndex === undefined) return;

        /*
         * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
         * the turn wrapper always exists but its contents may be an
         * unmounted placeholder, which grows into real dom once it nears
         * the viewport - so re-center iteratively until the scroll
         * position settles instead of centering once on a fake height.
         */
        const container = document.getElementById('messages');
        if (!container) return;

        let lastTop = -1;
        for (let i = 0; i < 24; i++) {
            await Alpine.nextTick();

            const el = document.querySelector(`[data-turn-index="${turnIndex}"]`);
            if (!el) { break; }

            const containerRect = container.getBoundingClientRect();
            const elementRect = el.getBoundingClientRect();
            const offset = elementRect.top - containerRect.top - (containerRect.height / 2) + (elementRect.height / 2);
            // instant jump: smooth would sweep the lazy-mount zone through
            // every turn between here and the target
            container.scrollTo({ top: container.scrollTop + offset, behavior: 'instant' });

            await new Promise(resolve => requestAnimationFrame(resolve));
            if (container.scrollTop === lastTop) break;
            lastTop = container.scrollTop;
        }

        this.scrollToTurnIndex = null;
    }
}
