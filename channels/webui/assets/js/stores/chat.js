/*
 * splices a freshly fetched page of turns into the loaded window.
 */
function mergeTurnPage(existing, existingStart, incoming, incomingStart) {
    incoming = incoming || [];
    existing = existing || [];

    if (existing.length === 0) return incoming;

    const keptPrefix = existing.slice(0, Math.max(0, Math.min(existing.length, incomingStart - existingStart)));

    const merged = incoming.map((turn, i) => {
        const prev = existing[i + incomingStart - existingStart];
        return (prev && prev.hash && prev.hash === turn.hash) ? prev : turn;
    });

    const result = keptPrefix.concat(merged);

    // exactly one live turn may exist, always as the tail: a mid-stream
    // reload used to leave a stale copy behind (often at the head of the
    // window), rendering a duplicate agent chain inside an older message
    const liveTails = existing.filter(t => t && t.live === true);
    const live = liveTails.length > 0 ? liveTails[liveTails.length - 1] : null;

    for (let i = result.length - 1; i >= 0; i--) {
        if (result[i] && result[i].live === true) result.splice(i, 1);
    }

    if (live) {
        let lastUser = -1;
        for (let i = result.length - 1; i >= 0; i--) {
            if (result[i].role === 'user') { lastUser = i; break; }
        }

        if (lastUser !== -1) result.length = lastUser + 1;
        result.push(live);
    }

    return result;
}

function parseStoredTags() {
    try {
        const parsed = JSON.parse(localStorage.getItem('sidebarTagFilter') || '[]');
        return Array.isArray(parsed) ? parsed.filter(t => typeof t === 'string') : [];
    } catch (err) {
        return [];
    }
}

CHAT_STORE = {
    /*
     * alpine.js store for chat state
     */

    dayGroups: [],
    chatLimit: 10,
    dayFetchGen: 0,

    moveChatTarget: null,

    categories: [],
    chat: {},
    selectedChat: null,
    selectedCategory: 'general',

    turnHistory: [],
    turnStart: 0,
    totalTurns: 0,
    hasMoreOlder: false,
    loadingOlder: false,
    turnPageSize: 5,
    olderTriggerPx: 300,
    olderPrefetchPx: 600,
    _olderIntersecting: false,
    _unloadQueued: false,
    _lastUnloadAt: 0,

    editingMessageIndex: null,
    editContent: '',

    /*
     * the user turn currently pinned to the top of the message view.
     * updated from the flow markers in chat/index.html via x-prompt-marker:
     * a turn pins itself once it scrolls out through the top edge, and
     * unpins the moment it scrolls back into view. switching is event-driven
     * (fires only on intersection changes), never per-frame.
     */
    pinnedTurnIndex: null,
    pinnedPromptHeight: 0,

    // a turn that just unpinned keeps its height reserve for the duration of
    // the grow animation, so removing it can't make the turn snap to one
    // line and then grow back (a collapse-then-grow jolt).
    releasingTurnIndex: null,
    _releaseTimer: null,

    /*
     * is any user turn currently overlapping the messages viewport? measured
     * via the pin markers, which always track the turn's true flow position:
     * a pinned turn is sticky, so its own bounding rect always reports it as
     * visible. the turn keeps its full flow height while pinned (the min-height
     * reserve), so marker top + turn offsetHeight is its true flow bottom.
     */
    // the strip of the scrollbox hidden behind the floating chat header
    // (window.css runs #messages under it; --header-height fed by init.js)
    headerInset(container) {
        return parseFloat(getComputedStyle(container).getPropertyValue('--header-height')) || 0;
    },

    userPromptInView(container) {
        const rect = container.getBoundingClientRect();
        const visibleTop = rect.top + this.headerInset(container);

        for (const marker of container.querySelectorAll('.pin-marker')) {
            const turnEl = marker.nextElementSibling;
            if (!turnEl || !turnEl.matches('.turn')) continue;
            if (!turnEl.querySelector(':scope > .message-wrapper.user')) continue;

            const flowTop = marker.getBoundingClientRect().top;
            if (flowTop < rect.bottom && flowTop + turnEl.offsetHeight > visibleTop) return true;
        }

        return false;
    },

    updatePromptPin(turnIndex, intersecting, marker) {
        if (intersecting) {
            if (this.pinnedTurnIndex !== turnIndex) return;

            this.pinnedTurnIndex = null;
            this.releasingTurnIndex = turnIndex;

            clearTimeout(this._releaseTimer);
            this._releaseTimer = setTimeout(() => {
                if (this.releasingTurnIndex === turnIndex) this.releasingTurnIndex = null;
            }, 350);
            return;
        }

        if (!this.pinnedPromptsEnabled()) return;

        // leaving, but which way? only pin prompts that left through the
        // TOP edge - a marker leaving through the bottom means we scrolled
        // up to older messages, where pinning would be wrong.
        const container = document.getElementById('messages');
        if (!container) return;

        // the visible top edge is the header's bottom, not the scrollport's
        if (marker.getBoundingClientRect().top > container.getBoundingClientRect().top + this.headerInset(container)) return;

        // the pin only exists to keep context visible while the chat window
        // shows no user prompt of its own
        if (this.userPromptInView(container)) return;

        /*
         * a prompt can only take the pin if it's NEWER than the current one.
         * every marker reports its initial intersection on its own schedule
         * (on load, and again when older pages get prepended), so "last
         * callback wins" would let an older prompt steal the pin - turn
         * index is what decides, not callback order.
         */
        if (this.pinnedTurnIndex !== null && turnIndex <= this.pinnedTurnIndex) return;

        const turnEl = container.querySelector(`[data-turn-index="${turnIndex}"]`);
        if (!turnEl || turnEl.querySelector('.editing')) return;

        const wrapper = turnEl.querySelector(':scope > .message-wrapper.user');
        if (!wrapper) return;

        // reserve the full height BEFORE the class is applied so collapsing
        // the bubble to a single line doesn't yank the response upward
        this.pinnedPromptHeight = wrapper.offsetHeight;
        this.pinnedTurnIndex = turnIndex;
    },

    pinnedPromptsEnabled() {
        return localStorage.getItem('pinnedPromptsEnabled') !== 'false';
    },

    // grow the pinned prompt back open, then drop the pin entirely
    clearPromptPin() {
        if (this.pinnedTurnIndex === null) return;

        const releasing = this.pinnedTurnIndex;
        this.pinnedTurnIndex = null;
        this.releasingTurnIndex = releasing;

        clearTimeout(this._releaseTimer);
        this._releaseTimer = setTimeout(() => {
            if (this.releasingTurnIndex === releasing) this.releasingTurnIndex = null;
        }, 350);
    },

    /*
     * throttled entry point from ui.onScroll (itself throttled at 100ms),
     * coalesced into one frame. pure measurement, so it stays correct even
     * when no marker ever reported the position change.
     */
    schedulePromptPinRecompute() {
        if (this._pinRecomputeQueued) return;

        this._pinRecomputeQueued = true;
        requestAnimationFrame(() => {
            this._pinRecomputeQueued = false;
            this.recomputePromptPin();
        });
    },

    /*
     * resolves the pin by measuring every marker at once: the pin belongs to
     * the NEWEST user turn that sits above the top edge. needed because
     * IntersectionObserver only reports state CHANGES: on load the chat is
     * rendered at the top and then jumped to the bottom, during which only
     * markers near the top fire (pinning an older prompt), while markers
     * that were below the fold and are now above it never report anything.
     * called after anchored loads (see anchorToBottom), not per-frame.
     */
    recomputePromptPin() {
        const container = document.getElementById('messages');
        if (!container) return;

        // the pin only shows while no user prompt is in view at all; once
        // any real prompt is on screen the sticky duplicate is redundant
        if (!this.pinnedPromptsEnabled() || this.userPromptInView(container)) {
            this.clearPromptPin();
            return;
        }

        // pin boundary is the header's bottom edge (the scrollport's top
        // hides behind the floating header - see headerInset)
        const top = container.getBoundingClientRect().top + this.headerInset(container);

        let activeIndex = null;
        let activeWrapper = null;

        for (const marker of container.querySelectorAll('.pin-marker')) {
            if (marker.getBoundingClientRect().top > top) continue;

            // the turn is the marker's next sibling. do NOT bind an index
            // attribute onto the marker itself: a reactive attribute on the
            // same element as x-prompt-marker makes Alpine re-run the
            // directive and respawn its observer on every update.
            const turnEl = marker.nextElementSibling;
            if (!turnEl || !turnEl.matches('.turn') || turnEl.querySelector('.editing')) continue;

            const idx = Number(turnEl.dataset.turnIndex);

            const wrapper = turnEl.querySelector(':scope > .message-wrapper.user');
            if (!wrapper) continue;

            activeIndex = idx;
            activeWrapper = wrapper;
        }

        if (activeIndex === this.pinnedTurnIndex) return;

        if (this.pinnedTurnIndex !== null) {
            const releasing = this.pinnedTurnIndex;
            this.releasingTurnIndex = releasing;

            clearTimeout(this._releaseTimer);
            this._releaseTimer = setTimeout(() => {
                if (this.releasingTurnIndex === releasing) this.releasingTurnIndex = null;
            }, 350);
        }

        if (activeIndex === null) {
            this.pinnedTurnIndex = null;
            return;
        }

        this.pinnedPromptHeight = activeWrapper.offsetHeight;
        this.pinnedTurnIndex = activeIndex;
    },

    user_input: '',
    last_user_input: '',

    inputHistory: JSON.parse(localStorage.getItem('input_history') || '[]'),
    historyIndex: -1,
    draftValue: '',

    async loadInputHistory() {
        try {
            const saved = await simpleApiFetch('/api/input_history');
            if (Array.isArray(saved)) {
                this.inputHistory = saved;
                localStorage.setItem('input_history', JSON.stringify(saved));
            }
        } catch (err) {
            console.warn('loading input history failed:', err);
        }
    },

    pushInputHistory(msg) {
        msg = (msg || '').trim();
        if (!msg) return;
        if (this.inputHistory[this.inputHistory.length - 1] !== msg) {
            this.inputHistory.push(msg);
            if (this.inputHistory.length > 100) this.inputHistory.shift();
            localStorage.setItem('input_history', JSON.stringify(this.inputHistory));
            // fire-and-forget: the backend is the source of truth now
            simpleApiPost('/api/input_history', { message: msg }).catch(() => {});
        }
        this.historyIndex = -1;
        this.draftValue = '';
    },

    historyPrev() {
        if (!this.inputHistory.length) return;
        if (this.historyIndex === -1) {
            this.draftValue = this.user_input;
            this.historyIndex = this.inputHistory.length - 1;
        } else if (this.historyIndex > 0) {
            this.historyIndex--;
        }
        this.user_input = this.inputHistory[this.historyIndex];
    },

    historyNext() {
        if (this.historyIndex === -1) return;
        if (this.historyIndex < this.inputHistory.length - 1) {
            this.historyIndex++;
            this.user_input = this.inputHistory[this.historyIndex];
        } else {
            this.historyIndex = -1;
            this.user_input = this.draftValue;
            this.draftValue = '';
        }
    },

    currentTokenUsage: 0,

    contextBreakdown: null,

    /* ----------------------
     * turn pagination
     * ----------------------- */
    turnAt(absIndex) {
        return this.turnHistory[absIndex - this.turnStart];
    },

    resetWindow() {
        this.turnHistory = [];
        this.turnStart = 0;
        this.totalTurns = 0;
        this.hasMoreOlder = false;
        this.loadingOlder = false;
        this.pinnedTurnIndex = null;
        this.pinnedPromptHeight = 0;
        this._olderIntersecting = false;
        this._unloadQueued = false;
        this._lastUnloadAt = 0;
    },

    windowSize() {
        const last = this.turnHistory[this.turnHistory.length - 1];
        const loaded = this.turnHistory.length - (last && last.live === true ? 1 : 0);
        return Math.max(this.turnPageSize, loaded);
    },

    applyTurnPage(result, merge) {
        const incoming = result.turn_history ?? [];
        const page = result.turn_page ?? {};
        const start = typeof page.start === 'number' ? page.start : Math.max(0, incoming.length - this.turnPageSize);
        const total = typeof page.total === 'number' ? page.total : start + incoming.length;

        if (merge) {
            const keptPrefix = this.turnHistory.length > 0 && this.turnStart < start;
            this.turnHistory = mergeTurnPage(this.turnHistory, this.turnStart, incoming, start);
            if (!keptPrefix) this.turnStart = start;
        } else {
            this.turnHistory = incoming;
            this.turnStart = start;
        }

        this.totalTurns = total;
        this.hasMoreOlder = this.turnStart > 0;
    },

    async loadOlderTurns() {
        if (this.loadingOlder || !this.hasMoreOlder) return;

        this.loadingOlder = true;

        try {
            const result = await simpleApiFetch(
                `/api/chat/turns?before=${this.turnStart}&limit=${this.turnPageSize}`
            );
            if (!result) return;

            const turns = result.turns ?? [];
            if (turns.length === 0) {
                this.hasMoreOlder = false;
                return;
            }

            // pure prepend: native scroll anchoring keeps the viewport exactly
            // where it is while older content appears above it. this requires
            // #messages to NOT set overflow-anchor: none (see chat/window.css);
            // any manual scrollTop correction layered on top would double-move
            // and reintroduce the jump.
            this.turnHistory = turns.concat(this.turnHistory);
            this.turnStart = result.start;
            this.totalTurns = result.total;
            this.hasMoreOlder = result.start > 0;
        } catch (err) {
            console.warn('loading older turns failed:', err);
        } finally {
            this.loadingOlder = false;
        }
    },

    async resyncWindow() {
        if (this.turnHistory.length === 0) {
            await this.reloadChat();
            return;
        }

        const size = Math.min(this.windowSize(), 200);
        const result = await simpleApiFetch(
            `/api/chat/turns?before=${this.turnStart + size}&limit=${size}`
        );
        if (!result) return;

        const turns = result.turns ?? [];
        const keepCount = Math.max(0, Math.min(this.turnHistory.length, result.start - this.turnStart));

        this.turnHistory = this.turnHistory.slice(0, keepCount).concat(turns);
        if (keepCount === 0) this.turnStart = result.start;
        this.totalTurns = result.total;
        this.hasMoreOlder = this.turnStart > 0;
    },

    loadOlderTurnsFromIntersect() {
        this._olderIntersecting = true;
        this._fillOlderWhileIntersecting();
    },

    olderTurnsLeftIntersect() {
        this._olderIntersecting = false;
    },

    async _fillOlderWhileIntersecting() {
        while (this._olderIntersecting && this.hasMoreOlder) {
            const sinceUnload = performance.now() - this._lastUnloadAt;

            if (sinceUnload < 300) {
                await new Promise(resolve => setTimeout(resolve, 300 - sinceUnload + 1));
                if (!this._olderIntersecting) return;
                continue;
            }

            if (this.loadingOlder) {
                await Alpine.nextTick();
                continue;
            }

            await this.loadOlderTurns();
            await Alpine.nextTick();
            await new Promise(resolve => requestAnimationFrame(resolve));
        }
    },

    scheduleUnloadCheck() {
        if (this._unloadQueued) return;
        this._unloadQueued = true;
        requestAnimationFrame(() => {
            this._unloadQueued = false;
            this._runUnloadCheck();
        });
    },

    _runUnloadCheck() {
        const messages = document.getElementById('messages');
        if (!messages || messages.classList.contains('anchor-hidden')) return;
        if (this.loadingOlder) return;
        if (this.turnHistory.length <= this.turnPageSize) return;

        const turnEls = [...messages.querySelectorAll('#messages > .turn-block .turn')];
        if (turnEls.length < 2) return;

        // keep a cushion above the viewport top so unloading never drags
        // the older-turns loader back into its prefetch margin
        const keepAbove = Math.max(this.olderTriggerPx * 2 + 200, 600);
        const cutLine = messages.getBoundingClientRect().top - keepAbove;

        let maxDrop = this.turnHistory.length - this.turnPageSize;
        if (this.turnHistory[this.turnHistory.length - 1]?.live === true) {
            maxDrop = Math.min(maxDrop, this.turnHistory.length - 1);
        }

        // never unload past the newest user turn: it owns the response that
        // may be filling the viewport below it, and the pinned-prompt feature
        // needs its marker in the DOM long after it scrolled out the top
        let lastUser = -1;
        for (let i = this.turnHistory.length - 1; i >= 0; i--) {
            if (this.turnHistory[i]?.role === 'user') { lastUser = i; break; }
        }
        if (lastUser !== -1) maxDrop = Math.min(maxDrop, lastUser);

        const viewTop = messages.getBoundingClientRect().top + this.headerInset(messages);

        let drop = 0;
        for (let t = 0; t < turnEls.length; t++) {
            if (drop >= maxDrop) break;

            const turnEl = turnEls[t];
            const idx = Number(turnEl.dataset.turnIndex);
            if (!Number.isFinite(idx) || idx !== this.turnStart + drop) break;

            if (turnEl.getBoundingClientRect().bottom >= cutLine) break;

            // pin handover: a user turn must stay loaded until the next newer
            // user turn's flow position has crossed the viewport top (its
            // marker tracks the true position even while that turn is pinned
            // sticky). dropping it earlier leaves the response region above
            // with no prompt left to pin.
            if (turnEl.querySelector(':scope > .message-wrapper.user')) {
                const nextUser = turnEls.slice(t + 1).find(e => e.querySelector(':scope > .message-wrapper.user'));
                const nextMarker = nextUser ? nextUser.previousElementSibling : null;

                if (!nextMarker || nextMarker.getBoundingClientRect().top >= viewTop) break;
            }

            drop++;
        }
        if (drop <= 0) return;

        this._dropPrefixTurns(drop);
        this._lastUnloadAt = performance.now();

        // no scrollTop compensation needed: native scroll anchoring holds
        // the visual position while the prefix elements disappear
        Alpine.nextTick(() => {
            Alpine.store('ui')._updateShouldScroll(messages);
        });
    },

    _dropPrefixTurns(drop) {
        if (drop <= 0) return;

        if (this.pinnedTurnIndex !== null && this.pinnedTurnIndex - this.turnStart < drop) {
            this.clearPromptPin();
        }

        this.turnHistory = this.turnHistory.slice(drop);
        this.turnStart += drop;
        this.hasMoreOlder = this.turnStart > 0;
    },

    async fillViewport(maxPages = 8) {
        const el = document.getElementById('messages');
        if (!el) return;

        let pages = 0;
        while (this.hasMoreOlder && pages < maxPages && el.scrollHeight <= el.clientHeight + 8) {
            await this.loadOlderTurns();
            await Alpine.nextTick();
            pages++;
        }

        if (pages > 0 && Alpine.store('ui').shouldScroll) {
            el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
        }
    },

    async load() {
        // called by Alpine.init
        await this.reloadCategories();
        this.loadInputHistory();

        const result = await simpleApiFetch(`/api/chat/current?limit=${this.windowSize()}`);
        if (!result) { return }

        document.getElementById('messages')?.classList.add('anchor-hidden');

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;
        this.applyTurnPage(result, true);
        this.currentTokenUsage = result.token_usage;

        await this.reloadChats();

        // ensure the chat exists in the visible sidebar list before scrolling
        await this.ensureChatVisible(this.selectedChat);
    },

    /* ----------------------
     * chat manipulation
     * ----------------------- */
    /*
     * opens a chat at its end without ever showing the top of it first
     */
    async anchorToBottom() {
        const ui = Alpine.store('ui');
        const el = document.getElementById('messages');

        if (!el) {
            await ui.forceScrollToBottom();
            return;
        }

        el.classList.add('anchor-hidden');
        try {
            await Alpine.nextTick();
            await ui.forceScrollToBottom();
            await this.fillViewport();

            // markers that started below the fold never report their jump to
            // above the top edge (IO only fires on state changes, and their
            // state stayed 'not intersecting'), so resolve the pin by hand
            // once the anchored scroll has landed
            requestAnimationFrame(() => this.recomputePromptPin());
        } finally {
            el.classList.remove('anchor-hidden');
        }
    },

    async loadChat(chatId) {
        if (this.selectedChat === chatId) { return; }

        // don't allow chat switching if a stream is ongoing
        if (Alpine.store("stream").state != 'idle') { return; }

        const result = await simpleApiFetch(`/api/chat/load/${chatId}?limit=${this.turnPageSize}`);
        if (!result) { return; }

        this.resetWindow();
        this.chat = result;
        this.selectedChat = chatId;
        this.selectedCategory = result.category;
        this.applyTurnPage(result, false);
        this.currentTokenUsage = result.token_usage;

        await this.anchorToBottom();

        await this.ensureChatVisible(chatId);

        document.getElementById('user-input')?.focus();
    },

    /* ----------------------
     * sidebar search
     * ----------------------- */
    searchQuery: '',
    searchResults: [],
    searchLoading: false,
    searchDebounce: null,

    searchInContent: localStorage.getItem('sidebarSearchInContent') === 'true',

    get searching() { return Boolean(this.searchQuery.trim()); },

    /* ----------------------
     * tag filter (sidebar)
     * ----------------------- */
    selectedTags: parseStoredTags(),
    availableTags: [],

    tagParam() {
        return this.selectedTags.map(t => `&tags=${encodeURIComponent(t)}`).join('');
    },

    async loadTags() {
        const qs = this.catParam();
        const url = `/api/chats/tags${qs ? `?${qs.slice(1)}` : ''}`;

        let tags = null;
        try {
            tags = await simpleApiFetch(url);
        } catch (err) {
            console.warn('loading chat tags failed:', err);
            return;
        }

        this.availableTags = tags ?? [];

        // prune selections whose tag no longer exists in this category
        // (chat deleted, tag removed, or category switched) - silently,
        // no reload: the list refresh that follows picks it up anyway.
        const pruned = this.selectedTags.filter(t => this.availableTags.includes(t));
        if (pruned.length !== this.selectedTags.length) {
            this.selectedTags = pruned;
            localStorage.setItem('sidebarTagFilter', JSON.stringify(pruned));
        }
    },

    async toggleTag(tag) {
        if (this.selectedTags.includes(tag)) {
            this.selectedTags = this.selectedTags.filter(t => t !== tag);
        } else {
            this.selectedTags = [...this.selectedTags, tag];
        }
        localStorage.setItem('sidebarTagFilter', JSON.stringify(this.selectedTags));
        await this.reloadChats();
    },

    async clearTags() {
        if (this.selectedTags.length === 0) { return; }
        this.selectedTags = [];
        localStorage.setItem('sidebarTagFilter', '[]');
        await this.reloadChats();
    },

    /* ----------------------
     * day groups (sidebar)
     * ----------------------- */
    collapsedDays: {},

    tzOffset() {
        // JS getTimezoneOffset: minutes behind UTC (CEST -> -120)
        return new Date().getTimezoneOffset();
    },

    catParam() {
        return this.selectedCategory ? `&category=${encodeURIComponent(this.selectedCategory)}` : '';
    },

    todayKey() {
        return localDayKey(new Date());
    },

    /* ----------------------
     * time tabs (sidebar): Today / Week / Older.
     * ----------------------- */
    timeTab: localStorage.getItem('sidebarTimeTab') || 'today',

    setTimeTab(tab) {
        if (this.timeTab === tab) { return; }
        this.timeTab = tab;
        localStorage.setItem('sidebarTimeTab', tab);
    },

    groupTab(key) {
        if (!key || key === 'undated') { return 'older'; }
        if (key === this.todayKey()) { return 'today'; }
        if (key.startsWith('last-week-')) { return 'week'; }
        return key.split('-').length >= 3 ? 'week' : 'older';
    },

    // the x-for source in sidebar.html (search results bypass the tabs)
    visibleGroups() {
        if (this.searching) { return this.displayGroups(); }
        return this.dayGroups.filter(g => this.groupTab(g.key) === this.timeTab);
    },

    isGroupCollapsed(group) {
        // search results are always shown fully - hiding matches behind
        // a collapsed header would be maddening
        if (this.searching) { return false; }
        if (group.key in this.collapsedDays) { return Boolean(this.collapsedDays[group.key]); }
        // month groups on the Older tab start collapsed; day groups on
        // Today/Week stay expanded (their headers are hidden anyway)
        return this.groupTab(group.key) === 'older';
    },

    toggleDayGroup(group) {
        const collapse = !this.isGroupCollapsed(group);
        this.collapsedDays[group.key] = collapse;

        if (collapse) {
            group.chats = [];
            group.offset = 0;
            group.loaded = false;
            group.hasMore = group.count > 0;
        } else {
            Alpine.nextTick(() => this.ensureDayChatsFilled(group));
        }
    },

    async ensureDayChatsFilled(group, el) {
        while (true) {
            // the x-if may have (re)rendered the loader: re-resolve it
            if (!el || !el.isConnected) {
                el = document.querySelector(`[data-day-loader="${group.key}"]`);
            }
            if (!el || !el.isConnected) { break; }

            const container = el.closest('.chats');
            if (!container || !group.hasMore) { break; }

            // another call is fetching this group: wait for it
            if (group.loading) {
                await new Promise(resolve => setTimeout(resolve, 50));
                continue;
            }

            const rect = el.getBoundingClientRect();
            const crect = container.getBoundingClientRect();
            const visible = rect.top < crect.bottom && rect.bottom > crect.top;
            if (!visible) { break; }

            const progressed = await this.loadDayChats(group);
            if (!progressed) { break; }

            // let alpine render the new chats before re-measuring
            await Alpine.nextTick();
        }
    },

    // the x-for source in sidebar.html: day groups while browsing,
    // search results bucketed into groups while searching
    displayGroups() {
        if (!this.searching) { return this.dayGroups; }

        const groups = [];
        const byKey = {};

        for (const chat of this.searchResults) {
            const key = chat.group_key || 'undated';
            if (!(key in byKey)) {
                byKey[key] = { key: key, label: chat.group_label || 'Undated', chats: [] };
                groups.push(byKey[key]);
            }
            byKey[key].chats.push(chat);
        }

        return groups;
    },

    async reloadDayGroups() {
        const gen = ++this.dayFetchGen;

        // tagParam() narrows day counts to the active tag filter
        const groupList = await simpleApiFetch(
            `/api/chats/days?tz_offset=${this.tzOffset()}${this.catParam()}${this.tagParam()}`
        );

        // stale: a newer reload superseded this one
        if (gen !== this.dayFetchGen) { return; }

        this.dayGroups = (groupList ?? []).map(g => ({
            key: g.key,
            label: g.label,
            count: g.count,
            chats: [],
            offset: 0,
            hasMore: g.count > 0,
            loading: false,
            loaded: false
        }));

        const onTab = g => !this.isGroupCollapsed(g) && this.groupTab(g.key) === this.timeTab;

        await Promise.all(
            this.dayGroups.filter(onTab).map(g => this.loadDayChats(g))
        );

        await Alpine.nextTick();
        await Promise.all(
            this.dayGroups.filter(onTab).map(g => this.ensureDayChatsFilled(g))
        );
    },

    // loads one page of chats for a single day group. resolves to true
    // if progress was made, false if nothing more can load (already
    // loading / exhausted / failed / stale).
    async loadDayChats(group) {
        if (!group || group.loading || !group.hasMore) { return false; }

        group.loading = true;
        const gen = this.dayFetchGen;
        const before = group.chats.length;

        let result = null;
        try {
            result = await simpleApiFetch(
                `/api/chats/day?day=${group.key}&offset=${group.offset}` +
                `&limit=${this.chatLimit}&tz_offset=${this.tzOffset()}${this.catParam()}${this.tagParam()}`
            );
        } catch (err) {
            result = null;
        } finally {
            group.loading = false;
        }

        // stale (list reloaded mid-flight) or failed: mark exhausted so
        // loop callers can't spin; a reload rebuilds the group anyway.
        if (gen !== this.dayFetchGen || !this.dayGroups.includes(group)) { return false; }

        if (!result) { group.hasMore = false; return false; }

        group.chats.push(...result.messages);
        group.offset += result.messages.length;
        group.hasMore = result.has_more;
        group.loaded = true;

        return group.chats.length > before;
    },

    setSearchInContent(on) {
        this.searchInContent = Boolean(on);
        localStorage.setItem('sidebarSearchInContent', this.searchInContent);

        // re-run the active search so the mode switch applies immediately
        clearTimeout(this.searchDebounce);
        if (this.searching) {
            this.searchResults = [];
            this.searchLoading = true;
            this._runChatSearch(this.searchQuery.trim());
        }
    },

    setSearchQuery(q) {
        this.searchQuery = q;
        clearTimeout(this.searchDebounce);

        if (!q.trim()) {
            // back to pagination mode: visibleChats was frozen (not
            // mutated) during the search, so just switch back.
            this.searchResults = [];
            this.searchLoading = false;
            return;
        }

        this.searchResults = [];
        this.searchLoading = true;

        // debounce so we don't hit the backend on every keystroke
        this.searchDebounce = setTimeout(() => this._runChatSearch(q.trim()), 200);
    },

    async _runChatSearch(q) {
        this.searchLoading = true;
        const results = await this.searchGlobal(q, this.searchInContent, this.selectedCategory, this.selectedTags);

        // stale: query changed or was cleared while the request was in flight
        if (this.searchQuery.trim() !== q) { return; }

        this.searchResults = results;
        this.searchLoading = false;
    },

    async reloadChats() {
        await this.loadTags();
        await this.reloadDayGroups();

        // refresh search results alongside, so renames/deletes (which
        // reload the list) don't leave the search mode list stale.
        if (this.searching) { await this._runChatSearch(this.searchQuery.trim()); }
    },

    async ensureChatVisible(chatId) {
        for (const group of this.dayGroups) {
            if (group.chats.some(c => c.id === chatId)) {
                this.collapsedDays[group.key] = false;
                this.setTimeTab(this.groupTab(group.key));
                return true;
            }

            while (group.hasMore) {
                // a concurrent per-group loader fetch is in flight: wait
                // for it instead of treating 'false' as 'no progress'
                while (group.loading) {
                    await new Promise(resolve => setTimeout(resolve, 50));
                }

                const progressed = await this.loadDayChats(group);
                if (group.chats.some(c => c.id === chatId)) {
                    this.collapsedDays[group.key] = false;
                    this.setTimeTab(this.groupTab(group.key));
                    return true;
                }
                if (!progressed) { break; }
            }
        }

        return false;
    },

    async newChat(category = null, title = null, tags = []) {
        const body = { category: category ?? this.selectedCategory };
        if (title) { body.title = title; }
        if (tags && tags.length > 0) { body.tags = tags; }

        await simpleApiPost('/api/chat/new', body);

        result = await simpleApiFetch(`/api/chat/current?limit=${this.turnPageSize}`);
        if (!result) { return; }

        this.chat = result;

        this.selectedChat = result.id;
        this.selectedCategory = result.category;
        this.currentTokenUsage = result.token_usage;
        this.applyTurnPage(result, false);

        // the new chat may live in a category the dropdown doesn't list yet
        await this.reloadCategories();

        this.collapsedDays[this.todayKey()] = false;

        await this.reloadChats();
        await this.reloadChat();

        document.getElementById('user-input')?.focus();
    },

    async renameChat(chat_id, newTitle) {
        await simpleApiPost(`/api/chat/rename/${chat_id}`, {title: newTitle});

        // the header reads this.chat directly: keep it live so renaming the
        // open chat updates instantly instead of going stale until next load
        if (chat_id === this.selectedChat) { this.chat.title = newTitle; }

        await this.reloadChats();
    },

    async moveChat(chat_id, category) {
        await simpleApiPost(`/api/chat/set-category/${chat_id}`, { category: category });

        if (chat_id === this.selectedChat) {
            this.selectedCategory = category;
            await this.reloadChat();
        }

        await this.reloadCategories();
        await this.reloadChats();
    },

    async deleteChat(chat_id) {
        if (!confirm("Are you sure you want to delete this chat?")) { return }

        await simpleApiPost(`/api/chat/delete/${chat_id}`);

        await this.reloadCategories();

        const cats = this.categories ?? [];
        if (this.selectedCategory && !cats.includes(this.selectedCategory)) {
            this.selectedCategory = cats.includes('general')
                ? 'general'
                : (cats[0] ?? 'general');
        }

        await this.reloadChats();
    },

    async deleteCategory(name) {
        await simpleApiPost('/api/chats/categories/delete', { name: name });

        await this.reloadCategories();

        if (this.selectedCategory === name) {
            this.selectedCategory = 'general';
        }

        await this.reloadChats();
        await this.reloadChat();
    },

    async reloadChat() {
        stream = Alpine.store("stream");

        if (!this.selectedChat) {
            console.log("tried to reload the chat, but no chat is loaded!");
            return;
        }

        const result = await simpleApiFetch(`/api/chat/current?limit=${this.windowSize()}`);
        if (!result) { return }

        const prevCategory = this.selectedCategory;

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;

        this.applyTurnPage(result, true);

        if (result.category !== prevCategory) {
            await this.reloadCategories();
            await this.reloadChats();
            await this.ensureChatVisible(result.id);
        }
    },

    async reloadCategories() {
        this.categories = await simpleApiFetch('/api/chats/categories');
    },

    dropdownCategories() {
        let cats = [...(this.categories ?? [])];
        if (this.selectedCategory && !cats.includes(this.selectedCategory)) {
            cats.push(this.selectedCategory);
        }

        return cats;
    },

    dropdownValue() {
        void (this.categories ?? []).length;
        return this.selectedCategory;
    },

    async selectCategory(category) {
        // no-op when the dropdown fires a change back to the current value
        if (category === this.selectedCategory) { return; }

        this.selectedCategory = category;
        // reloadChats() re-runs the sidebar search when active, so the
        // results are already re-scoped to the new category after this
        await this.reloadChats();
    },

    async clearInput() {
        // store the last user input for use in things like placeholder message bubbles
        this.last_user_input = this.user_input;
        this.user_input = '';
    },


    async send(text) {
        stream = Alpine.store('stream');

        const wasSteering = stream.state !== 'idle';

        // record the sent text in the input history before clearing the box
        this.pushInputHistory(text);

        await this.clearInput();

        // handle any files the user may have attached
        const uploadStore = Alpine.store("upload");

        let files = null;

        if (uploadStore.files.length > 0) {
            files = await Promise.all(
                uploadStore.files.map(async (file) => ({
                    name: file.name,
                    data: await uploadStore.readFileAsBase64(file)
                }))
            );
        }

        AudioManager.play("send_message");

        /*
         * send the message to the backend - websockets will take it from here
         * the backend will now emit user_message_added to confirm the user message was received by the backend,
         * which the frontend (services/websockets.js) receives and then triggers reloadChat() on this chat store
         * so that the new user message shows up
         */
        const success = await simpleSocketSend({
            type: "user_message",
            content: text,
            files: files
        });

        // if the message never made it onto the socket, restore the draft
        // (and keep any attached files) so the user can retry
        if (success === false) {
            this.user_input = text;
            if (!wasSteering) {
                Alpine.store("stream").state = "idle";
            }
            return;
        }

        uploadStore.clear();
    },

    /* ----------------------
     * message actions
     * ----------------------- */
    async copyMessage(turnIndex) {
      const turn = this.turnAt(turnIndex);
      const msg = turn?.messages?.[turn.messages?.length - 1]; // last message in the turn
      if (!msg) return;

      // if the message had multimedia in it, extract only the text bit
      const filenames = msg._metadata?.filenames || [];
      const text = Array.isArray(msg.content)
        ? msg.content.filter((b, i) => b?.type === 'text' && b.text && !filenames[i]).map(b => b.text).join('\n\n')
        : msg.content;

      // resolves to whether the write to the clipboard succeeded
      return navigator.clipboard.writeText(text)
        .then(() => {
            return true;
        })
        .catch(err => {
            return false;
        });
    },

    async deleteMessage(turnIndex) {
        const turn = this.turnAt(turnIndex);
        if (!turn) return;
        await simpleSocketSend({
            "type": "message_delete",
            "index": turn.first_message_index
        });
    },

    async regenerateMessage(turnIndex) {
        const turn = this.turnAt(turnIndex);
        if (!turn) return;

        Alpine.store('stream').userMsg = null;
        Alpine.nextTick(async () => {
            await simpleSocketSend({
                "type": "message_regenerate",
                "index": turn.first_message_index
            });
        });
    },

    async startEdit(turnIndex) {
        const turn = this.turnAt(turnIndex);
        const msg = turn?.messages?.[turn.messages?.length - 1]; // last message in the turn
        if (!msg) { return; }
        
        this.editingMessageIndex = msg.index;
        this.editContent = msg.content;
        Alpine.store('ui').scrollToTurnIndex = turnIndex;
    },

    async cancelEdit() {
        this.editingMessageIndex = null;
        this.editContent = '';
    },

    async saveEdit(index) {
        await simpleSocketSend({
            "type": "message_edit",
            "index": index,
            "content": this.editContent
        });

        this.editingMessageIndex = null;
        this.editContent = '';
    },

    /* ----------------------
     * chat export
     * ----------------------- */
    async export() {
        try {
            // the backend returns {content, filename}: title->filename
            // sanitization moved server-side
            const result = await simpleApiFetch('/api/chat/export');

            if (!result || !result.content) {
                throw new Error('Export returned empty data');
            }

            // Create blob and trigger download
            const blob = new Blob([result.content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = result.filename || 'chat-export.txt';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Export failed:', err);
            // Optional: show a toast/notification to the user
        }
    },

    /* ----------------------
     * global search
     * ----------------------- */
    async searchGlobal(query, searchInContent = true, category = null, tags = [], sort = 'updated') {
        try {
            return await simpleApiPost('/api/chats/search', {
                query: query,
                search_in_content: searchInContent,
                category: category,
                tags: tags,
                sort: sort,
                tz_offset: this.tzOffset()
            });
        } catch (err) {
            console.error('Global search failed:', err);
            return [];
        }
    },

    async loadChatFromSearch(chatId) {
        await this.loadChat(chatId);
        Alpine.store('ui').closeModal();
        if (Alpine.store('ui').isMobile) {
            Alpine.store('ui').showSidebar = false;
        }
    },

    /* ----------------------
     * chat-specific getters
     * ----------------------- */
    // chat name for the header, hard-capped at 150 chars (CSS handles
    // soft truncation when it still doesn't fit the viewport)
    headerTitle() {
        const title = this.chat?.title || '';
        return title.length > 150 ? `${title.slice(0, 150).trimEnd()}…` : title;
    },

    get promptprogress() {
        // llama.cpp router model-load progress takes over the indicator
        // while a model is being swapped in, before prompt eval begins.
        const load = Alpine.store("stream").modelLoad;
        if (load) {
            const percent = load.percent ?? 0;

            // trim the org prefix from the router's repo:tag id
            // ("ggml-org/gemma-3-4b-it-GGUF:Q4_K_M" -> "gemma-3-4b-it-GGUF:Q4_K_M")
            const modelName = (load.model || "").split("/").pop();

            let label = modelName ? `Loading ${modelName}` : "Loading model";
            if (load.status === "queued") { label = `Queued: ${modelName || "model"}`; }
            if (load.status === "downloading") { label = `Downloading ${modelName || "model"}`; }

            const stage = load.stage ? ` · ${load.stage.replace(/_/g, " ")}` : "";

            return {
                mode: "model_load",
                percent,
                percent_str: `${percent}%`,
                remaining_str: `(${label}${stage})`,
                show_eta: false
            };
        }

        const progressData = Alpine.store("stream").processing;

        const cache = progressData.cache || 0;
        const processed = (progressData.processed || 0) - cache;
        const total = (progressData.total || 0) - cache;
        const percent = progressData.percent ?? 0;
        const remaining = progressData.eta_seconds || 0;

        return {
            cache,
            processed,
            total,
            percent,
            percent_str: `${percent}%`,
            elapsed: ((progressData.time_ms || 0) / 1000).toFixed(1),
            remaining,
            show_eta: processed > 0 && remaining > 0,
            // placeholder instead of hiding ETA so pill width stays stable
            remaining_str: (processed > 0 && remaining > 0) ? `(ETA: ${Math.ceil(remaining)}s)` : `(ETA: ...)`
        };
    }
}
