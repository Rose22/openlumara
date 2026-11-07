/* -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-04)
   characters sidebar panel logic. plain global object consumed by
   x-data="CHARACTERS_PANEL" in sidebars/character_list.html (ext asset
   scripts load before alpine, same as the core stores). talks to the
   module's own routes under /api/ext/characters/. */
const CHARACTERS_PANEL = {
    names: [],      // [{key, name, category}]
    counts: {},     // {character key: chat count}
    selected: "",   // character key, "" = none picked yet (shows no chats)
    chats: [],      // [{id, title, updated}]
    loading: false,
    loaded: false,

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-23)
    // category filter for the character dropdown. "" = all categories,
    // "__none__" = the uncategorized bucket, anything else = exact match.
    category: "",

    categories() {
        // distinct non-empty categories, sorted, with the uncategorized
        // bucket appended only when at least one character lacks one
        const cats = new Set();
        let hasNone = false;
        for (const entry of this.names) {
            if (entry.category) { cats.add(entry.category); }
            else { hasNone = true; }
        }
        const list = [...cats].sort((a, b) => a.localeCompare(b));
        if (hasNone) { list.push("__none__"); }
        return list;
    },

    categoryLabel() {
        if (!this.category) { return "all categories"; }
        if (this.category === "__none__") { return "uncategorized"; }
        return this.category;
    },

    visibleNames() {
        if (!this.category) { return this.names; }
        return this.names.filter(n =>
            this.category === "__none__" ? !n.category : n.category === this.category
        );
    },

    selectCategory(cat) {
        this.category = cat;
        // -- the filter may hide the currently-selected character; keep the
        // selection (its chats stay listed) unless it's no longer visible,
        // in which case drop back to the neutral prompt.
        if (this.selected && !this.visibleNames().some(n => n.key === this.selected)) {
            this.selected = "";
            this.chats = [];
        }
    },

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

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-14)
   character management modal (add / edit / delete with inline confirm /
   import json & png cards). opened via $store.ui.openModal('characters')
   from the sidebar tab's gear button; markup lives in
   templates/modals/manage_characters.html (auto-discovered). */
/* -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-23)
   unique id source for world info rows, so Alpine's x-for keys stay
   stable while the user adds/removes entries in the editor. */
let _wi_uid = 0;

function characterManager() {
    return {
        view: 'list',      // 'list' | 'editor'
        mode: 'add',       // 'add' | 'edit'
        characters: [],    // full character objects from /all
        loading: false,
        busy: false,
        confirming: null,  // storage key awaiting delete confirmation
        error: '',
        wiOpen: false,     // world info section expanded in the editor?
        categoryFilter: '',  // list view: '' = all, '__none__' = uncategorized

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-23)
        categories() {
            const cats = new Set();
            let hasNone = false;
            for (const c of this.characters) {
                if (c.category) { cats.add(c.category); }
                else { hasNone = true; }
            }
            const list = [...cats].sort((a, b) => a.localeCompare(b));
            if (hasNone) { list.push("__none__"); }
            return list;
        },

        categoryFilterLabel() {
            if (!this.categoryFilter) { return "all categories"; }
            if (this.categoryFilter === "__none__") { return "uncategorized"; }
            return this.categoryFilter;
        },

        filteredCharacters() {
            if (!this.categoryFilter) { return this.characters; }
            return this.characters.filter(c =>
                this.categoryFilter === "__none__" ? !c.category : c.category === this.categoryFilter
            );
        },
        form: {
            key: '',
            name: '',
            profile: '',
            scenario: '',
            first_message: '',
            post_history: '',
            category: '',
            mode: 'Character',  // Character (pure) | Assistant (full system prompt + tools)
            tags: '',      // comma-separated string in the form
            world_info: [],  // [{id, keyword, info}] rows
        },

        async init() {
            await this.load();
        },

        // escape: editor -> back to list, list -> close the modal
        esc() {
            if (this.view === 'editor') { this.backToList(); return; }
            Alpine.store('ui').closeModal();
        },

        async load() {
            this.loading = true;
            try {
                this.characters = await simpleApiFetch('/api/ext/characters/all');
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to load characters';
                this.characters = [];
            } finally {
                this.loading = false;
            }
        },

        openAdd() {
            this.error = '';
            this.confirming = null;
            this.mode = 'add';
            this.wiOpen = false;
            this.form = {
                key: '',
                name: '',
                profile: '',
                scenario: '',
                first_message: '',
                post_history: '',
                category: '',
                mode: 'Character',
                tags: '',
                world_info: [],
            };
            this.view = 'editor';
        },

        /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-11-06)
           world info is stored as a list of {keywords: [...], info} entries;
           edited as rows with a comma-separated keyword string per row.
           also still accepts the old {keyword: info} dict shape, so a
           not-yet-migrated character edits cleanly. */
        _worldInfoToRows(wi) {
            if (!wi || typeof wi !== 'object') { return []; }

            // old dict shape (or a raw character_book): one row per key
            if (!Array.isArray(wi)) {
                const entries = (wi.entries && typeof wi.entries === 'object') ? wi.entries : wi;
                const pairs = Array.isArray(entries)
                    ? entries.map(e => [e && (e.key || e.keywords), e && (e.content || e.info)])
                    : Object.entries(entries);
                return pairs
                    .filter(([kw, info]) => kw && info)
                    .map(([kw, info]) => ({
                        id: ++_wi_uid,
                        keywords: Array.isArray(kw) ? kw.join(', ') : String(kw),
                        info: typeof info === 'string' ? info : JSON.stringify(info),
                    }));
            }

            return wi
                .filter(e => e && typeof e === 'object' && e.info)
                .map(e => ({
                    id: ++_wi_uid,
                    keywords: Array.isArray(e.keywords)
                        ? e.keywords.join(', ')
                        : String(e.keywords || e.keyword || ''),
                    info: typeof e.info === 'string' ? e.info : JSON.stringify(e.info),
                }));
        },

        _rowsToWorldInfo(rows) {
            const out = [];
            for (const row of rows) {
                const keywords = (row.keywords || '')
                    .split(',')
                    .map(k => k.trim())
                    .filter(k => k);
                const info = (row.info || '').trim();
                if (!keywords.length || !info) { continue; }
                out.push({ keywords: keywords, info: info });
            }
            return out;
        },

        addWorldInfo() {
            this.form.world_info.push({ id: ++_wi_uid, keywords: '', info: '' });
        },

        removeWorldInfo(idx) {
            this.form.world_info.splice(idx, 1);
        },

        async edit(key) {
            this.error = '';
            // grab the freshest copy from the backend rather than trusting
            // the list snapshot (another tab may have edited it)
            let char = this.characters.find(c => c.key === key);
            try {
                char = await simpleApiFetch(`/api/ext/characters/get?name=${encodeURIComponent(key)}`);
            } catch (e) {
                // fall back to the list copy if the fetch failed
            }
            if (!char) { return; }

            this.mode = 'edit';
            const wiRows = this._worldInfoToRows(char.world_info);
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-23)
            // always start collapsed; the count pill on the header shows
            // whether there are entries to expand into.
            this.wiOpen = false;
            this.form = {
                key: key,
                name: char.name || key,
                profile: char.profile || '',
                scenario: char.scenario || '',
                first_message: char.first_message || '',
                post_history: char.post_history || '',
                category: char.category || '',
                mode: char.mode === 'Assistant' ? 'Assistant' : 'Character',
                tags: (char.tags || []).join(', '),
                world_info: wiRows,
            };
            this.view = 'editor';
        },

        backToList() {
            this.view = 'list';
            this.error = '';
            this.confirming = null;
        },

        async save() {
            this.error = '';
            const name = this.form.name.trim();
            const profile = this.form.profile.trim();

            if (!name) { this.error = 'character name cannot be empty'; return; }
            if (!profile) { this.error = 'character profile must not be blank'; return; }

            const payload = {
                name: name,
                profile: profile,
                scenario: this.form.scenario,
                first_message: this.form.first_message,
                post_history: this.form.post_history,
                category: this.form.category.trim(),
                mode: this.form.mode,
                tags: this.form.tags,
                world_info: this._rowsToWorldInfo(this.form.world_info),
            };

            this.busy = true;
            try {
                if (this.mode === 'add') {
                    await simpleApiPost('/api/ext/characters/add', payload);
                } else {
                    payload.key = this.form.key;
                    await simpleApiPost('/api/ext/characters/edit', payload);
                }
                await this.load();
                this.backToList();
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to save character';
            } finally {
                this.busy = false;
            }
        },

        async remove(key) {
            this.busy = true;
            try {
                await simpleApiPost('/api/ext/characters/remove', { name: key });
                this.confirming = null;
                await this.load();
            } catch (e) {
                this.error = typeof e === 'string' ? e : 'failed to delete character';
            } finally {
                this.busy = false;
            }
        },

        // reads the picked file(s) locally and hands the bytes to the
        // backend as base64 (keeps the route plain JSON, no multipart)
        async importFiles(event) {
            const input = event.target;
            const files = Array.from(input.files || []);
            input.value = '';   // allow re-picking the same file later
            if (files.length === 0) { return; }

            this.error = '';
            this.busy = true;
            const failures = [];

            for (const file of files) {
                try {
                    const data = await this._readAsBase64(file);
                    await simpleApiPost('/api/ext/characters/import_file', {
                        filename: file.name,
                        data: data,
                    });
                } catch (e) {
                    failures.push(`${file.name}: ${typeof e === 'string' ? e : 'import failed'}`);
                }
            }

            if (failures.length) { this.error = failures.join(' • '); }
            this.busy = false;
            await this.load();
        },

        _readAsBase64(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = () => reject(`${file.name}: could not be read`);
                reader.readAsDataURL(file);
            });
        },
    };
}
