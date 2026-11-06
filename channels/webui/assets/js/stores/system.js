SYSTEM_STORE = {
    data: {},
    logs: [],
    running: true,
    restarting: false,
    message: '',

    async restart(message = 'Restarting server..') {
        this.message = message || "Restarting server..";
        this.restarting = true;

        try {
            await simpleApiPost("/api/system/restart");
        } catch (e) {
            // expected: the server dies while handling the request.
            // the websocket reconnect in services/websockets.js reloads
            // the page once the server is back, so keep the overlay up.
            if (window.socket && window.socket.readyState === WebSocket.OPEN) {
                // server survived the call: this was a real failure
                this.restarting = false;
                this.message = String(e);
            }
            return;
        }

        // request completed: the server is about to go down and the page
        // reloads itself on reconnect, so leave restarting=true here
    },

    async loadData() {
        // admin lockdown: logs are only shown in the (disabled) settings
        // modal and the endpoint is blocked, so skip them. /api/system/data
        // stays open since the context pill needs max_context from it.
        if (!window.ADMIN_SETTINGS_DISABLED) {
            // logs are best-effort: a refusal (403/401 for remote or
            // unauthenticated callers) must never break the load chain
            try {
                this.logs = await simpleApiFetch("/api/system/logs");
            } catch (e) {
                this.logs = [];
            }
        }
        this.data = await simpleApiFetch("/api/system/data");
    }
}
