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
    },
    async closeModal() {
        this.currentModal = null;
    }
}
