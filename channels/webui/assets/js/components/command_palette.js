
const PALETTE_RECENTS_KEY = 'commandPaletteRecents';
const PALETTE_MAX_RESULTS = 60;

const PALETTE = {
    visible: false,
    query: '',
    activeIndex: 0,
    rows: [],
    recents: [],

    toggle() {
        if (this.visible) this.close();
        else this.open();
    },

    async open() {
        this.visible = true;
        this.query = '';
        this.activeIndex = 0;

        try {
            this.recents = JSON.parse(localStorage.getItem(PALETTE_RECENTS_KEY) || '[]');
            if (!Array.isArray(this.recents)) this.recents = [];
        } catch (err) {
            this.recents = [];
        }

        if (!window.ADMIN_SETTINGS_DISABLED) {
            const settings = Alpine.store('settings');
            if (!settings.cachedModels || settings.cachedModels.length === 0) {
                settings.fetchModels().catch(() => {});
            }
        }

        this.rebuild();

        await Alpine.nextTick();
        const input = document.getElementById('command-palette-input');
        if (input) input.focus();
    },

    close() {
        this.visible = false;
        this.query = '';
    },

    rebuild() {
        let commands;
        try {
            commands = collectCommands();
        } catch (err) {
            console.error('command palette: collect failed', err);
            commands = [];
        }

        const q = this.query.trim();

        if (!q) {
            this.rows = this.rowsFor(this.grouped(commands), true);
        } else {
            const scored = [];
            for (const cmd of commands) {
                const score = cmdMatchScore(q, cmd.label);
                if (score === null) continue;

                const recency = this.recents.indexOf(cmd.id);
                const bonus = recency === -1 ? 0 : 30 - recency * 3;

                scored.push({ cmd, sort: score + bonus - (cmd.priority ?? 3) * 4 });
            }

            const sorted = scored
                .sort((a, b) => b.sort - a.sort)
                .slice(0, PALETTE_MAX_RESULTS)
                .map(s => s.cmd);

            this.rows = this.rowsFor([{ label: '', items: sorted }], false);
        }

        this.activeIndex = this.firstSelectable();
    },

    grouped(commands) {
        const rank = c => {
            const i = this.recents.indexOf(c.id);
            return i === -1 ? 99 : i;
        };

        const sorted = [...commands].sort((a, b) => {
            const ra = rank(a), rb = rank(b);
            if (ra !== rb) return ra - rb;

            const pa = a.priority ?? 3, pb = b.priority ?? 3;
            if (pa !== pb) return pa - pb;

            return a.label.localeCompare(b.label);
        });

        const groups = new Map();
        for (const cmd of sorted) {
            const label = cmd.group || 'Other';
            if (!groups.has(label)) groups.set(label, []);
            groups.get(label).push(cmd);
        }

        return [...groups.entries()].map(([label, items]) => ({ label, items }));
    },

    rowsFor(groups, withHeaders) {
        const rows = [];
        for (const group of groups) {
            if (withHeaders && group.label) {
                rows.push({ id: 'hdr-' + group.label, header: true, label: group.label });
            }
            for (const cmd of group.items) {
                rows.push({ id: cmd.id, cmd });
            }
        }
        return rows;
    },

    firstSelectable() {
        const i = this.rows.findIndex(r => !r.header);
        return i === -1 ? 0 : i;
    },

    pageStep() {
        const list = document.getElementById('cmd-list');
        if (!list || !this.rows.length) return 5;

        const rowH = list.scrollHeight / this.rows.length;
        return Math.max(2, Math.floor(list.clientHeight / rowH));
    },

    _lastMove: 0,

    move(delta) {
        const now = performance.now();
        if (now - this._lastMove < 50) return;
        this._lastMove = now;

        const selectable = this.rows.some(r => !r.header);
        if (!selectable) return;

        const paging = Math.abs(delta) > 1;
        let i = this.activeIndex;

        for (let guard = 0; guard < this.rows.length; guard++) {
            if (paging) {
                const next = i + delta;
                if (next < 0) { i = 0; break; }
                if (next >= this.rows.length) { i = this.rows.length - 1; break; }
                i = next;
            } else {
                i = (i + delta + this.rows.length) % this.rows.length;
            }

            if (!this.rows[i].header) break;
        }
        this.activeIndex = i;

        Alpine.nextTick(() => {
            const el = document.querySelector('.cmd-item.active');
            if (el) el.scrollIntoView({ block: 'nearest' });
        });
    },

    async runItem(cmd) {
        if (!cmd) return;

        this.recents = [cmd.id, ...this.recents.filter(r => r !== cmd.id)].slice(0, 8);
        localStorage.setItem(PALETTE_RECENTS_KEY, JSON.stringify(this.recents));

        this.close();

        try {
            await cmd.run();
        } catch (err) {
            console.error('command palette: command failed', cmd.id, err);
            Alpine.store('ui').toast('Command failed: ' + err);
        }
    },

    runActive() {
        this.runItem(this.rows[this.activeIndex]?.cmd);
    },

    keyFor(cmd) {
        const kb = Alpine.store('keyboard');
        const id = cmd.keyId ?? cmd.id;
        return kb.bindings[id] || '';
    }
};
