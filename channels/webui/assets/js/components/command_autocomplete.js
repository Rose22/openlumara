/*
 * Slash-command autocomplete for the message input.
 *
 * Ported from the old webui's autocomplete.js: when the draft starts with the
 * configured command prefix (core -> cmd_prefix, usually "/"), a dropdown of
 * matching commands appears above the input, grouped by category (core and
 * one per module). The list is fetched once from the backend
 * (/api/command_prefix + /api/commands, which wrap core.commands.get_commands)
 * and filtered live as the user types. Arrow keys move the selection, Enter
 * completes it (capture phase, so it wins over send-on-Enter), Escape or a
 * click outside hides it.
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
        groups: [],         // filtered, per category: { category, cmds: [{name, desc, nameHtml}] }
        items: [],          // same matches flattened, for keyboard navigation
        selected: 0,
        selectedName: "",   // which item the highlight follows (across the nested x-for)
        justAccepted: false,  // suppress the dropdown right after a completion, until typing continues

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

        // the single reactive entry point: wired to the textarea via x-effect,
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

            // keep the dropdown closed right after a completion; a further
            // keystroke (e.g. a space for subcommands) reopens it as usual
            if (this.justAccepted) {
                if (value === this.items[this.selected]?.name) return;
                this.justAccepted = false;
            }

            this.filter(value.slice(this.prefix.length).toLowerCase());
            if (!this.items.length) { this.hide(); return; }

            this.selected = 0;
            this.selectedName = this.items[0].name;
            this.visible = true;
        },

        filter(typed) {
            const groups = [];
            const flat = [];

            for (const [category, cmds] of Object.entries(this.commands)) {
                const matches = [];

                for (const [name, desc] of Object.entries(cmds ?? {})) {
                    if (!name) continue;  // blank spacer entries in CMD_DEFS

                    const lower = name.toLowerCase();
                    const descLower = (desc ?? "").toLowerCase();

                    if (lower.startsWith(this.prefix + typed) || descLower.includes(typed)) {
                        matches.push({ name, desc: desc ?? "", nameHtml: this.highlight(name, typed) });
                    }
                }

                if (matches.length) {
                    groups.push({ category, cmds: matches });
                    flat.push(...matches);
                }
            }

            this.groups = groups;
            this.items = flat;
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
            this.groups = [];
            this.items = [];
            this.selected = 0;
            this.selectedName = "";
        },

        select(index) {
            if (!this.items.length) return;
            this.selected = (index + this.items.length) % this.items.length;
            this.selectedName = this.items[this.selected].name;
        },

        move(delta) {
            this.select(this.selected + delta);

            Alpine.nextTick(() => {
                document.querySelector(".autocomplete-item.selected")
                    ?.scrollIntoView({ block: "nearest" });
            });
        },

        accept() {
            const cmd = this.items[this.selected];
            if (!cmd) return;

            this.justAccepted = true;
            Alpine.store("chat").user_input = cmd.name + " ";
            this.hide();
        },

        // capture-phase key handling from the textarea: while the dropdown is
        // open, these keys belong to it, never to send/history/navigation
        toggle(e) {
            if (!this.visible) return;

            if (e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); this.move(1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); e.stopPropagation(); this.move(-1); }
            else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); this.accept(); }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); this.hide(); }
        }
    };
}
