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

    visibleChats: [],
    chatOffset: 0,
    chatLimit: 10,
    hasMoreChats: true,

    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
       the chat object the 'move to category' modal targets (the whole
       object, not just the id: moved chats can come from search results,
       which don't live in visibleChats) */
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

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // the loaded chat's day group must be open, even if it isn't today
        this.expandDayOfChat(this.selectedChat);
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
        // keep the open chat's day group expanded in the sidebar
        this.expandDayOfChat(chatId);

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

    sidebarChats() {
        return this.searching ? this.searchResults : this.visibleChats;
    },

    /* ----------------------
     * date grouping (sidebar)
     * ----------------------- */
    /* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
       chats are grouped by relative calendar day under collapsible
       headers. default: today expanded, every other day collapsed;
       once the user toggles a group, their explicit choice wins. */
    collapsedDays: {},

    todayKey() {
        return new Date().toDateString();
    },

    isGroupCollapsed(key) {
        if (key in this.collapsedDays) { return this.collapsedDays[key]; }
        return key !== this.todayKey();
    },

    toggleDayGroup(key) {
        this.collapsedDays[key] = !this.isGroupCollapsed(key);
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    // the group of the open chat is always expanded (on load/chat switch)
    // so the active item is never hidden behind a collapsed header.
    expandDayOfChat(chatId) {
        const chat = this.visibleChats.find(c => c.id === chatId)
            || this.searchResults.find(c => c.id === chatId);
        if (!chat) { return; }

        this.collapsedDays[dayKeyOf(chat.updated) || 'undated'] = false;
    },

    groupedSidebarChats() {
        // pagination mode filters by category here (the template used to
        // do it per-item); search results are already category-scoped
        // by the backend.
        const source = this.searching
            ? this.searchResults
            : this.visibleChats.filter(c => c.category === this.selectedCategory);

        // chats arrive newest-first, so first-seen order = correct day
        // order; the byKey map merges late-arriving pages into the day
        // they belong to instead of spawning duplicate headers.
        const groups = [];
        const byKey = {};

        for (const chat of source) {
            const key = dayKeyOf(chat.updated) || 'undated';
            if (!(key in byKey)) {
                byKey[key] = { key: key, label: dayLabelOf(chat.updated), chats: [] };
                groups.push(byKey[key]);
            }
            byKey[key].chats.push(chat);
        }

        return groups;
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

    async reloadChats() {
        this.cancelChatFetch();
        this.chatOffset = 0;
        this.visibleChats = [];
        await this._fetchChats();

        // ensure there are always more chats loaded than what fits in the current viewport
        await this.ensureMoreChats();

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // refresh search results alongside pagination, so renames/deletes
        // (which reload the list) don't leave the search mode list stale.
        if (this.searching) { await this._runChatSearch(this.searchQuery.trim()); }
    },

    async ensureChatVisible(chatId) {
        const exists = this.visibleChats.some(c => c.id === chatId);
        if (exists) { return; }

        // keep loading more chats until the target chat appears
        // (break if a page was cancelled by a newer reload)
        while (this.hasMoreChats && !this.visibleChats.some(c => c.id === chatId)) {
            if (!await this.loadMoreChats()) { break; }
        }
    },

    // resolves to true if a page was actually loaded, false if it was
    // cancelled or failed
    async loadMoreChats() {
        if (!this.hasMoreChats) { return false; }

        const before = this.visibleChats.length;
        const loaded = await this._fetchChats();
        if (!loaded) { return false; }

        // if the api returned nothing new, stop so callers that loop
        // (like ensureChatVisible) can't spin forever.
        if (this.visibleChats.length === before) { this.hasMoreChats = false; }

        return true;
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    // aborts an in-flight pagination request. kept because x-intersect can
    // still fire loadMoreChats right as a reload starts (category switch),
    // and an uncancelled page would land on top of the fresh page 1.
    chatsAbort: null,

    cancelChatFetch() {
        if (this.chatsAbort) { this.chatsAbort.abort(); this.chatsAbort = null; }
    },

    async ensureMoreChats(el) {
        /* 
         * makes sure there are always more chats loaded
         * than what the viewport can show,
         * so that x-intersect always works (because it needs to be out of view first)
         */
        // search mode shows backend results, pagination is frozen
        if (this.searching) { return; }

        const intersect_el = document.getElementById("chat-scroll-loader");
        if (!intersect_el) { return; }

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // compare against the .chats scroll container, not the window -
        // the loader scrolls inside that box, not with the page.
        const container = intersect_el.parentElement;
        if (!container) { return; }

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
        // loop instead of a one-shot check: with date grouping, a loaded
        // page can land entirely in collapsed groups, so the loader never
        // leaves the viewport and x-intersect (entry-only) won't re-fire.
        // keep going until the loader is out of view or no progress was
        // made (cancelled fetch / no more chats), so this can't spin.
        while (true) {
            const rect = intersect_el.getBoundingClientRect();
            const crect = container.getBoundingClientRect();

            const visible = rect.top < crect.bottom && rect.bottom > crect.top;
            if (!visible) { break; }

            const loaded = await this.loadMoreChats();
            if (!loaded) { break; }
        }
    },

    fetchingChats: false,

    // resolves to true if the page was loaded into visibleChats,
    // false if it was cancelled or failed
    async _fetchChats() {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // x-intersect can fire several times while a page is still in
        // flight (scroll + ensureMoreChats + ensureChatVisible all call
        // in), and concurrent fetches with the same offset pushed
        // duplicate chat objects into visibleChats (bloat + duplicate
        // x-for keys). one fetch at a time: callers wait for the in-flight
        // page rather than no-op, so loop callers can't busy-spin without
        // making progress.
        while (this.fetchingChats) {
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        this.fetchingChats = true;

        const controller = new AbortController();
        this.chatsAbort = controller;

        try {
            const offset = this.chatOffset;
            const catParam = this.selectedCategory ? `&category=${encodeURIComponent(this.selectedCategory)}` : '';
            const result = await simpleApiFetch(`/api/chats?offset=${offset}&limit=${this.chatLimit}${catParam}`, controller.signal);
            if (!result) { return false; }

            this.visibleChats.push(...result.messages);
            this.chatOffset += result.messages.length;
            this.hasMoreChats = result.has_more;
            return true;
        } catch (err) {
            // aborted (search cleared / list reloaded) or network hiccup:
            // either way, nothing was pushed and callers should stop
            return false;
        } finally {
            this.fetchingChats = false;
        }
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
            
            const queryLower = (query || '').toLowerCase();

            // Priority sort:
            // 1. Chats whose title contains the query come first
            // 2. Within each group, sorted by updated descending (newest first)
            result.sort((a, b) => {
                const aMatches = (a.title || '').toLowerCase().includes(queryLower);
                const bMatches = (b.title || '').toLowerCase().includes(queryLower);

                // Primary: matching titles first
                if (aMatches && !bMatches) return -1;
                if (!aMatches && bMatches) return 1;

                // Secondary: both match or both don't → sort by date descending
                return (b.updated || '').localeCompare(a.updated || '');
            });

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

        return {
            cache,
            processed,
            total,
            percent,
            percent_str: `${percent}%`,
            elapsed: elapsed.toFixed(1),
            remaining,
            remaining_str: `(ETA: ${Math.ceil(remaining)}s)`
        };
    }
}
