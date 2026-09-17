/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
 * real rendered heights of lazy-mounted turns, keyed by the turn object
 * (which mergeTurnHistory keeps identity-stable). lives outside the alpine
 * store on purpose: no reactivity needed on it, and it keeps the proxy
 * from ever wrapping the WeakMap.
 */
const _turnHeights = new WeakMap();

/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
 * per-element lerp-chase state (active rAF id) and a marker for elements
 * whose user-input interrupt listeners are already wired up
 */
const _chases = new WeakMap();
const _interruptBound = new WeakSet();

UI_STORE = {
    scrollThreshold: 50,
    errors: [],
    currentModal: null,
    notice: null,

    shouldScroll: true,
    scrollToTurnIndex: null,

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
     * lerp-chase streaming autoscroll: instead of native smooth scroll (no
     * speed control), each animation frame moves scrollTop a fraction of the
     * remaining distance toward the bottom. the target is re-read every
     * frame, so tokens arriving mid-chase are folded into the same glide.
     * scrollFollowSpeed is the knob: 0.2 = glidey, 0.5 = snappy, 1 = instant.
     * while a chase is in flight its intermediate positions are suppressed
     * from bottom-detection (they would flip shouldScroll off and stall the
     * follow); a real wheel/touch cancels the chase and resumes tracking.
     */
    scrollFollowSpeed: 0.2,
    _suppressScroll: false,

    _updateShouldScroll(el) {
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        this.shouldScroll = distFromBottom < this.scrollThreshold;
    },

    _stopChase(el) {
        const chase = _chases.get(el);
        if (!chase) return;
        if (chase.raf) cancelAnimationFrame(chase.raf);
        _chases.delete(el);
        this._suppressScroll = false;
    },

    _chaseScrollToBottom(el) {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            this._stopChase(el);
            el.scrollTop = el.scrollHeight;
            return;
        }

        let chase = _chases.get(el);
        if (!chase) {
            chase = { raf: null };
            _chases.set(el, chase);
            this._suppressScroll = true;

            // user input wins: give up the chase and let onScroll track
            // their real position again. bound once per element.
            if (!_interruptBound.has(el)) {
                _interruptBound.add(el);
                const stop = () => {
                    this._stopChase(el);
                    this._updateShouldScroll(el);
                };
                el.addEventListener('wheel', stop, { passive: true });
                el.addEventListener('touchstart', stop, { passive: true });
            }
        }

        if (chase.raf) return; // already chasing; the step re-reads the target

        const step = () => {
            const target = el.scrollHeight - el.clientHeight;
            const remaining = target - el.scrollTop;
            if (Math.abs(remaining) < 1) {
                el.scrollTop = target;
                this._stopChase(el);
                this._updateShouldScroll(el);
                return;
            }
            el.scrollTop += remaining * this.scrollFollowSpeed;
            chase.raf = requestAnimationFrame(step);
        };
        chase.raf = requestAnimationFrame(step);
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

        // lerp chase for the streaming follow; tokens arriving mid-chase
        // just extend the glide since the target is re-read every frame
        Alpine.nextTick(() => {
            this._chaseScrollToBottom(el);
        });
    },

    async forceScrollToBottom(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
        // cancel an in-flight chase so its per-frame writes don't fight
        // the instant jumps below
        this._stopChase(el);

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

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
        // a running chase would fight the re-centering loop below
        this._stopChase(container);

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
