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
    showCategories: true,
    showChatList: true,

    expandReasoning: true,

    async init() {
        // check if this is a phone
        this.windowWidth = window.innerWidth;
        this.isMobile = window.innerWidth <= 768;

        // hide sidebar on mobile (in favor of a hamburger button)
        this.showSidebar = !this.isMobile;

        // on mobile, the sidebar is a drill-down navigator rather than a two-column pane
        this.showCategories = !this.isMobile;
        this.showChatList = true;

        this.expandReasoning = localStorage.getItem("expandReasoning") !== 'false';
    },

    async toggleSidebar() {
        this.showSidebar = !this.showSidebar;
    },
    async toggleCategories() {
        this.showCategories = !this.showCategories;
    },
    async toggleChatList() {
        this.showChatList = !this.showChatList;
    },

    async toggleMobileSidebarView() {
        // toggles between the chatlist and the categories list
        if (this.showChatList) {
            this.showChatList = false;
            this.showCategories = true;
        } else {
            this.showChatList = true;
            this.showCategories = false;
        }
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

        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        const wasAtBottom = this.shouldScroll;

        if (distFromBottom < this.scrollThreshold) {
            this.shouldScroll = true;
        } else {
            this.shouldScroll = false;
        }
    },

    async scrollToBottom(containerId = 'messages') {
        if (!this.shouldScroll) return;

        const el = document.getElementById(containerId);
        if (!el) return;

        Alpine.nextTick(() => {
            el.scrollTop = el.scrollHeight;
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
