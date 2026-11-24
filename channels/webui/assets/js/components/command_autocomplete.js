let CMD_AC = null;

function cmdAutocompleteInstance() { return CMD_AC; }

function trimSpacers(cmds) {
    const out = [];

    for (const cmd of cmds) {
        if (cmd.spacer && (!out.length || out[out.length - 1].spacer)) continue;
        out.push(cmd);
    }

    while (out.length && out[out.length - 1].spacer) { out.pop(); }

    return out;
}

function commandAutocomplete() {
    return {
        prefix: "/",
        commands: {},       
        loaded: false,
        loading: false,
        attempted: false,
        visible: false,
        tabs: [],           
        activeTab: "",      
        items: [],          
        selected: 0,
        selectedName: "",   

        init() {
            CMD_AC = this;
            this.load();

            const wrapper = this.$el.parentElement?.querySelector('.input-wrapper');

            if (wrapper && typeof ResizeObserver !== 'undefined') {
                this._posObserver = new ResizeObserver(() => this.syncPos());
                this._posObserver.observe(wrapper);
            }

            window.addEventListener('resize', () => this.syncPos());
        },

        syncPos() {
            const input = this.$el.parentElement;
            const wrapper = input?.querySelector('.input-wrapper');
            const dropdown = this.$el.querySelector('.autocomplete-dropdown');
            if (!wrapper || !dropdown) return;

            const wr = wrapper.getBoundingClientRect();
            const pr = input.getBoundingClientRect();

            this.$el.style.left = (wr.left - pr.left) + 'px';
            this.$el.style.width = wr.width + 'px';

            dropdown.style.left = '0';
            dropdown.style.width = '100%';
            dropdown.style.bottom = (pr.bottom - wr.top) + 'px';
            dropdown.style.marginBottom = '-1px';
        },

        async load() {
            if (this.loading) return;
            this.loading = true;

            try {
                const [prefix, commands] = await Promise.all([
                    simpleApiFetch("/api/command_prefix"),
                    simpleApiFetch("/api/commands")
                ]);
                if (typeof prefix === "string" && prefix) this.prefix = prefix;
                if (commands && typeof commands === "object") this.commands = commands;
                this.loaded = true;
            } catch (err) {
                console.warn("command autocomplete: failed to load commands", err);
            } finally {
                this.loading = false;
            }
        },

        watch(text) {
            if (!this.loaded) {
                if (!text?.startsWith(this.prefix) || this.attempted) return;
                this.attempted = true;
                this.load();
                return;
            }

            const value = (text ?? "").trim();
            if (!value.startsWith(this.prefix)) { this.hide(); return; }

            this.filter(value.slice(this.prefix.length).toLowerCase());

            if (!this.tabs.length) { this.hide(); return; }

            let tab = this.tabs.find(t => t.category === this.activeTab && t.count > 0)
                ?? this.tabs.find(t => t.count > 0)
                ?? this.tabs[0];

            this.activeTab = tab.category;
            this.items = tab.cmds;
            this.select(0);
            this.visible = true;
        },

        filter(typed) {
            const names = [];
            let anyNameHit = false;

            for (const [category, cmds] of Object.entries(this.commands)) {
                const matches = [];

                for (const [name, desc] of Object.entries(cmds ?? {})) {
                    if (!name || name.startsWith("__SPACER__")) continue;

                    const lower = name.toLowerCase();
                    const target = this.prefix + typed;

                    let score = null;
                    if (lower.startsWith(target)) score = 200;
                    else if (lower.includes(target)) score = 150;

                    if (score !== null) {
                        matches.push({ name, desc: desc || category, nameHtml: this.highlight(name, typed), score: score - lower.length * 0.01 });
                    }
                }

                if (matches.length) {
                    anyNameHit = true;
                    matches.sort((a, b) => b.score - a.score);
                    names.push({ category, count: matches.length, cmds: matches });
                }
            }

            if (anyNameHit) { this.tabs = names; return; }

            const tabs = [];

            for (const [category, cmds] of Object.entries(this.commands)) {
                const matches = [];

                for (const [name, desc] of Object.entries(cmds ?? {})) {
                    if (!name || name.startsWith("__SPACER__")) continue;

                    const descLower = (desc ?? "").toLowerCase();
                    if (descLower.includes(typed)) {
                        matches.push({ name, desc: desc || category, nameHtml: this.highlight(name, typed) });
                    }
                }

                if (matches.length) {
                    tabs.push({ category, count: matches.length, cmds: trimSpacers(matches) });
                }
            }

            this.tabs = tabs;
        },

        switchTab(delta) {
            if (this.tabs.length < 2) return;

            const i = this.tabs.findIndex(t => t.category === this.activeTab);
            const n = this.tabs.length;
            const next = this.tabs[(((i + delta) % n) + n) % n];

            this.activeTab = next.category;
            this.items = next.cmds;
            this.select(0);
            this.scrollActiveTabIntoView();
        },

        scrollActiveTabIntoView() {
            Alpine.nextTick(() => {
                const strip = this.$el.querySelector(".autocomplete-tabs");
                strip?.querySelector(".autocomplete-tab.active")
                    ?.scrollIntoView({ block: "nearest", inline: "nearest" });
            });
        },

        pickTab(category) {
            const tab = this.tabs.find(t => t.category === category);
            if (!tab) return;

            this.activeTab = category;
            this.items = tab.cmds;
            this.select(0);
            this.scrollActiveTabIntoView();
        },

        highlight(name, typed) {
            const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
            if (!typed) return esc(name);

            const idx = name.toLowerCase().indexOf(this.prefix + typed);
            if (idx === -1) return esc(name);

            const end = idx + this.prefix.length + typed.length;
            return esc(name.slice(0, idx))
                + "<mark>" + esc(name.slice(idx, end)) + "</mark>"
                + esc(name.slice(end));
        },

        hide() {
            this.visible = false;
            this.tabs = [];
            this.activeTab = "";
            this.items = [];
            this.selected = 0;
            this.selectedName = "";
        },

        land(index, dir) {
            const n = this.items.length;
            if (!n) return -1;

            let i = ((index % n) + n) % n;
            let guard = 0;
            while (this.items[i].spacer && guard++ < n) {
                i = (i + dir + n) % n;
            }

            return this.items[i].spacer ? -1 : i;
        },

        select(index) {
            const i = this.land(index, 1);
            if (i === -1) return;

            this.selected = i;
            this.selectedName = this.items[i].name;
        },

        move(delta) {
            const i = this.land(this.selected + delta, delta);
            if (i === -1) return;

            this.selected = i;
            this.selectedName = this.items[i].name;

            Alpine.nextTick(() => {
                const el = this.$refs.list?.querySelectorAll(".autocomplete-item")[this.selected];
                el?.scrollIntoView({ block: "nearest" });
            });
        },

        accept() {
            const cmd = this.items[this.selected];
            if (!cmd) return;

            Alpine.store("chat").user_input = cmd.name + " ";
            this.hide();
        },

        toggle(e) {
            if (!this.visible) return;

            if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); this.move(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); e.stopPropagation(); this.move(-1); }
            else if (e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); this.switchTab(1); }
            else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); this.switchTab(-1); }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); this.hide(); }
            else if (e.key === "Enter") {
                const cmd = this.items[this.selected];
                if (!cmd || cmd.spacer) { this.hide(); return; }

                e.preventDefault();
                e.stopPropagation();
                this.accept();
            }
        }
    };
}
