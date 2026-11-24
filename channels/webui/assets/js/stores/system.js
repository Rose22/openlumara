SYSTEM_STORE = {
    data: {},
    logs: [],
    running: true,
    restarting: false,
    message: '',

    // --- Updates (git-based, mirrors the updater module) ---
    update: {
        status: null,
        checking: false,
        updating: false,
        error: null,
        // installed user modules/channels: each {name, type, library,
        // commit, remote_commit, behind, update_available, note},
        // plus per-row UI state (error, updating)
        entries: [],
        // when the entry statuses were last fetched: the repo panels reuse
        // these results within a minute instead of refetching every repo
        checkedAt: null,

        get anyUpdates() {
            return Boolean(this.status && this.status.update_available)
                || (this.entries || []).some(e => e.update_available);
        },
    },

    async checkForUpdates() {
        if (this.update.checking || this.update.updating) return;
        this.update.checking = true;
        this.update.error = null;

        // core install and installed repos are independent checks: run them
        // together, and let one failing not wipe out the other's results
        try {
            this.update.status = await simpleApiFetch("/api/system/update_check");
        } catch (e) {
            this.update.status = null;
            this.update.error = typeof e === 'string' ? e : 'Update check failed';
        }

        try {
            const fresh = await simpleApiFetch("/api/system/entry_updates");
            // carry per-row errors over; re-checking replaces the statuses
            const oldErrors = {};
            for (const e of this.update.entries) {
                if (e.error) oldErrors[e.name] = e.error;
            }
            for (const e of fresh) {
                e.error = oldErrors[e.name] || null;
                e.updating = false;
            }
            this.update.entries = fresh;
            this.update.checkedAt = Date.now();
        } catch (e) {
            // keep whatever entry list we had; surface the failure as a note
            // on a placeholder row so the panel never looks silently empty
            if (!this.update.entries.length) {
                this.update.entries = [{
                    name: 'modules & channels', type: 'module', library: '',
                    update_available: false, error: typeof e === 'string' ? e : 'Entry update check failed',
                }];
            }
        } finally {
            this.update.checking = false;
        }
    },

    async updateEntry(entry) {
        if (entry.updating || this.update.updating) return;

        entry.updating = true;
        entry.error = null;

        let data = null;
        try {
            // not simpleApiPost: a refused update arrives as success=false
            // and must fall into the failure branch below
            data = (await (await fetch("/api/system/entry_update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: entry.name })
            })).json()).data;
        } catch (e) {
            entry.updating = false;
            entry.error = typeof e === 'string' ? e : 'Update failed';
            return;
        }

        if (data && data.restart_required) {
            // code changed on disk: the running server still holds the old
            // version, so restart for it to take effect. the row stays in
            // its Updating.. state: the page reloads before it could clear.
            this.restart("Restarting the server to load the updated " + data.kind + " '" + entry.name + "'");
            return;
        }

        entry.updating = false;
        entry.error = (typeof data === 'string') ? data : null;

        // re-check every entry's status (also refreshes the cache the repo
        // panels reuse, and clears this entry's behind count)
        try {
            const fresh = await simpleApiFetch("/api/system/entry_updates");
            this.update.entries = fresh;
            this.update.checkedAt = Date.now();
            const updated = fresh.find(x => x.name === entry.name);
            if (updated) Object.assign(entry, updated);
        } catch (e) {
            // status refresh is best-effort; the update itself succeeded
        }
    },

    async performUpdate() {
        if (!confirm('Update OpenLumara now? The server will restart automatically when it finishes.')) return;

        this.update.updating = true;
        // full-screen overlay while the update script runs server-side
        this.restart("Updating OpenLumara.. the server will restart when finished");

        let data = null;
        try {
            // not simpleApiPost: a refused update arrives as success=false
            // and must fall into the failure branch below
            data = (await (await fetch("/api/system/update", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}"
            })).json()).data;
            // request completed: the server restarts right now; the websocket
            // reconnect in services/websockets.js reloads the page once it's back
        } catch (e) {
            // network error: either the server died mid-request (the update
            // is installing) or it refused outright. if the websocket is
            // still open, the server survived: report the failure. else
            // keep the overlay up and let the reconnect reload the page.
            if (window.socket && window.socket.readyState === WebSocket.OPEN) {
                this.update.updating = false;
                this.restarting = false;
                this.update.error = typeof e === 'string' ? e : 'Update failed';
                this.checkForUpdates();
            }
            return;
        }

        if (typeof data === 'string' && data.includes('already running')) {
            this.update.updating = false;
            this.restarting = false;
            this.update.error = data;
        }
    },

    async updateAll() {
        if (!this.update.anyUpdates || this.update.updating) return;
        if (!confirm('Update OpenLumara and all outdated modules/channels? The server will restart automatically when it finishes.')) return;

        this.update.updating = true;
        this.restart("Updating everything.. the server will restart when finished");

        let resp = null;
        try {
            resp = await (await fetch("/api/system/update_all", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}"
            })).json();
        } catch (e) {
            // server died mid-request while restarting: keep the overlay up,
            // the websocket reconnect reloads the page. socket still open
            // means this was a real failure.
            if (window.socket && window.socket.readyState === WebSocket.OPEN) {
                this.update.updating = false;
                this.restarting = false;
                this.update.error = typeof e === 'string' ? e : 'Update failed';
                this.checkForUpdates();
            }
            return;
        }

        // structured response = nothing needed the restart after all:
        // lift the overlay and show whatever failed; a string response is
        // the update script's output, restart is underway, overlay stays.
        if (resp && resp.data && typeof resp.data === 'object') {
            this.update.updating = false;
            this.restarting = false;
            if ((resp.data.failed || []).length) {
                this.update.error = 'Some updates failed: ' + resp.data.failed.join(' | ');
            }
            this.checkForUpdates();
        }
    },

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
