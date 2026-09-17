/*
 * structural equality check between two turns.
 *
 * used so that reloading a chat can keep the *existing* turn objects around
 * for every turn that didn't actually change. alpine's x-for keys turns by
 * index, so if you hand it a fresh array of fresh objects it re-seeds the
 * scope of every single turn, which re-runs every x-html in the chat, which
 * re-parses the markdown of your entire conversation on every reload.
 *
 * keeping the object identity stable means only genuinely new/changed turns
 * ever re-render.
 */
function turnsEqual(a, b) {
    if (!a || !b) return false;
    if (a.role !== b.role) return false;
    if (a.first_message_index !== b.first_message_index) return false;
    if (a.last_message_index !== b.last_message_index) return false;

    const am = a.messages || [];
    const bm = b.messages || [];
    if (am.length !== bm.length) return false;

    for (let i = 0; i < am.length; i++) {
        const x = am[i];
        const y = bm[i];

        if (x === y) continue;
        if (!x || !y) return false;

        if (x.index !== y.index) return false;
        if (x.role !== y.role) return false;
        if (x.content !== y.content) return false;
        if (x.reasoning_content !== y.reasoning_content) return false;
        if (x._metadata?.is_cmd !== y._metadata?.is_cmd) return false;

        const xc = x.tool_calls || [];
        const yc = y.tool_calls || [];
        if (xc.length !== yc.length) return false;

        for (let j = 0; j < xc.length; j++) {
            if (xc[j].id !== yc[j].id) return false;
            if (xc[j].response !== yc[j].response) return false;
        }
    }

    return true;
}

function mergeTurnHistory(existing, incoming) {
    incoming = incoming || [];
    if (!Array.isArray(existing) || existing.length === 0) return incoming;

    const merged = new Array(incoming.length);

    for (let i = 0; i < incoming.length; i++) {
        merged[i] = turnsEqual(existing[i], incoming[i]) ? existing[i] : incoming[i];
    }

    return merged;
}

CHAT_STORE = {
    /*
     * alpine.js store for chat state
     */

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
       option d: the sidebar shows ALL day headers at once (cheap
       /api/chats/days listing), and chats are fetched per-day only when
       a group is expanded (paginated per day via /api/chats/day).
       group shape: {key, label, count, chats, offset, hasMore, loading,
       loaded}. the old flat visibleChats/chatOffset pagination is gone. */
    dayGroups: [],
    chatLimit: 10,
    dayFetchGen: 0,

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
       the chat object the 'move to category' modal targets (the whole
       object, not just the id: moved chats can come from search results,
       which don't live in the day groups) */
    moveChatTarget: null,

    categories: [],
    chat: {},
    selectedChat: null,
    selectedCategory: 'general',

    turnHistory: [],
    editingMessageIndex: null,
    editContent: '',

    user_input: '',
    last_user_input: '',

    currentTokenUsage: 0,

    async load() {
        // called by Alpine.init
        await this.reloadCategories();

        const result = await simpleApiFetch(`/api/chat/current`);
        if (!result) { return }

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;
        this.turnHistory = result.turn_history;
        this.currentTokenUsage = result.token_usage;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // only fetch the chat list AFTER selectedCategory is known: it
        // used to load first (scoped to 'general'), then the category
        // flipped to the loaded chat's category, and the x-if category
        // filter hid every (wrongly-scoped) chat in the sidebar.
        await this.reloadChats();

        // ensure the chat exists in the visible sidebar list before scrolling
        await this.ensureChatVisible(this.selectedChat);
    },

    /* ----------------------
     * chat manipulation
     * ----------------------- */
    async loadChat(chatId) {
        if (this.selectedChat === chatId) { return; }

        // don't allow chat switching if a stream is ongoing
        if (Alpine.store("stream").state != 'idle') { return; }

        const result = await simpleApiFetch(`/api/chat/load/${chatId}`);
        if (!result) { return; }

        this.chat = result;
        this.selectedChat = chatId;
        this.selectedCategory = result.category;
        this.turnHistory = result.turn_history;

        ui = Alpine.store('ui');
        this.currentTokenUsage = result.token_usage;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // the open chat's day group must be expanded (and the chat
        // itself loaded), so the active item is never hidden
        await this.ensureChatVisible(chatId);

        // make sure it always shows the bottom of the chat
        await ui.forceScrollToBottom();
    },

    /* ----------------------
     * sidebar search
     * ----------------------- */
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    // searching now uses the backend /api/chats/search endpoint (the same
    // one the global search modal uses): one request, all matches, no
    // pagination. while searching, the paginated visibleChats list simply
    // freezes (the scroll loader is hidden), so clearing the box is a pure
    // mode switch back to it - no refetch needed.
    searchQuery: '',
    searchResults: [],
    searchLoading: false,
    searchDebounce: null,

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    // content search is opt-in via the toggle button next to the search
    // field (default: titles only), persisted across sessions.
    searchInContent: localStorage.getItem('sidebarSearchInContent') === 'true',

    get searching() { return Boolean(this.searchQuery.trim()); },

    /* ----------------------
     * day groups (sidebar)
     * ----------------------- */
    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
       option d: /api/chats/days lists every day that has chats (cheap,
       no chat data), so all headers render instantly. chats are only
       fetched for EXPANDED groups, paginated per day. default: today
       expanded, everything else collapsed; an explicit toggle wins. */
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

    isGroupCollapsed(group) {
        // search results are always shown fully - hiding matches behind
        // a collapsed header would be maddening
        if (this.searching) { return false; }
        if (group.key in this.collapsedDays) { return Boolean(this.collapsedDays[group.key]); }
        return group.key !== this.todayKey();
    },

    toggleDayGroup(group) {
        const collapse = !this.isGroupCollapsed(group);
        this.collapsedDays[group.key] = collapse;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // on expand, fill the viewport: the per-group loader can appear
        // already in view, and x-intersect (entry-only) won't fire for
        // it. run the fill loop after the DOM updated.
        if (!collapse) {
            Alpine.nextTick(() => this.ensureDayChatsFilled(group));
        }
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // keep loading pages for one day group while its loader is visible
    // in the .chats scroll container, so a newly expanded group always
    // shows chats (and x-intersect can take over from there: once
    // content pushes the loader out of view, entry events drive it).
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
    // client-side grouped search results while searching
    displayGroups() {
        if (!this.searching) { return this.dayGroups; }

        // search results arrive newest-first, so first-seen order is
        // the correct (descending) day order. groupKeyOf mirrors the
        // backend: past week by day, older by month.
        const groups = [];
        const byKey = {};

        for (const chat of this.searchResults) {
            const key = groupKeyOf(chat.updated) || 'undated';
            if (!(key in byKey)) {
                byKey[key] = { key: key, label: dayLabelFromKey(key), chats: [] };
                groups.push(byKey[key]);
            }
            byKey[key].chats.push(chat);
        }

        return groups;
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // fetch the day header list, then (re)load the chats of every group
    // that is currently expanded. a generation counter discards stale
    // in-flight requests when the list reloads again (fast category
    // switches, deletes, etc).
    async reloadDayGroups() {
        const gen = ++this.dayFetchGen;

        const groupList = await simpleApiFetch(`/api/chats/days?tz_offset=${this.tzOffset()}${this.catParam()}`);

        // stale: a newer reload superseded this one
        if (gen !== this.dayFetchGen) { return; }

        this.dayGroups = (groupList ?? []).map(g => ({
            key: g.key,
            label: dayLabelFromKey(g.key),
            count: g.count,
            chats: [],
            offset: 0,
            hasMore: g.count > 0,
            loading: false,
            loaded: false
        }));

        await Promise.all(
            this.dayGroups.filter(g => !this.isGroupCollapsed(g))
                .map(g => this.loadDayChats(g))
        );

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // first pages are in: fill the viewport of every expanded group
        // (a loader that renders already-visible never fires x-intersect)
        await Alpine.nextTick();
        await Promise.all(
            this.dayGroups.filter(g => !this.isGroupCollapsed(g))
                .map(g => this.ensureDayChatsFilled(g))
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

        const result = await simpleApiFetch(
            `/api/chats/day?day=${group.key}&offset=${group.offset}` +
            `&limit=${this.chatLimit}&tz_offset=${this.tzOffset()}${this.catParam()}`
        );

        group.loading = false;

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
        if (this.searching) { this._runChatSearch(this.searchQuery.trim()); }
    },

    sidebarSnippet(chat) {
        // 3-line content preview for search results (shown when content
        // search is on). returns html with the query highlighted.
        if (!this.searchInContent) { return ''; }

        const snippets = chat.message_snippets;
        if (!snippets || snippets.length === 0) { return ''; }

        const text = escapeHtml(snippets[0]);
        const q = this.searchQuery.trim();
        if (!q) { return text; }

        // both sides escaped identically before regexing, so queries with
        // & < > " ' still match the escaped text
        const pattern = escapeHtml(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return text.replace(
            new RegExp(pattern, 'gi'),
            (m) => `<strong class="search-highlight">${m}</strong>`
        );
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

        // debounce so we don't hit the backend on every keystroke
        this.searchDebounce = setTimeout(() => this._runChatSearch(q.trim()), 200);
    },

    async _runChatSearch(q) {
        this.searchLoading = true;
        const results = await this.searchGlobal(q, this.searchInContent, this.selectedCategory);

        // stale: query changed or was cleared while the request was in flight
        if (this.searchQuery.trim() !== q) { return; }

        this.searchResults = results;
        this.searchLoading = false;
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // option d: reloading the sidebar = reloading the day header list
    // (which re-fetches the chats of every expanded group). collapsed
    // groups cost one cheap day-list request, nothing else.
    async reloadChats() {
        await this.reloadDayGroups();

        // refresh search results alongside, so renames/deletes (which
        // reload the list) don't leave the search mode list stale.
        if (this.searching) { await this._runChatSearch(this.searchQuery.trim()); }
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // walk the day groups (newest first), loading each one's chats
    // until the target chat shows up, then expand its group. usually it
    // hits immediately in the already-loaded today group; opening an old
    // chat walks back through the days (without expanding them).
    async ensureChatVisible(chatId) {
        for (const group of this.dayGroups) {
            if (group.chats.some(c => c.id === chatId)) {
                this.collapsedDays[group.key] = false;
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
                    return true;
                }
                if (!progressed) { break; }
            }
        }

        return false;
    },

    async newChat(category = null) {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // create the chat inside the given category, falling back to the
        // currently selected one (the endpoint defaults to 'general' when
        // nothing is sent). the category modal passes an explicit name to
        // create a brand new category: a category exists once a chat uses it.
        await simpleApiPost('/api/chat/new', { category: category ?? this.selectedCategory });

        result = await simpleApiFetch('/api/chat/current');
        if (!result) { return; }

        this.chat = result;

        this.selectedChat = result.id;
        this.selectedCategory = result.category;
        this.currentTokenUsage = result.token_usage;
        this.turnHistory = result.turn_history;

        // the new chat may live in a category the dropdown doesn't list yet
        await this.reloadCategories();

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // a new chat always lives in 'today' - force that group open even
        // if it was manually collapsed, so the new chat is visible
        this.collapsedDays[this.todayKey()] = false;

        await this.reloadChats();
        await this.reloadChat();
    },

    async renameChat(chat_id, newTitle) {
        await simpleApiPost(`/api/chat/rename/${chat_id}`, {title: newTitle});
        await this.reloadChats();
    },

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
       move a chat to another category. if it's the open chat, its own
       category changed too - reload it and re-scope the sidebar list so
       the moved chat (and the now-current category's chats) stay visible. */
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

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // refreshing the category list after every delete keeps the
        // dropdown in sync: if the last chat of a category was removed,
        // its option disappears; if that was the selected category,
        // fall back to 'general' (or the first remaining one).
        await this.reloadCategories();

        const cats = this.categories ?? [];
        if (this.selectedCategory && !cats.includes(this.selectedCategory)) {
            this.selectedCategory = cats.includes('general')
                ? 'general'
                : (cats[0] ?? 'general');
        }

        await this.reloadChats();
    },

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
       delete a category: the backend moves all of its chats to 'general'.
       if it was the selected category, fall back; reloadChat() because the
       currently open chat may itself have just moved to 'general'. */
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

        const result = await simpleApiFetch(`/api/chat/current`);
        if (!result) { return }

        const prevCategory = this.selectedCategory;

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;

        // reuse the existing turn objects for every turn that didn't actually
        // change, so alpine doesn't re-render (and re-parse the markdown of)
        // the entire conversation on every single reload
        this.turnHistory = mergeTurnHistory(this.turnHistory, result.turn_history);

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // if the backend switched us to a chat in another category, the
        // sidebar list is now scoped to the wrong category (everything
        // would vanish behind the x-if filter) - refetch it, and make
        // sure the newly selected chat is in the list.
        if (result.category !== prevCategory) {
            await this.reloadCategories();
            await this.reloadChats();
            await this.ensureChatVisible(result.id);
        }
    },

    async reloadCategories() {
        this.categories = await simpleApiFetch('/api/chats/categories');
    },

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
       options for the sidebar category dropdown. always includes the
       selected category, even if the backend list doesn't contain it
       yet (e.g. a chat was just loaded/created in a brand new category)
       - a select whose value matches no option renders blank.
       sorted alphabetically, with 'general' pinned to the top. */
    dropdownCategories() {
        let cats = [...(this.categories ?? [])];
        if (this.selectedCategory && !cats.includes(this.selectedCategory)) {
            cats.push(this.selectedCategory);
        }

        cats.sort((a, b) => (a ?? '').localeCompare(b ?? ''));

        const generalIndex = cats.indexOf('general');
        if (generalIndex > 0) {
            cats.splice(generalIndex, 1);
            cats.unshift('general');
        }

        return cats;
    },

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
       the select's :value binding goes through this instead of
       selectedCategory directly: touching this.categories makes alpine's
       effect re-run when the option list changes, so the value is
       re-applied even if it was set before the options existed (a plain
       :value effect only tracks selectedCategory and would leave the
       dropdown blank). */
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
        if (stream.state !== 'idle') {
            // don't allow sending during a stream
            // (TODO: allow nudging (interrupting the stream and sending a new message))
            return;
        }

        Alpine.store("stream").state = "message_sending";
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

        uploadStore.clear();
    },

    /* ----------------------
     * message actions
     * ----------------------- */
    async copyMessage(turnIndex) {
      const turn = this.turnHistory[turnIndex];
      const msg = turn?.messages?.[turn.messages?.length - 1]; // last message in the turn
      if (!msg) return;
      navigator.clipboard.writeText(msg.content)
        .then(() => {
            return true;
        })
        .catch(err => {
            return false;
        });
    },

    async deleteMessage(turnIndex) {
        const turn = this.turnHistory[turnIndex];
        if (!turn) return;
        await simpleSocketSend({
            "type": "message_delete",
            "index": turn.first_message_index
        });
    },

    async regenerateMessage(turnIndex) {
        const turn = this.turnHistory[turnIndex];
        if (!turn) return;

        Alpine.store('stream').userMsg = null;
        Alpine.nextTick(async () => {
            await simpleSocketSend({
                "type": "message_regenerate",
                "index": turn.first_message_index
            });

            Alpine.store('stream').state = 'message_sending';
        });
    },

    async startEdit(turnIndex) {
        const turn = this.turnHistory[turnIndex];
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
            // Get the export string from the backend
            const exportStr = await simpleApiFetch('/api/chat/export');
            
            if (!exportStr) {
                throw new Error('Export returned empty data');
            }

            // Get chat title for filename
            const chatTitle = this.chat?.title || 'chat-export';
            const safeTitle = chatTitle.replace(/[\/\\:*?"<>|]/g, '_');
            const filename = `${safeTitle}.txt`;

            // Create blob and trigger download
            const blob = new Blob([exportStr], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
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
    async searchGlobal(query, searchInContent = true, category = null) {
        try {
            const result = await simpleApiPost('/api/chats/search', {
                query: query,
                search_in_content: searchInContent,
                category: category
            });
            
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
            // pure updated-descending sort (the old title-matches-first
            // priority scrambled the day groups in the sidebar, which
            // rely on strict newest-first order).
            result.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));

            return result;
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
    get promptprogress() {
        // does the math for the prompt processing indicator over in components/promptprocess.html
        // the math was ported straight over from the old webUI because, well, it works, and it's clean code
        const progressData = Alpine.store("stream").processing;

        const cache = progressData.cache || 0;
        const processed = progressData.processed - cache;
        const total = progressData.total - cache;
        const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
        const elapsed = progressData.time_ms / 1000;
        const remaining = (total - processed) > 0 ? (elapsed / processed) * (total - processed) : 0;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // expose show_eta so the indicator hides ETA until it can actually be estimated
        return {
            cache,
            processed,
            total,
            percent,
            percent_str: `${percent}%`,
            elapsed: elapsed.toFixed(1),
            remaining,
            show_eta: processed > 0 && remaining > 0,
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
            // placeholder instead of hiding ETA so pill width stays stable
            remaining_str: (processed > 0 && remaining > 0) ? `(ETA: ${Math.ceil(remaining)}s)` : `(ETA: ...)`
        };
    }
}
