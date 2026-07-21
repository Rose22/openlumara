UI_STORE = {
    errors: [],
    currentModal: null,
    notice: null,
    systemLogs: [],

    async openModal(name) {
        if (this.currentModal === 'settings') {
            // auto-save the settings when switching to a different modal
            await Alpine.store('settings').saveSettings();
        }
        this.currentModal = name;
    },
    async closeModal() {
        this.currentModal = null;
    },

    async reloadLogs() {
        this.systemLogs = await simpleApiFetch("/api/system/logs");
    }
}
