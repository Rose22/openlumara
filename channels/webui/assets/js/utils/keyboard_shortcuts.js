/*
 * Chat keyboard navigation. Every shortcut is user-rebindable: the actual keys
 * come from $store.keyboard (persisted in localStorage, edited under
 * Settings -> Keyboard), this file only maps an action id to its behaviour.
 */

// the message view element, or null when no chat is showing (login page)
function chatMessagesEl() {
    return document.getElementById('messages');
}

// true when a modal dialog is covering the UI and owns the keyboard
function chatNavModalOpen() {
    return Boolean(Alpine.store('ui').currentModal);
}

/*
 * plain viewport scroll of the message view. works from anywhere on the page,
 * including while focus sits in the message input or inside a focused code
 * block: the chat is the one scroller these keys belong to.
 */
function scrollMessagesBy(deltaY) {
    const el = chatMessagesEl();
    if (!el) return false;

    el.scrollBy({ top: deltaY, behavior: 'smooth' });
    return true;
}

/*
 * the turn to navigate relative to: the last keyboard-jumped turn still in the
 * window, else the first turn (partially) visible in the viewport.
 */
function currentNavTurnIndex() {
    const messages = chatMessagesEl();
    if (!messages) return null;

    const chat = Alpine.store('chat');

    // the turn the last jump landed on. trusted only while it is still on
    // screen: once the user has scrolled it away, jumping continues from what
    // they are actually looking at rather than from an invisible anchor
    const starred = messages.querySelector('.turn.kb-nav-target');
    if (starred) {
        const idx = Number(starred.dataset.turnIndex);
        const containerRect = messages.getBoundingClientRect();
        const turnRect = starred.getBoundingClientRect();

        if (Number.isFinite(idx) &&
            turnRect.bottom > containerRect.top && turnRect.top < containerRect.bottom) {
            return idx;
        }

        starred.classList.remove('kb-nav-target');
    }

    const containerTop = messages.getBoundingClientRect().top;
    let best = null;
    for (const el of messages.querySelectorAll('.turn[data-turn-index]')) {
        if (el.getBoundingClientRect().bottom > containerTop) {
            best = Number(el.dataset.turnIndex);
            break;
        }
    }
    return best !== null ? best : chat.turnStart + chat.turnHistory.length - 1;
}

/*
 * hop one turn back/forward (Alt+PageUp/PageDown by default). older turns are
 * windowed out of the store, so hopping back may need to load a page first.
 */
async function jumpToAdjacentTurn(direction) {
    const chat = Alpine.store('chat');
    if (!chat.turnHistory.length) return;

    const ui = Alpine.store('ui');
    const current = currentNavTurnIndex();
    if (current === null) return;

    const target = direction < 0 ? current - 1 : current + 1;

    for (let guard = 0; guard < 10; guard++) {
        const rel = target - chat.turnStart;
        if (rel < 0) {
            if (!chat.hasMoreOlder || chat.loadingOlder) return;
            await chat.loadOlderTurns();
            await Alpine.nextTick();
            continue;
        }

        const turn = chat.turnHistory[rel];
        // a live turn streams at the very bottom and is being generated;
        // hopping past it lands on nothing
        if (!turn || (turn.live === true && direction > 0)) return;

        await ui.scrollToTurn(target);

        const el = document.querySelector(`[data-turn-index="${target}"]`);
        if (el) {
            // one target at a time: clear both markers everywhere, then force a
            // reflow so re-adding the flash class restarts the animation when
            // the same turn is jumped to twice in a row
            document.querySelectorAll('.turn.kb-nav-target, .turn.kb-turn-highlight')
                .forEach(e => e.classList.remove('kb-nav-target', 'kb-turn-highlight'));

            void el.offsetWidth;
            el.classList.add('kb-nav-target');
            el.classList.add('kb-turn-highlight');
        }
        return;
    }
}

/*
 * Alt+ArrowUp/Down: switch to the previous/next chat in the sidebar's
 * current ordering (visibleGroups: active time tab, or search results).
 */
async function goToAdjacentChat(direction) {
    const chat = Alpine.store('chat');
    const ui = Alpine.store('ui');

    const flat = [];
    for (const group of chat.visibleGroups()) {
        for (const c of (group.chats ?? [])) { flat.push(c); }
    }
    if (flat.length < 2) { ui.toast('No other chats to switch to'); return; }

    let idx = flat.findIndex(c => c.id === chat.selectedChat);
    if (idx === -1) {
        // current chat not in the list: ArrowDown goes to the newest, ArrowUp the oldest
        await chat.loadChat(direction < 0 ? flat[0].id : flat[flat.length - 1].id);
        return;
    }

    idx += direction;
    if (idx < 0 || idx >= flat.length) {
        ui.toast(direction < 0 ? 'Newest chat' : 'Oldest chat');
        return;
    }

    await chat.loadChat(flat[idx].id);
}

/*
 * the last assistant turn that can be copied/regenerated (skips live turns,
 * whose copy/regenerate buttons are disabled while streaming anyway)
 */
function lastAssistantTurnIndex() {
    const chat = Alpine.store('chat');
    for (let i = chat.turnHistory.length - 1; i >= 0; i--) {
        const turn = chat.turnHistory[i];
        if (turn && turn.role === 'assistant' && turn.live !== true) {
            return chat.turnStart + i;
        }
    }
    return null;
}

/*
 * action id -> behaviour. Adding a shortcut means adding a def in
 * utils/shortcuts.js and a handler here.
 */
function shortcutHandlers() {
    const ui = () => Alpine.store('ui');

    return {
        scroll_up: () => scrollMessagesBy(-window.innerHeight * 0.85),
        scroll_down: () => scrollMessagesBy(window.innerHeight * 0.85),

        prev_turn: () => jumpToAdjacentTurn(-1),
        next_turn: () => jumpToAdjacentTurn(1),

        prev_chat: () => goToAdjacentChat(-1),
        next_chat: () => goToAdjacentChat(1),

        prev_sidebar_tab: () => ui().cycleSidebarTab(-1),
        next_sidebar_tab: () => ui().cycleSidebarTab(1),

        copy_last_assistant: async () => {
            const turnIndex = lastAssistantTurnIndex();
            if (turnIndex === null) { ui().toast('No assistant message to copy'); return; }

            const ok = await Alpine.store('chat').copyMessage(turnIndex);
            ui().toast(ok ? 'Copied last message to clipboard' : 'Copy failed');
        },

        regenerate_last_assistant: async () => {
            if (Alpine.store('stream').state !== 'idle') { ui().toast('Wait for the current stream to finish'); return; }

            const turnIndex = lastAssistantTurnIndex();
            if (turnIndex === null) { ui().toast('No assistant message to regenerate'); return; }

            await Alpine.store('chat').regenerateMessage(turnIndex);
        },

        global_search: () => {
            if (ui().currentModal === 'global_search') ui().closeModal();
            else ui().openModal('global_search');
        },

        toggle_sidebar: () => ui().toggleSidebar(),

        // lives outside $store.ui.currentModal so it can open on top of any
        // dialog, and toggling it closed from inside works too
        command_palette: () => Alpine.store('palette').toggle()
    };
}

/*
 * the only actions allowed while a modal is open: global search so Ctrl+Space
 * can still dismiss the dialog it opened, the sidebar toggle, which lives
 * outside the dialog either way, and the command palette, which renders above
 * dialogs and is the one keyboard route that still works behind one.
 */
const MODAL_SAFE_ACTIONS = ['global_search', 'toggle_sidebar', 'command_palette'];

/*
 * the command palette owns the plain keyboard: it is an overlay, not a
 * modal, so these chat-bound actions must stand down while it is open -
 * most importantly PageUp/PageDown, which would otherwise scroll the chat
 * behind the palette (and the palette re-binds those keys for its own list
 * scrolling). modal-safe actions keep working: the palette itself, sidebar,
 * global search.
 */
const PALETTE_BLOCKED_ACTIONS = [
    'scroll_up', 'scroll_down', 'prev_turn', 'next_turn',
    'copy_last_assistant', 'regenerate_last_assistant'
];

/*
 * dialogs that already carry their own @keydown.escape.window handling:
 * global_search (toggle + dismiss), move_chat, and every module-contributed
 * modal (we can't know their internals, so they keep owning their Escape).
 * the global closer below covers the rest - most importantly settings,
 * closing it through its dirty-state prompt rather than around it.
 */
const MODAL_ESCAPE_NATIVE = ['global_search', 'move_chat'];

async function registerKeyboardShortcuts() {
    document.addEventListener('keydown', async (e) => {
        // while rebinding, the recorder (capture phase) owns the keyboard -
        // Escape there cancels the recording, it must never close the modal
        if (Alpine.store('keyboard').recording) return;

        // Esc closes whatever dialog is open (settings included: its own
        // unsaved-changes prompt runs through close()). Modals with their own
        // escape.window listeners close themselves, so stand down for those;
        // and when Escape is bound to a modal-safe action (e.g. the palette
        // toggle) that handler owns the key instead
        if (e.key === 'Escape') {
            const ui = Alpine.store('ui');
            const escAction = ui.currentModal && Alpine.store('keyboard').match(e);
            if (ui.currentModal && !MODAL_ESCAPE_NATIVE.includes(ui.currentModal) &&
                !(escAction && MODAL_SAFE_ACTIONS.includes(escAction))) {
                e.preventDefault();

                if (ui.currentModal === 'settings') {
                    // go through the component so unsaved changes get their
                    // save/don't-save prompt instead of being discarded
                    const root = document.querySelector('.settings-modal');
                    const data = root && Alpine.$data ? Alpine.$data(root) : null;
                    if (data && typeof data.close === 'function') await data.close();
                    else await ui.closeModal();
                } else {
                    await ui.closeModal();
                }
            }
            // fall through: the palette is not a modal, its own window
            // listener handles Escape while it is visible
        }

        const actionId = Alpine.store('keyboard').match(e);
        if (!actionId) return;

        // shortcuts fire wherever focus happens to be on the page (input box,
        // a code block, a button, nothing at all) - a modal is the exception
        if (chatNavModalOpen() && !MODAL_SAFE_ACTIONS.includes(actionId)) return;

        // ...and so are chat-scoped actions while the command palette has
        // the keyboard (see PALETTE_BLOCKED_ACTIONS)
        if (Alpine.store('palette').visible && PALETTE_BLOCKED_ACTIONS.includes(actionId)) return;

        const handler = shortcutHandlers()[actionId];
        if (!handler) return;

        // a bound shortcut should never also trigger what the browser would
        // have done with those keys; unbound actions never reach this point
        e.preventDefault();

        await handler(e);
    });
}
