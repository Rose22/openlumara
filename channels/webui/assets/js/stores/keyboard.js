
const SHORTCUT_STORAGE_KEY = 'chatKe***)';
const SHORTCUT_ENABLED_KEY = 'chatShortcutsEnabled';

KEYBOARD_STORE = {
    defs: SHORTCUT_DEFS,

    bindings: {},
    enabled: true,

    recording: null,
    message: null,
    _recorder: null,
    _clickCanceller: null,

    init() {
        this.enabled = localStorage.getItem(SHORTCUT_ENABLED_KEY) !== 'false';
        this.bindings = this._load();
    },

    _load() {
        let saved = {};
        try {
            const parsed = JSON.parse(localStorage.getItem(SHORTCUT_STORAGE_KEY) || '{}');
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) { saved = parsed; }
        } catch (err) {
            saved = {};
        }

        const bindings = {};
        for (const def of SHORTCUT_DEFS) { bindings[def.id] = def.default; }

        for (const [id, combo] of Object.entries(saved)) {
            if (!(id in bindings)) continue;

            if (combo === '') { bindings[id] = ''; continue; }

            let normalized = normalizeBinding(combo);
            if (!normalized) continue;

            if (BLOCKED_SHORTCUTS.includes(normalized) && SHORTCUT_MIGRATIONS[normalized]) {
                normalized = SHORTCUT_MIGRATIONS[normalized];
            }

            bindings[id] = normalized;
        }

        return bindings;
    },

    persist() {
        localStorage.setItem(SHORTCUT_STORAGE_KEY, JSON.stringify(this.bindings));
    },

    setEnabled(on) {
        this.enabled = Boolean(on);
        localStorage.setItem(SHORTCUT_ENABLED_KEY, this.enabled);
    },

    defFor(id) {
        return SHORTCUT_DEFS.find(d => d.id === id) || null;
    },

    match(e) {
        if (!this.enabled) return null;

        const combo = shortcutFromEvent(e);
        if (!combo) return null;

        if (isTypingBinding(combo) && isEditableElement(e.target)) return null;

        for (const [id, binding] of Object.entries(this.bindings)) {
            if (binding && binding === combo) return id;
        }
        return null;
    },

    assign(id, combo) {
        const normalized = normalizeBinding(combo);
        if (!normalized) return;

        if (BLOCKED_SHORTCUTS.includes(normalized)) {
            this.message = { kind: 'error', text: formatBinding(normalized) + ' is reserved by the browser' };
            return;
        }

        const previous = this.bindings[id] || '';
        const owner = Object.keys(this.bindings).find(other => other !== id && this.bindings[other] === normalized);

        this.bindings[id] = normalized;

        if (owner) {
            this.bindings[owner] = previous;
            const ownerDef = this.defFor(owner);
            this.message = previous
                ? { kind: 'ok', text: 'Swapped with ' + (ownerDef ? ownerDef.label : owner) }
                : { kind: 'ok', text: 'Unbound from ' + (ownerDef ? ownerDef.label : owner) };
        } else {
            this.message = null;
        }

        this.persist();
    },

    clear(id) {
        this.bindings[id] = '';
        this.message = null;
        this.persist();
    },

    resetOne(id) {
        const def = this.defFor(id);
        if (!def) return;

        this.assign(id, def.default);
    },

    resetAll() {
        this.bindings = {};
        for (const def of SHORTCUT_DEFS) { this.bindings[def.id] = def.default; }

        this.message = { kind: 'ok', text: 'Restored the default shortcuts' };
        this.persist();
    },

    startRecording(id) {
        this.stopRecording();
        this.recording = id;
        this.message = null;

        const cancelOnClick = (e) => {
            if (e.target.closest && e.target.closest('[data-shortcut-control]')) return;
            this.stopRecording();
        };

        const handler = (e) => {
            e.preventDefault();
            e.stopPropagation();

            if (e.key === 'Escape') { this.stopRecording(); return; }
            if (e.key === 'Backspace' || e.key === 'Delete') { this.clear(id); this.stopRecording(); return; }

            const combo = shortcutFromEvent(e);
            if (!combo) return;  

            this.assign(id, combo);
            this.stopRecording();
        };

        this._recorder = handler;
        this._clickCanceller = cancelOnClick;
        document.addEventListener('keydown', handler, true);
        document.addEventListener('click', cancelOnClick, true);
    },

    stopRecording() {
        if (this._recorder) document.removeEventListener('keydown', this._recorder, true);
        if (this._clickCanceller) document.removeEventListener('click', this._clickCanceller, true);
        this._recorder = null;
        this._clickCanceller = null;
        this.recording = null;
    },

    label(id) {
        return formatBinding(this.bindings[id]);
    }
};
