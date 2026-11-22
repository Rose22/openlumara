/*
 * Keyboard shortcut store.
 *
 * Bindings live in localStorage only (like the other browser-side prefs in
 * Appearance): every change applies instantly and survives a reload, with no
 * server round trip and no restart required.
 */

const SHORTCUT_STORAGE_KEY = 'chatKe***)';
const SHORTCUT_ENABLED_KEY = 'chatShortcutsEnabled';

KEYBOARD_STORE = {
    defs: SHORTCUT_DEFS,

    // action id -> canonical binding ('' means unbound)
    bindings: {},
    enabled: true,

    // action id whose binding is currently being captured
    recording: null,
    // inline notice shown above the list: { kind: 'ok'|'error', text }
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

        // start from the defaults so shortcuts added in a later version are
        // never missing, then overlay whatever the user recorded
        const bindings = {};
        for (const def of SHORTCUT_DEFS) { bindings[def.id] = def.default; }

        for (const [id, combo] of Object.entries(saved)) {
            if (!(id in bindings)) continue;

            if (combo === '') { bindings[id] = ''; continue; }

            let normalized = normalizeBinding(combo);
            if (!normalized) continue;

            // a saved combo the browser swallows (e.g. the old Ctrl+PageUp
            // turn-jump default) gets remapped instead of kept dead
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

    /*
     * the action (if any) this key event triggers. exact modifier matching: a
     * binding for Alt+PageUp must not fire on Alt+Shift+PageUp.
     */
    match(e) {
        if (!this.enabled) return null;

        const combo = shortcutFromEvent(e);
        if (!combo) return null;

        // a bare text/edit binding (a lone "K", or bare Backspace) must not
        // fire while the user is typing, or that key becomes unusable in the
        // field. bare navigation keys are commands and fire regardless.
        if (isTypingBinding(combo) && isEditableElement(e.target)) return null;

        for (const [id, binding] of Object.entries(this.bindings)) {
            if (binding && binding === combo) return id;
        }
        return null;
    },

    /*
     * bind an action to a combo. a combo already owned by another action is
     * swapped out of it (like VS Code), so no shortcut ever goes silently
     * missing - the notice says which action gave it up.
     */
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

        // reclaim the default combo from whoever took it, then restore it
        this.assign(id, def.default);
    },

    resetAll() {
        this.bindings = {};
        for (const def of SHORTCUT_DEFS) { this.bindings[def.id] = def.default; }

        this.message = { kind: 'ok', text: 'Restored the default shortcuts' };
        this.persist();
    },

    /*
     * capture the next chord pressed anywhere. listens in the capture phase
     * and swallows the event, so the shortcut being recorded can't also fire.
     */
    startRecording(id) {
        this.stopRecording();
        this.recording = id;
        this.message = null;

        // clicking anywhere outside the recording row drops the capture, so a
        // stray click can't leave a recording armed for the next keypress
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
            if (!combo) return;  // still waiting for a real key after the modifiers

            this.assign(id, combo);
            this.stopRecording();
        };

        this._recorder = handler;
        this._clickCanceller = cancelOnClick;
        document.addEventListener('keydown', handler, true);
        // a click (not pointerdown) so the row's own handlers still run first
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
