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

    get filteredSubItems() {
        return (cat) => {
            const catData = this.categories[cat];
            if (!catData || !catData.enabled) return [];
            return catData.enabled.filter(item => 
                this.showUnsafe || !catData.unsafeModules[item]
            );
        };
    },

    // --- Init & Load ---
    async init() {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        // admin lockdown: the settings endpoints are blocked server-side,
        // so skip loading them entirely instead of erroring on 403s.
        if (window.ADMIN_SETTINGS_DISABLED) return;

        await this.load();
        await this.checkApiConnection();
    },

    async load() {
        this.loading = true;
        this.error = null;

        try {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // the backend now returns the fully merged, render-ready
            // category tree (schemas + values), so the client-side
            // structure builder and the module-info round-trip are gone.
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

        console.log("saving settings to server..");

        try {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // send the (edited) category tree straight through; the
            // backend flattens it back into raw config itself, and now
            // also tells us whether the changes require a server restart
            // or an API reconnect (the client-side config diffing is gone)
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
            this.error = err.message || 'Failed to save settings';
        } finally {
            this.loading = false;
        }
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
