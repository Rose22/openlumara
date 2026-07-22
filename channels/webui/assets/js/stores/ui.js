UI_STORE = {
    scrollThreshold: 100,
    errors: [],
    currentModal: null,
    notice: null,

    async openModal(name) {
        if (this.currentModal === 'settings') {
            // auto-save the settings when switching to a different modal
            await Alpine.store('settings').saveSettings();
        }

        this.currentModal = name;

        /*
         * post-open actions
         */

        if (name === 'logs') {
            // scroll down to the bottom
            await Alpine.nextTick();

            const el = document.getElementById('log-container');
            if (el) el.scrollTop = el.scrollHeight;
        }
    },
    async closeModal() {
        this.currentModal = null;
    },

    /*
     * Called from @scroll on the messages container.
     * Toggles shouldScroll based on whether the user is near the bottom.
     */
    onScroll(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        const wasAtBottom = this.shouldScroll;

        if (distFromBottom < this.scrollThreshold) {
            this.shouldScroll = true;
        } else {
            this.shouldScroll = false;
        }
    },

    async scrollToBottom(containerId = 'messages') {
        if (!this.shouldScroll) return;

        const el = document.getElementById(containerId);
        if (!el) return;

        Alpine.nextTick(() => {
            el.scrollTop = el.scrollHeight;
        });
    },

    async forceScrollToBottom(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        Alpine.nextTick(() => {
            el.scrollTop = el.scrollHeight;
            this.shouldScroll = true;
        });
    },
}
