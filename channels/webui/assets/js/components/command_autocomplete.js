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

/*
 * Spacer rows only make sense BETWEEN two real matches: leading ones would
 * dangle blank space above the first result and trailing ones below the
 * last, so pruning them keeps matches flush at the top of the list.
 */
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

        // fired from the textarea's @input only: real keystrokes open the
        // popup. deliberately NOT a reactive watcher - accept() mutates the
        // input store, and a reactive reopen raced the hide() right after
        // completion, leaving a blank popup that kept eating Enter presses.
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
            // pass 1: NAME matches only, everywhere. description matching is
            // a pure fallback: the moment a real name matches, description-
            // only results are irrelevant noise (/update must never share
            // the list with ...hard because its help text mentions restart)
            const names = [];
            let anyNameHit = false;

            for (const [category, cmds] of Object.entries(this.commands)) {
                const matches = [];

                for (const [name, desc] of Object.entries(cmds ?? {})) {
                    if (!name || name.startsWith("__SPACER__")) continue;

                    const lower = name.toLowerCase();
                    const target = this.prefix + typed;

                    // starts-with beats contains, shorter beats longer
                    let score = null;
                    if (lower.startsWith(target)) score = 200;
                    else if (lower.includes(target)) score = 150;

                    if (score !== null) {
                        matches.push({ name, desc: desc || category, nameHtml: this.highlight(name, typed), score: score - lower.length * 0.01 });
                    }
                }

                if (matches.length) {
                    anyNameHit = true;
                    // stable sort keeps equal-scored commands in their
                    // original CMD_DEFS order
                    matches.sort((a, b) => b.score - a.score);
                    names.push({ category, count: matches.length, cmds: matches });
                }
            }

            if (anyNameHit) { this.tabs = names; return; }

            // pass 2 (only when nothing matches by name): search descriptions
            const tabs = [];

            for (const [category, cmds] of Object.entries(this.commands)) {
                const matches = [];

                for (const [name, desc] of Object.entries(cmds ?? {})) {
                    // CMD_DEFS marks section breaks with "__SPACER__N" keys;
                    // other channels render them as blank lines. do the same:
                    // a dead row, never selectable. NOTE: the marker is the
                    // NAME, not an empty description - plenty of real
                    // commands (e.g. /update) simply have no help text.
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

        // when the strip overflows horizontally, arrow-cycling must keep the
        // active tab visible. inline-only: block scrolling would steal the
        // command list's own scroll position.
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

            // fill the input and close, period. the watch only runs on actual
            // text changes, so the popup stays gone until the next keystroke
            // (which is also how subcommands get offered again) and the next
            // Enter belongs to send, never to this popup.
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
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); this.hide(); }
            else if (e.key === "Enter") {
                // Enter belongs to the popup only while it has something to
                // complete. once the draft no longer matches any command
                // (only-spacer matches, stale selection, ...), nothing may be
                // claimed - the key falls through to send as if we weren't here
                const cmd = this.items[this.selected];
                if (!cmd || cmd.spacer) { this.hide(); return; }

                e.preventDefault();
                e.stopPropagation();
                this.accept();
            }
        }
    };
}
