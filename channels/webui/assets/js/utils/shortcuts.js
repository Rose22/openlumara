/*
 * Shortcut definitions shared by the key handler (utils/keyboard_shortcuts.js)
 * and the settings UI (stores/keyboard.js).
 *
 * A binding is a canonical string: modifiers in fixed order (Ctrl, Alt, Shift)
 * plus a base key, e.g. "Ctrl+Shift+Y", "Alt+ArrowUp", "PageUp".
 * Ctrl and Cmd are treated as the same "Ctrl" modifier, so a layout saved on
 * macOS reads naturally on Windows and vice versa.
 */

const SHORTCUT_DEFS = [
    {
        id: 'scroll_up', label: 'Scroll chat up',
        description: 'Scroll the message view up by roughly one screen.',
        default: 'PageUp'
    },
    {
        id: 'scroll_down', label: 'Scroll chat down',
        description: 'Scroll the message view down by roughly one screen.',
        default: 'PageDown'
    },
    {
        id: 'prev_turn', label: 'Jump to previous message',
        description: 'Jump to the previous turn in the chat, highlighting it. Loads older turns as needed.',
        default: 'Alt+PageUp'
    },
    {
        id: 'next_turn', label: 'Jump to next message',
        description: 'Jump to the next turn in the chat, highlighting it.',
        default: 'Alt+PageDown'
    },
    {
        id: 'prev_chat', label: 'Previous chat',
        description: 'Switch to the previous chat in the sidebar list.',
        default: 'Alt+ArrowUp'
    },
    {
        id: 'next_chat', label: 'Next chat',
        description: 'Switch to the next chat in the sidebar list.',
        default: 'Alt+ArrowDown'
    },
    {
        id: 'prev_sidebar_tab', label: 'Previous sidebar tab',
        description: 'Switch to the previous tab in the sidebar strip, wrapping around.',
        default: 'Alt+Shift+PageUp'
    },
    {
        id: 'next_sidebar_tab', label: 'Next sidebar tab',
        description: 'Switch to the next tab in the sidebar strip, wrapping around.',
        default: 'Alt+Shift+PageDown'
    },
    {
        id: 'copy_last_assistant', label: 'Copy last reply',
        description: 'Copy the last assistant message to the clipboard.',
        default: 'Ctrl+Shift+Y'
    },
    {
        id: 'regenerate_last_assistant', label: 'Regenerate last reply',
        description: 'Regenerate the last assistant message.',
        default: 'Ctrl+Shift+G'
    },
    {
        id: 'command_palette', label: 'Command palette',
        description: 'Open the command palette, which reaches every action in the interface.',
        default: 'Ctrl+K'
    },
    {
        id: 'global_search', label: 'Global search',
        description: 'Open (or close) the global search dialog.',
        default: 'Ctrl+Space'
    },
    {
        id: 'toggle_sidebar', label: 'Toggle sidebar',
        description: 'Show or hide the sidebar.',
        default: 'Ctrl+B'
    }
];

/* combos the browser owns: handing them out would only produce confusion.
 * Ctrl+PageUp/PageDown belong here especially: Chrome switches tabs with them
 * and only surfaces them on keyup, so a page-level keydown handler never sees
 * them at all (they were the original turn-jump default for this reason). */
const BLOCKED_SHORTCUTS = [
    'Ctrl+N', 'Ctrl+W', 'Ctrl+T', 'Ctrl+Shift+N', 'Ctrl+Shift+T',
    'Ctrl+Shift+I', 'Ctrl+Shift+J', 'Ctrl+Shift+C', 'Ctrl+Tab', 'Ctrl+F5',
    'Ctrl+PageUp', 'Ctrl+PageDown'
];

/* previously-shipped defaults that are now known-bad, remapped on load so an
 * existing localStorage entry doesn't keep a dead binding forever */
const SHORTCUT_MIGRATIONS = {
    'Ctrl+PageUp': 'Alt+PageUp',
    'Ctrl+PageDown': 'Alt+PageDown'
};

const SHORTCUT_NAMED_KEYS = {
    ArrowUp: 'ArrowUp', ArrowDown: 'ArrowDown', ArrowLeft: 'ArrowLeft', ArrowRight: 'ArrowRight',
    PageUp: 'PageUp', PageDown: 'PageDown', Home: 'Home', End: 'End',
    Space: 'Space', Enter: 'Enter', Tab: 'Tab', Escape: 'Escape',
    Backspace: 'Backspace', Delete: 'Delete', Insert: 'Insert',
    Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Backslash: '\\',
    Semicolon: ';', Quote: "'", Comma: ',', Period: '.', Slash: '/', Backquote: '`',
    IntlBackslash: '\\'
};

for (let i = 1; i <= 12; i++) { SHORTCUT_NAMED_KEYS['F' + i] = 'F' + i; }

// keys that carry no meaning on their own while recording
const BARE_MODIFIER_KEYS = ['Control', 'Alt', 'Shift', 'Meta', 'OS'];

/* the base (non-modifier) half of a binding, derived from e.code so it is
 * layout independent for letters/digits and immune to Shift casing */
function shortcutBaseKey(e) {
    const code = e.code || '';

    if (/^Key[A-Z]$/.test(code)) return code.slice(3);
    if (/^Digit[0-9]$/.test(code)) return code.slice(5);
    if (/^Numpad([0-9])$/.test(code)) return 'Num' + code[6];
    if (SHORTCUT_NAMED_KEYS[code]) return SHORTCUT_NAMED_KEYS[code];

    if (e.key && e.key.length === 1) return e.key.toUpperCase();
    return null;
}

/*
 * canonical binding for a keyboard event, or null when the event carries no
 * usable base key (a bare modifier being pressed down).
 */
function shortcutFromEvent(e) {
    if (BARE_MODIFIER_KEYS.includes(e.key)) return null;

    const base = shortcutBaseKey(e);
    if (!base) return null;

    const mods = [];
    if (e.ctrlKey || e.metaKey) mods.push('Ctrl');
    if (e.altKey) mods.push('Alt');
    if (e.shiftKey) mods.push('Shift');

    return mods.concat(base).join('+');
}

/*
 * normalize a hand-written/persisted binding into the canonical form, so
 * stale or differently-ordered entries still match. returns null when the
 * binding is empty or no longer usable.
 */
function normalizeBinding(binding) {
    if (!binding || typeof binding !== 'string') return null;

    const parts = binding.split('+');
    const rawBase = parts.pop();
    if (!rawBase) return null;

    // run the base through the same canonicalizer a live key produces, so
    // "ctrl+y" and "Ctrl+Y" end up identical
    const base = shortcutBaseKey({ code: rawBase === ' ' ? 'Space' : rawBase, key: rawBase });
    if (!base) return null;

    const mods = [];
    for (const mod of parts) {
        const m = mod.toLowerCase();
        if (m === 'ctrl' || m === 'control' || m === 'meta' || m === 'cmd' || m === 'command') {
            if (!mods.includes('Ctrl')) mods.push('Ctrl');
        } else if (m === 'alt' || m === 'option') {
            if (!mods.includes('Alt')) mods.push('Alt');
        } else if (m === 'shift') {
            if (!mods.includes('Shift')) mods.push('Shift');
        } else {
            return null;
        }
    }

    return mods.concat(base).join('+');
}

/* is this the element the user is typing into? */
function isEditableElement(el) {
    if (!el || !el.tagName) return false;
    if (el.isContentEditable) return true;
    return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName);
}

/* keys a focused field needs to function: they type a character, or they edit
 * the text around the caret. a bare binding on one of these can never be a
 * shortcut while typing, or that key would stop working in the field. */
const FIELD_EDIT_KEYS = ['Space', 'Enter', 'Tab', 'Backspace', 'Delete'];

/*
 * is this binding something that would be typed INTO a field rather than a
 * command? bare navigation keys (PageUp, PageDown, arrows, Home, End) are
 * commands and must keep firing while the message box has focus - only a bare
 * text/edit key is ambiguous enough to have to stand down.
 */
function isTypingBinding(binding) {
    if (!binding) return false;
    if (binding.includes('+')) return false;  // any modifier makes it a chord
    if (binding.length === 1) return true;    // a letter, digit or symbol
    if (/^Num/.test(binding)) return true;    // numpad digits also type text
    return FIELD_EDIT_KEYS.includes(binding);
}

// human-readable form: "Ctrl+Shift+Y" -> "Ctrl + Shift + Y"
function formatBinding(binding) {
    if (!binding) return 'Unbound';
    return binding.split('+').join(' + ');
}
