/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-04)
   characters sidebar panel logic. plain global object consumed by
   x-data="CHARACTERS_PANEL" in sidebars/character_list.html (ext asset
   scripts load before alpine, same as the core stores). talks to the
   module's own routes under /api/ext/characters/. */
const CHARACTERS_PANEL = {
    names: [],      // [{key, name}]
    counts: {},     // {character key: chat count}
    selected: "",   // character key, "" = none picked yet (shows no chats)
    chats: [],      // [{id, title, updated}]
    loading: false,
    loaded: false,

    // driven by x-intersect on the panel root: fires every time the tab
    // switch makes the panel visible (first time = full load)
    async refresh() {
        if (!this.loaded) { await this.load(); return; }
        await Promise.all([
            simpleApiFetch('/api/ext/characters/chats_count')
                .then(c => { this.counts = c; }).catch(() => {}),
            this.loadChats(),
        ]);
    },

    selectedLabel() {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-04)
        // an empty selection means nothing has been picked yet (not
        // "untagged chats"), so prompt the user to pick one.
        if (!this.selected) { return "select a character"; }
        const entry = this.names.find(n => n.key === this.selected);
        return entry ? entry.name : this.selected;
    },

    async load() {
        this.loading = true;
        try {
            const [names, counts] = await Promise.all([
                simpleApiFetch('/api/ext/characters/names'),
                simpleApiFetch('/api/ext/characters/chats_count'),
            ]);
            this.names = names;
            this.counts = counts;
            await this.loadChats();
            this.loaded = true;
        } catch (e) {
            console.error("characters panel:", e);
        } finally {
            this.loading = false;
        }
    },

    async loadChats() {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-04)
        // with no character selected the panel shows no chats at all -
        // the untagged-chats view is gone along with the old label.
        if (!this.selected) { this.chats = []; return; }
        try {
            this.chats = await simpleApiFetch(`/api/ext/characters/chats?character=${encodeURIComponent(this.selected)}`);
        } catch (e) {
            console.error("characters panel:", e);
            this.chats = [];
        }
    },

    select(key) {
        this.selected = key;
        this.loadChats();
    },

    async newChat() {
        if (!this.selected) { return; }
        try {
            const result = await simpleApiPost('/api/ext/characters/create_chat', { name: this.selected });
            // backend created the chat and made it current; mirror that
            // into the core store. the id is brand new, so loadChat won't
            // early-return, and its ensureChatVisible opens the day group
            // in the chats tab too.
            if (result && result.id) {
                await Alpine.store('chat').loadChat(result.id);
                // same mobile behavior as the chats tab: the sidebar is a
                // full-screen overlay, so dismiss it to reveal the new chat
                if (Alpine.store('ui').isMobile) {
                    Alpine.store('ui').showSidebar = false;
                }
                // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-04)
                // refresh just the chat list (and its count) instead of a
                // full panel reload - names haven't changed.
                await this.loadChats();
                simpleApiFetch('/api/ext/characters/chats_count')
                    .then(c => { this.counts = c; }).catch(() => {});
            }
        } catch (e) {
            console.error("characters panel:", e);
        }
    },
};
