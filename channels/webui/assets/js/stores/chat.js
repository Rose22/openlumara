function mergeTurnHistory(existing, incoming) {
    incoming = incoming || [];
    if (!Array.isArray(existing) || existing.length === 0) return incoming;

    const merged = new Array(incoming.length);

    for (let i = 0; i < incoming.length; i++) {
        merged[i] = (existing[i] && existing[i].hash && existing[i].hash === incoming[i].hash)
            ? existing[i]
            : incoming[i];
    }

    const tail = existing[existing.length - 1];
    if (tail && tail.live === true) {
        let lastUser = -1;
        for (let i = incoming.length - 1; i >= 0; i--) {
            if (incoming[i].role === 'user') { lastUser = i; break; }
        }

        const kept = lastUser === -1 ? merged : merged.slice(0, lastUser + 1);
        kept.push(tail);
        return kept;
    }

    return merged;
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
    editingMessageIndex: null,
    editContent: '',

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

    async load() {
        // called by Alpine.init
        await this.reloadCategories();
        this.loadInputHistory();

        const result = await simpleApiFetch(`/api/chat/current`);
        if (!result) { return }

        this.chat = result;
        this.selectedChat = result.id;
        this.selectedCategory = result.category;
        this.turnHistory = mergeTurnHistory(this.turnHistory, result.turn_history);
        this.currentTokenUsage = result.token_usage;

        Alpine.store('ui').prepareBottomWindow();

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

        const ui = Alpine.store('ui');

        this.turnHistory = [];
        ui.resetTurnMounts();
        await Alpine.nextTick();

        this.chat = result;
        this.selectedChat = chatId;
        this.selectedCategory = result.category;
        this.turnHistory = result.turn_history;
        this.currentTokenUsage = result.token_usage;

        // bottom-up: mount the tail of the chat before scrolling to it
        ui.prepareBottomWindow();

        await this.ensureChatVisible(chatId);

        // make sure it always shows the bottom of the chat
        await ui.forceScrollToBottom();
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

        if (!collapse) {
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

        await Promise.all(
            this.dayGroups.filter(g => !this.isGroupCollapsed(g))
                .map(g => this.loadDayChats(g))
        );

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
            `&limit=${this.chatLimit}&tz_offset=${this.tzOffset()}${this.catParam()}${this.tagParam()}`
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

        this.collapsedDays[this.todayKey()] = false;

        await this.reloadChats();
        await this.reloadChat();
    },

    async renameChat(chat_id, newTitle) {
        await simpleApiPost(`/api/chat/rename/${chat_id}`, {title: newTitle});
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

        Alpine.store('ui').syncMountWindows();

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
      const turn = this.turnHistory[turnIndex];
      const msg = turn?.messages?.[turn.messages?.length - 1]; // last message in the turn
      if (!msg) return;

      // if the message had multimedia in it, extract only the text bit
      const filenames = msg._metadata?.filenames || [];
      const text = Array.isArray(msg.content)
        ? msg.content.filter((b, i) => b?.type === 'text' && b.text && !filenames[i]).map(b => b.text).join('\n\n')
        : msg.content;

      navigator.clipboard.writeText(text)
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
