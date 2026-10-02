function globalSearch() {
    return {
        query: '',
        results: [],
        loading: false,
        searchInContent: true,
        activeIndex: -1,
        debounceTimer: null,

        init() {
            this.query = '';
            this.results = [];
            this.activeIndex = -1;
            this.loading = false;
            this.searchInContent = true;
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
            // the modal is x-if now, so it can unmount before this fires:
            // guard the lookup and keep the timer handle so destroy() can
            // clear it.
            this.focusTimer = setTimeout(() => {
                const input = document.getElementById("global-search-input");
                if (input) input.focus();
            }, 50);
        },

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // alpine calls destroy() on x-if teardown: cancel the pending
        // debounce/focus timers so a search can't resolve against an
        // unmounted component.
        destroy() {
            clearTimeout(this.debounceTimer);
            clearTimeout(this.focusTimer);
        },

        async search() {
            clearTimeout(this.debounceTimer);
            const q = this.query.trim();

            if (!q) {
                this.results = [];
                this.loading = false;
                return;
            }

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-02)
            // clear stale results and show loading immediately, then
            // debounce the actual API call.
            this.results = [];
            this.activeIndex = -1;
            this.loading = true;

            this.debounceTimer = setTimeout(async () => {
                const results = await Alpine.store('chat').searchGlobal(q, this.searchInContent, null, [], 'relevance');
                // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-02)
                // discard in-flight responses for a query the user has
                // since typed over, so slow responses can't clobber
                // fresher results.
                if (this.query.trim() !== q) return;
                this.results = results;
                this.loading = false;
                this.activeIndex = -1;
            }, 150);
        },

        selectResult(chatId) {
            Alpine.store('chat').loadChatFromSearch(chatId);
        },

        navigateResults(direction) {
            if (this.results.length === 0) return;
            this.activeIndex = Math.max(0, Math.min(
                this.activeIndex + direction,
                this.results.length - 1
            ));

            // Scroll the active result into view
            this.$nextTick(() => {
                const activeEl = this.$el.querySelector('.global-search-result.active');
                if (activeEl) {
                    activeEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            });
        },

        async enterResult() {
            if (this.results.length === 0) return;
            const idx = this.activeIndex >= 0 ? this.activeIndex : 0;
            // bugfix: results are chat objects (id at top level), not
            // wrappers - the .chat.id lookup was always undefined, so
            // hitting Enter on a selected result never opened anything
            await this.selectResult(this.results[idx]?.id);
        }
    }
}
