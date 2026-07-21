UI_STORE = {
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

}
