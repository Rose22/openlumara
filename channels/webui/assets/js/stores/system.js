SYSTEM_STORE = {
    logs: [],
    running: true,
    restarting: false,
    message: '',

    async restart(message = 'Restarting server..') {
        this.message = message || "Restarting server..";
        this.restarting = true;
        await simpleApiPost("/api/system/restart");
        this.restarting = false;
    },

    async reloadLogs() {
        this.logs = await simpleApiFetch("/api/system/logs");
    }
}
