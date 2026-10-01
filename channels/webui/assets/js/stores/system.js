SYSTEM_STORE = {
    data: {},
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

    async loadData() {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        // admin lockdown: logs are only shown in the (disabled) settings
        // modal and the endpoint is blocked, so skip them. /api/system/data
        // stays open since the context pill needs max_context from it.
        if (!window.ADMIN_SETTINGS_DISABLED) {
            this.logs = await simpleApiFetch("/api/system/logs");
        }
        this.data = await simpleApiFetch("/api/system/data");
    }
}
