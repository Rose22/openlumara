/*
 * notif.js — Browser push notifications
 * Uses the Web Notifications API to alert the user of new messages
 * when the browser tab is not in focus.
 */

const NOTIFY_STORE = {
    permission: "default",       // default | granted | denied
    enabled: false,              // user toggle

    async init() {
        // Read permission state
        if ("Notification" in window) {
            this.permission = Notification.permission;
        }

        // Check for stored preference
        try {
            const saved = localStorage.getItem("webui_notif_enabled");
            if (saved === "true") this.enabled = true;
        } catch {}

        // Listen for permission changes (user may grant later)
        if ("Notification" in window) {
            Notification.onpermissionchange = () => {
                this.permission = Notification.permission;
            };
        }

        await this.requestPermission();
    },

    async requestPermission() {
        if (!("Notification" in window)) {
            console.warn("Browser does not support notifications.");
            return false;
        }

        if (this.permission === "granted") return true;
        if (this.permission === "denied") {
            console.warn("Notification permission was denied.");
            return false;
        }

        try {
            this.permission = await Notification.requestPermission();
            if (this.permission === "granted") {
                localStorage.setItem("webui_notif_enabled", "true");
                this.enabled = true;
            }
            return this.permission === "granted";
        } catch (err) {
            console.error("Failed to request notification permission:", err);
            return false;
        }
    },

    async send(body, icon = "/favicon.ico") {
        if (!this.enabled) return false;
        if (this.permission !== "granted") return false;

        try {
            new Notification("OpenLumara", {
                body: body,
                icon: icon,
                badge: icon,
                tag: "openlumara",
                requireInteraction: false
            });
        } catch (err) {
            console.error("Failed to show notification:", err);
        }
    }
};
