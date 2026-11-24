
function chatMessagesEl() {
    return document.getElementById('messages');
}

function chatNavModalOpen() {
    return Boolean(Alpine.store('ui').currentModal);
}

function scrollMessagesBy(deltaY) {
    const el = chatMessagesEl();
    if (!el) return false;

    el.scrollBy({ top: deltaY, behavior: 'smooth' });
    return true;
}

function currentNavTurnIndex() {
    const messages = chatMessagesEl();
    if (!messages) return null;

    const chat = Alpine.store('chat');

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
        if (!turn || (turn.live === true && direction > 0)) return;

        await ui.scrollToTurn(target);

        const el = document.querySelector(`[data-turn-index="${target}"]`);
        if (el) {
            document.querySelectorAll('.turn.kb-nav-target, .turn.kb-turn-highlight')
                .forEach(e => e.classList.remove('kb-nav-target', 'kb-turn-highlight'));

            void el.offsetWidth;
            el.classList.add('kb-nav-target');
            el.classList.add('kb-turn-highlight');
        }
        return;
    }
}

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

        command_palette: () => Alpine.store('palette').toggle()
    };
}

const MODAL_SAFE_ACTIONS = ['global_search', 'toggle_sidebar', 'command_palette'];

const PALETTE_BLOCKED_ACTIONS = [
    'scroll_up', 'scroll_down', 'prev_turn', 'next_turn',
    'copy_last_assistant', 'regenerate_last_assistant'
];

const MODAL_ESCAPE_NATIVE = ['global_search', 'move_chat'];

async function registerKeyboardShortcuts() {
    document.addEventListener('keydown', async (e) => {
        if (Alpine.store('keyboard').recording) return;

        if (e.key === 'Escape') {
            const ui = Alpine.store('ui');
            const escAction = ui.currentModal && Alpine.store('keyboard').match(e);
            if (ui.currentModal && !MODAL_ESCAPE_NATIVE.includes(ui.currentModal) &&
                !(escAction && MODAL_SAFE_ACTIONS.includes(escAction))) {
                e.preventDefault();

                if (ui.currentModal === 'settings') {
                    const root = document.querySelector('.settings-modal');
                    const data = root && Alpine.$data ? Alpine.$data(root) : null;
                    if (data && typeof data.close === 'function') await data.close();
                    else await ui.closeModal();
                } else {
                    await ui.closeModal();
                }
            }
        }

        const actionId = Alpine.store('keyboard').match(e);
        if (!actionId) return;

        if (chatNavModalOpen() && !MODAL_SAFE_ACTIONS.includes(actionId)) return;

        if (Alpine.store('palette').visible && PALETTE_BLOCKED_ACTIONS.includes(actionId)) return;

        const handler = shortcutHandlers()[actionId];
        if (!handler) return;

        e.preventDefault();

        await handler(e);
    });
}
