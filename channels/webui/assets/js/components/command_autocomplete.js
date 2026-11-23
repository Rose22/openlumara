/*
 * Slash-command autocomplete for the message input.
 *
 * Ported from the old webui's autocomplete.js: when the draft starts with the
 * configured command prefix (core -> cmd_prefix, usually "/"), a popup of
 * matching commands appears above the input. The list is fetched once from
 * the backend (/api/command_prefix + /api/commands, which wrap
 * core.commands.get_commands) and filtered live as the user types. Matches
 * are grouped per category (core and one per module); the categories show up
 * as TABS in the popup header and only the active tab's commands are listed.
 *
 * Keys (claimed in capture phase, so they win over send-on-Enter):
 *   up/down    move through the active tab's commands
 *   left/right switch category tabs
 *   enter      complete the selected command
 *   esc        close the popup
 * A click outside closes it too.
 */
// the textarea lives in its own Alpine scope (chat/input.html), so handlers
// there reach this component through the live instance registered in init()
let CMD_AC = null;

function cmdAutocompleteInstance() { return CMD_AC; }

function commandAutocomplete() {
    return {
        prefix: "/",
        commands: {},       // { category: { "/cmd": "description" } }
        loaded: false,
        loading: false,
        attempted: false,
        visible: false,
        tabs: [],           // filtered per category: { category, count, cmds: [{name, desc, nameHtml, spacer?}] }
        activeTab: "",      // category currently listed
        items: [],          // flattened cmds of the active tab (navigation space)
        selected: 0,
        selectedName: "",   // which row the highlight follows
        justAccepted: false,  // suppress the popup right after a completion, until typing continues

        init() {
            CMD_AC = this;
            this.load();
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

        // the single reactive entry point: wired to the input via x-effect,
        // so it also reacts to programmatic changes (input history recall etc.)
        watch(text) {
            // load once on startup; on failure, retry on the next keystroke
            if (!this.loaded) {
                if (!text?.startsWith(this.prefix) || this.attempted) return;
                this.attempted = true;
                this.load();
                return;
            }

            const value = (text ?? "").trim();
            if (!value.startsWith(this.prefix)) { this.hide(); return; }

            // keep the popup closed right after a completion; a further
            // keystroke (e.g. a space for subcommands) reopens it as usual
            if (this.justAccepted) {
                if (value === this.items[this.selected]?.name) return;
                this.justAccepted = false;
            }

            this.filter(value.slice(this.prefix.length).toLowerCase());

            if (!this.tabs.length) { this.hide(); return; }

            // keep the same tab while it still has matches, else fall back
            // to the first one with something in it
            let tab = this.tabs.find(t => t.category === this.activeTab && t.count > 0)
                ?? this.tabs.find(t => t.count > 0)
                ?? this.tabs[0];

            this.activeTab = tab.category;
            this.items = tab.cmds;
            this.select(0);
            this.visible = true;
        },

        filter(typed) {
            const tabs = [];

            for (const [category, cmds] of Object.entries(this.commands)) {
                const matches = [];
                let count = 0;

                for (const [name, desc] of Object.entries(cmds ?? {})) {
                    if (!name) continue;

                    // CMD_DEFS uses "__SPACER__N" keys with empty descriptions
                    // as section breaks; other channels render them as blank
                    // lines. do the same: a dead row, never selectable.
                    if (!desc) {
                        matches.push({ name, desc: "", spacer: true });
                        continue;
                    }

                    const lower = name.toLowerCase();
                    const descLower = desc.toLowerCase();

                    if (lower.startsWith(this.prefix + typed) || descLower.includes(typed)) {
                        matches.push({ name, desc, nameHtml: this.highlight(name, typed) });
                        count++;
                    }
                }

                if (count > 0) {
                    tabs.push({ category, count, cmds: matches });
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
        },

        pickTab(category) {
            const tab = this.tabs.find(t => t.category === category);
            if (!tab) return;

            this.activeTab = category;
            this.items = tab.cmds;
            this.select(0);
        },

        // <mark> the typed part inside the command name. both sides are
        // escaped first, so the result is safe for x-html.
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

        // land on a selectable row, walking in the direction of travel so an
        // upward move past a spacer never bounces back to where it started
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
            // exact landing spot (hover): nearest selectable either way
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

            // the list is a plain block scroller (the header sits outside it),
            // so nearest-neighbor scrolling behaves predictably again. the
            // item is picked by index, not by .selected, so duplicate command
            // names across categories can never target the wrong row.
            Alpine.nextTick(() => {
                const el = this.$refs.list?.querySelectorAll(".autocomplete-item")[this.selected];
                el?.scrollIntoView({ block: "nearest" });
            });
        },

        accept() {
            const cmd = this.items[this.selected];
            if (!cmd) return;

            this.justAccepted = true;
            Alpine.store("chat").user_input = cmd.name + " ";
            this.hide();
        },

        // capture-phase key handling from the textarea: while the popup is
        // open, these keys belong to it, never to send/history/navigation
        toggle(e) {
            if (!this.visible) return;

            if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); this.move(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); e.stopPropagation(); this.move(-1); }
            else if (e.key === "ArrowRight") { e.preventDefault(); e.stopPropagation(); this.switchTab(1); }
            else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); this.switchTab(-1); }
            else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); this.accept(); }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); this.hide(); }
        }
    };
}
