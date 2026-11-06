SETTINGS_STORE = {
    // --- API State ---
    apiStatus: false,
    apiError: false,
    
    // --- Settings Data ---
    originalCategories: {},
    changedModuleSettings: new Set(),
    categories: {},

    activeCategory: null,
    loading: false,

    // --- Error State ---
    // error: full-page load failure | saveError: dismissible banner at the
    // top of the settings page, fed by the server's refusal messages
    error: null,
    saveError: null,
    
    // --- Feature Flags ---
    showUnsafe: false,
    
    // --- Model Cache ---
    cachedModels: null,
    modelsLoadError: null,

    systemPrompt: '',
    
    // --- Computed Getters ---
    get hasChanges() {
        return JSON.stringify(this.categories) !== JSON.stringify(this.originalCategories);
    },

    get sortedCategories() {
        return Object.entries(this.categories)
            .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));
    },

    get groupedSubItems() {
        return (cat, enabledOnly = false) => {
            const catData = this.categories[cat];
            if (!catData || !catData.enabled) return [];

            const moduleCategories = catData.moduleCategories || {};
            const pool = enabledOnly ? [...catData.enabled] : [...catData.enabled, ...catData.disabled];
            const visible = pool.filter(item =>
                this.showUnsafe || !(catData.unsafeModules || {})[item]
            );

            const groups = {};
            for (const item of visible) {
                const label = moduleCategories[item] || "Other";
                if (!groups[label]) groups[label] = [];
                groups[label].push(item);
            }

            const sorted = Object.entries(groups).sort(([a], [b]) => {
                if (a === "Other") return 1;
                if (b === "Other") return -1;
                return a.localeCompare(b);
            });

            const hideLabels = sorted.length === 1 && sorted[0][0] === "Other";
            return sorted.map(([label, items]) => ({
                label: hideLabels ? "" : label,
                items
            }));
        };
    },

    // --- Init & Load ---
    async init() {
        // admin lockdown: the settings endpoints are blocked server-side,
        // so skip loading them entirely instead of erroring on 403s.
        if (window.ADMIN_SETTINGS_DISABLED) return;

        await this.load();
        await this.checkApiConnection();
    },

    async load() {
        this.loading = true;
        this.error = null;
        this.saveError = null;

        try {
            const payload = await simpleApiFetch('/api/settings/load');

            this.categories = payload.categories;
            this.originalCategories = JSON.parse(JSON.stringify(this.categories));
            this.changedModuleSettings.clear();

            this.showUnsafe = payload.show_unsafe_settings;

            this.systemPrompt = await simpleApiFetch("/api/chat/prompt");

            await this.checkApiConnection();
        } catch (err) {
            console.error('Failed to load settings:', err);
            this.error = err.message || 'Failed to load settings';
        } finally {
            this.loading = false;
        }
    },

    async checkApiConnection() {
        // get API connection status
        try {
            this.apiStatus = await simpleApiFetch("/api/check_connection");

            if (this.apiStatus) {
                this.modelsLoadError = null;
            }
        } catch (e) {
           this.apiStatus = false;
        }
    },

    async fetchModels() {
        console.log("fetching models..");

        this.loading = true;

        try {
            this.cachedModels = await simpleApiFetch('/api/models');
            this.modelsLoadError = null;
        } catch (err) {
            console.error('Failed to fetch models:', err);
            this.modelsLoadError = err || 'Failed to fetch models';
            this.cachedModels = null;
        }

        this.loading = false;
    },

    async saveSettings() {
        this.loading = true;
        this.error = null;
        this.saveError = null;

        console.log("saving settings to server..");

        try {
            const result = await simpleApiPost('/api/settings/save', {
                categories: JSON.parse(JSON.stringify(this.categories)),
                changed_modules: Array.from(this.changedModuleSettings)
            });

            // restart server if enabled modules/channels changed
            if (result?.requires_restart) {
                console.log("restarting server..");
                this.originalCategories = JSON.parse(JSON.stringify(this.categories));
                this.changedModuleSettings.clear();

                await Alpine.store('system').restart("Restarting the server to apply your changes..");
                return;
            }

            // Reconnect API if API settings changed
            else if (result?.requires_reconnect) {
                try {
                    console.log("reconnecting API");
                    await simpleApiPost('/api/reconnect', {});
                    this.apiError = null;
                } catch (reconnectErr) {
                    this.apiError = reconnectErr;
                    console.warn('Reconnect failed:', reconnectErr);
                }
            }

            this.originalCategories = JSON.parse(JSON.stringify(this.categories));

            // re-fetch system prompt
            this.systemPrompt = await simpleApiFetch("/api/chat/prompt");

            // handle localstorage settings
            const ui = Alpine.store('ui');
            localStorage.setItem('expandReasoning', ui.expandReasoning);

            this.changedModuleSettings.clear();
        } catch (err) {
            this.saveError = (err && err.message) ? err.message : (err || 'Failed to save settings');
        } finally {
            this.loading = false;
        }
    },

    resetChanges() {
        const restore = (target, source) => {
            for (const key of Object.keys(target)) {
                if (!(key in source)) continue;
                const t = target[key];
                const s = source[key];
                const bothObj = t && s && typeof t === 'object' && typeof s === 'object';
                if (bothObj && !Array.isArray(t) && !Array.isArray(s)) {
                    restore(t, s);
                } else if (t !== s) {
                    // deep-copy so later edits never touch the snapshot
                    target[key] = (s && typeof s === 'object') ? JSON.parse(JSON.stringify(s)) : s;
                }
            }
        };
        restore(this.categories, this.originalCategories);

        this.changedModuleSettings.clear();
        this.error = null;
        this.saveError = null;
        this.apiError = null;
    },

    toggleEnabled(category, itemName) {
        const cat = this.categories[category];
        if (!cat) return;

        const isEnabled = cat.enabled.includes(itemName);
        
        if (isEnabled) {
            // Disable: remove from enabled, add to disabled
            cat.enabled = cat.enabled.filter(item => item !== itemName);
            cat.disabled.push(itemName);
        } else {
            // Enable: remove from disabled, add to enabled
            cat.disabled = cat.disabled.filter(item => item !== itemName);
            cat.enabled.push(itemName);
        }
        
        // Sort for consistency
        cat.enabled.sort();
        cat.disabled.sort();
    },

}
