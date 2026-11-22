/*
 * Command palette registry.
 *
 * Single source of truth for the actions the palette (js/components/command_palette.js)
 * can reach. Nothing about the command list is hardcoded into the palette UI:
 * the registry assembles it fresh every time the palette opens, from:
 *
 *   1. core commands    - defined below (guarded by runtime state, so they
 *                         disappear when the feature they drive is off)
 *   2. keyboard actions - every rebindable action in SHORTCUT_DEFS, using the
 *                         shared handlers from utils/keyboard_shortcuts.js
 *   3. settings         - one "Open <page>" command per settings category,
 *                         plus one per module/channel page
 *   4. sidebar tabs     - the chat-list tab plus every module-contributed panel
 *   5. DOM discovery    - any element marked with a `data-cmd` attribute
 *   6. modules          - window.openlumaraCommands.add({...}) from any webui
 *                         extension script
 *
 * A command: { id, label, run, group?, icon?, hint?, priority?, keyId? }
 * keyId links it to a keyboard-store action so its binding shows as a <kbd>.
 */

const CMD_SOURCES = [];

// commands registered at runtime by modules, keyed by id
const CMD_EXTRA = {};

/*
 * register a command from anywhere (modules use window.openlumaraCommands).
 * re-registering an id replaces the previous definition.
 */
function registerCommand(cmd) {
    if (!cmd || !cmd.id || typeof cmd.run !== 'function' || !cmd.label) return;
    CMD_EXTRA[cmd.id] = cmd;
}

// the fuzzy matcher shared by the palette: null = no match.
// substring hits beat subsequence hits, word-start hits beat mid-word ones.
function cmdMatchScore(query, label) {
    if (!query) return 1;

    const q = query.toLowerCase();
    const l = label.toLowerCase();

    const idx = l.indexOf(q);
    if (idx !== -1) {
        const wordStart = idx === 0 || /[\s(\-_/.]/.test(l[idx - 1]);
        return 200 - idx + (wordStart ? 40 : 0) + (l.length - q.length < 8 ? 15 : 0);
    }

    // subsequence walk: every query char must appear, in order
    let score = 50;
    let pos = -1;
    for (const ch of q) {
        if (ch === ' ') continue;
        const found = l.indexOf(ch, pos + 1);
        if (found === -1) return null;
        if (found !== pos + 1) score -= 2 + Math.min(8, found - pos - 1);
        pos = found;
    }
    return score > 0 ? score : null;
}

// -- 1. core commands ---------------------------------------------------------

function coreCommands() {
    const S = () => Alpine.store('settings');
    const U = () => Alpine.store('ui');
    const C = () => Alpine.store('chat');
    const streamIdle = () => Alpine.store('stream').state === 'idle';

    // opening a settings page: the modal is a component, so aim it through the
    // ui store (openModal's optional category arg); this fallback drives the
    // live component directly for whatever reason the store arg went unread
    const openSettings = async (cat) => {
        if (window.ADMIN_SETTINGS_DISABLED) { U().toast('Admin settings are disabled'); return; }

        await U().openModal('settings', cat);
        await Alpine.nextTick();
        requestAnimationFrame(() => {
            const root = document.querySelector('.settings-modal');
            const data = root && Alpine.$data ? Alpine.$data(root) : null;
            if (data && typeof data.activeCategory !== 'undefined') {
                if (data.activeCategory !== cat) data.switchCategory(cat);
            }
        });
    };

    const list = [
        {
            id: 'new_chat', label: 'New chat', group: 'Chat', icon: 'add',
            enabled: streamIdle,
            run: async () => {
                await C().newChat();
                if (U().isMobile) U().showSidebar = false;
            }
        },
        {
            id: 'clear_chat', label: 'Clear current chat', group: 'Chat', icon: 'clear', hint: 'Dangerous',
            enabled: () => streamIdle() && Boolean(C().selectedChat),
            run: async () => {
                if (!confirm('Clear this chat? All its messages will be deleted.')) return;
                await simpleSocketSend({ type: 'user_message', content: '/clear' });
            }
        },
        {
            id: 'export_chat', label: 'Export current chat', group: 'Chat', icon: 'download',
            enabled: () => Boolean(C().selectedChat),
            run: () => C().export()
        },
        {
            id: 'rename_chat', label: 'Rename current chat', group: 'Chat', icon: 'edit',
            enabled: () => Boolean(C().selectedChat),
            run: () => startRenameSelectedChat()
        },
        {
            id: 'move_chat', label: 'Move current chat to category', group: 'Chat', icon: 'folder',
            enabled: () => Boolean(C().selectedChat),
            run: async () => {
                // the modal drives itself off the chat object, like the sidebar menu does
                const chat = C();
                for (const group of chat.visibleGroups()) {
                    const found = (group.chats ?? []).find(c => c.id === chat.selectedChat);
                    if (found) { chat.moveChatTarget = found; break; }
                }
                if (!chat.moveChatTarget) return;
                await U().openModal('move_chat');
            }
        },
        {
            id: 'manage_categories', label: 'Manage categories', group: 'Chat', icon: 'layers',
            run: () => U().openModal('categories')
        },
        {
            id: 'stop_generation', label: 'Stop generation', group: 'Chat', icon: 'stop',
            enabled: () => !streamIdle(),
            run: () => stopActiveStream()
        },
        {
            id: 'scroll_bottom', label: 'Scroll to bottom', group: 'Chat', icon: 'scroll-bottom',
            run: () => U().forceScrollToBottom()
        },
        {
            id: 'toggle_sidebar', label: 'Toggle sidebar', group: 'Interface', icon: 'sidebar',
            run: () => U().toggleSidebar()
        },
        {
            id: 'collapse_sidebar', label: 'Collapse sidebar to rail', group: 'Interface', icon: 'panel-close',
            enabled: () => !U().isMobile && !U().sidebarCollapsed,
            run: () => U().setSidebarCollapsed(true)
        },
        {
            id: 'global_search', label: 'Global search', group: 'Interface', icon: 'search',
            run: () => {
                if (U().currentModal === 'global_search') U().closeModal();
                else U().openModal('global_search');
            }
        },
        {
            id: 'toggle_reasoning', label: 'Expand/collapse reasoning', group: 'Interface', icon: 'lightbulb',
            run: () => {
                U().expandReasoning = !U().expandReasoning;
                localStorage.setItem('expandReasoning', String(U().expandReasoning));
            }
        },
        {
            id: 'toggle_theme', label: () => Alpine.store('theme').mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode',
            group: 'Appearance', icon: 'sun-moon',
            run: () => Alpine.store('theme').apply(
                Alpine.store('theme').family,
                Alpine.store('theme').mode === 'dark' ? 'light' : 'dark'
            )
        },
        {
            id: 'open_logs', label: 'System logs', group: 'System', icon: 'clipboard',
            enabled: () => !window.ADMIN_SETTINGS_DISABLED,
            // logs are a settings page (system_logs), not a modal of their own
            run: () => openSettings('system_logs')
        },
        {
            id: 'restart_server', label: 'Restart server', group: 'System', icon: 'server', hint: 'Dangerous',
            enabled: () => !window.ADMIN_SETTINGS_DISABLED,
            run: async () => {
                if (!confirm('Restart the OpenLumara server?')) return;
                await Alpine.store('system').restart();
            }
        },
        {
            id: 'reload_page', label: 'Reload page', group: 'System', icon: 'reload',
            run: () => window.location.reload()
        }
    ];

    if (login_enabled_palette()) {
        list.push({
            id: 'logout', label: 'Log out', group: 'System', icon: 'logout',
            run: () => {
                if (confirm('Log out?')) window.location.href = '/logout';
            }
        });
    }

    // -- 3. settings pages: one command per category, plus module/channel pages
    if (!window.ADMIN_SETTINGS_DISABLED) {
        for (const [cat, data] of Object.entries(S().categories ?? {})) {
            list.push({
                id: 'settings_' + cat,
                label: 'Open settings: ' + (data.title ?? cat),
                hint: 'Settings', group: 'Open', icon: 'gear', priority: 3,
                run: () => openSettings(cat)
            });

            if (['modules', 'user_modules', 'channels', 'user_channels'].includes(cat) && Array.isArray(data.enabled)) {
                for (const item of [...data.enabled, ...(data.disabled ?? [])]) {
                    list.push({
                        id: 'settings_' + cat + '_' + item,
                        label: 'Open settings: ' + item,
                        hint: 'Module', group: 'Open', icon: 'wrench', priority: 4,
                        run: () => openModuleSettings(cat, item)
                    });
                }
            }
        }

        // -- model switching: the palette lazily pulls the cached model list
        const models = S().cachedModels;
        if (Array.isArray(models) && models.length > 0) {
            const current = S().categories?.model?.settings?.name?.value || '';
            for (const name of models) {
                if (name === current) continue;
                list.push({
                    id: 'model_' + name,
                    label: 'Switch model: ' + name,
                    hint: 'Model', group: 'Open', icon: 'cube', priority: 4,
                    run: () => setModelCommand(name)
                });
            }
        }
    }

    return list;
}

async function openModuleSettings(cat, item) {
    if (window.ADMIN_SETTINGS_DISABLED) { Alpine.store('ui').toast('Admin settings are disabled'); return; }

    await Alpine.store('ui').openModal('settings', cat);
    await Alpine.nextTick();
    requestAnimationFrame(() => {
        const root = document.querySelector('.settings-modal');
        const data = root && Alpine.$data ? Alpine.$data(root) : null;
        if (data && typeof data.selectItem === 'function') data.selectItem(item, cat);
    });
}

// mirrors components/model_switcher.js so header dropdown and palette agree
async function setModelCommand(name) {
    try {
        await simpleApiPost('/api/model/set', { name });
        const field = Alpine.store('settings').categories?.model?.settings?.name;
        if (field) field.value = name;
    } catch (err) {
        Alpine.store('ui').toast('Failed to switch model: ' + err);
    }
}

/*
 * drive the sidebar item's inline rename flow (same one the "..." menu uses),
 * falling back to a prompt when the item isn't rendered (collapsed group,
 * different category tab).
 */
async function startRenameSelectedChat() {
    const chat = Alpine.store('chat');
    const el = document.getElementById('chat-' + chat.selectedChat);
    const data = el && Alpine.$data ? Alpine.$data(el) : null;

    if (data && 'renaming' in data) {
        data.renaming = true;
        data.renameValue = chat.chat?.title ?? '';

        await Alpine.nextTick();
        const input = el.querySelector('.rename-input');
        if (input) { input.focus(); input.select(); }
        return;
    }

    const title = prompt('New chat title:');
    if (title && title.trim()) await chat.renameChat(chat.selectedChat, title.trim());
}

// the login template never ships the palette, so a baked flag lookup is enough
function login_enabled_palette() {
    return document.body.hasAttribute('data-login-enabled');
}

// -- 2. keyboard actions ------------------------------------------------------

const CMD_KB_GROUPS = {
    scroll_up: 'Chat view', scroll_down: 'Chat view',
    prev_turn: 'Messages', next_turn: 'Messages',
    copy_last_assistant: 'Messages', regenerate_last_assistant: 'Messages',
    prev_chat: 'Navigation', next_chat: 'Navigation',
    prev_sidebar_tab: 'Navigation', next_sidebar_tab: 'Navigation'
};

const CMD_KB_ICONS = {
    scroll_up: 'arrow-up', scroll_down: 'arrow-down',
    prev_turn: 'turn-up', next_turn: 'turn-down',
    copy_last_assistant: 'clipboard', regenerate_last_assistant: 'reload',
    prev_chat: 'chat-page', next_chat: 'chat-page',
    prev_sidebar_tab: 'sidebar', next_sidebar_tab: 'sidebar'
};

function keyboardCommands() {
    const handlers = shortcutHandlers();

    // command_palette lists itself via nothing; global_search/toggle_sidebar
    // have nicer core commands that link the binding themselves
    return Object.entries(handlers)
        .filter(([id]) => !['command_palette', 'global_search', 'toggle_sidebar'].includes(id))
        .map(([id, handler]) => {
            const def = Alpine.store('keyboard').defFor(id);
            return {
                id: 'kb_' + id,
                label: def ? def.label : id,
                hint: def ? 'Shortcut action' : undefined,
                group: CMD_KB_GROUPS[id] ?? 'Chat',
                icon: CMD_KB_ICONS[id] ?? 'keyboard',
                keyId: id,
                priority: 2,
                run: () => handler()
            };
        });
}

// -- 4. sidebar tabs ----------------------------------------------------------

function sidebarTabCommands() {
    const U = () => Alpine.store('ui');
    const list = [];

    for (const btn of document.querySelectorAll('.sidebar-tab-list .sidebar-tab[data-tab]')) {
        const tab = btn.dataset.tab;
        if (tab === '') continue;  // handled by the core "show chats" command

        const label = (btn.getAttribute('title') || tab).trim();
        list.push({
            id: 'sidebar_tab_' + tab,
            label: 'Show panel: ' + label,
            hint: 'Sidebar', group: 'Interface', icon: 'sidebar', priority: 2,
            run: () => {
                U().showSidebarPanel();
                U().setSidebarTab(tab);
            }
        });
    }

    return list;
}

// -- 5. DOM discovery -----------------------------------------------------------
/*
 * elements declare themselves palette commands with a data-cmd attribute:
 *
 *   <button data-cmd="My Thing" data-cmd-group="MyModule" data-cmd-icon="✨" ...>
 *
 * the element's own click handler runs, so anything clickable can become
 * reachable without registering anything in JS. scanned live on every palette
 * open, so elements added later are picked up too.
 */
const CMD_SCAN_ROOTS = ['#main-wrapper header', '#main-wrapper .sidebar-shell', '#main-wrapper #input'];

function domCommands() {
    const list = [];

    for (const selector of CMD_SCAN_ROOTS) {
        for (const el of document.querySelectorAll(selector + ' [data-cmd]')) {
            const label = (el.getAttribute('data-cmd') || '').trim();
            if (!label) continue;

            list.push({
                id: 'dom_' + label.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
                label,
                hint: el.getAttribute('data-cmd-hint') || undefined,
                group: el.getAttribute('data-cmd-group') || 'Modules',
                icon: el.getAttribute('data-cmd-icon') || 'sparkle',
                priority: 4,
                run: () => el.click()
            });
        }
    }

    return list;
}

// -- assembly -------------------------------------------------------------------

function collectCommands() {
    const sources = [
        () => keyboardCommands(),
        () => coreCommands(),
        () => sidebarTabCommands(),
        () => domCommands(),
        () => Object.values(CMD_EXTRA)
    ];

    const byId = new Map();

    for (const source of sources) {
        let cmds;
        try {
            cmds = source();
        } catch (err) {
            console.error('command palette: source failed', err);
            continue;
        }

        for (const cmd of cmds ?? []) {
            if (byId.has(cmd.id)) continue;  // first source wins

            // enabled() commands quietly drop out when their feature is off
            if (cmd.enabled) {
                try {
                    if (!cmd.enabled()) continue;
                } catch (err) {
                    continue;
                }
            }

            // labels may be functions (state-dependent text): resolve once
            if (typeof cmd.label === 'function') {
                try { cmd.label = cmd.label(); } catch (err) { continue; }
            }

            byId.set(cmd.id, cmd);
        }
    }

    return [...byId.values()];
}

// modules: window.openlumaraCommands.add({ id, label, run, group?, icon?, hint?, enabled? })
window.openlumaraCommands = {
    add: registerCommand,
    remove: (id) => { delete CMD_EXTRA[id]; },
    collect: collectCommands
};
