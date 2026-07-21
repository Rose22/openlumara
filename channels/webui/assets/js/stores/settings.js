SETTINGS_STORE = {
    // --- API State ---
    apiStatus: false,
    apiError: false,
    
    // --- Settings Data ---
    settings: {},
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
    moduleInfoCache: {},
    
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
        await this.load();
        await this.checkApiConnection();
    },

    async load() {
        this.loading = true;
        this.error = null;

        try {
            const rawSettings = await simpleApiFetch('/api/settings/load');
            this.settings = rawSettings;
            
            try {
                this.moduleInfoCache = await simpleApiFetch('/api/settings/get_module_info');
            } catch (infoErr) {
                console.warn('Failed to fetch module info:', infoErr);
            }

            this.categories = buildSettingsStructure(rawSettings, this.moduleInfoCache);
            this.originalCategories = JSON.parse(JSON.stringify(this.categories));
            this.changedModuleSettings.clear();

            this.showUnsafe = this.settings.channels.settings.webui.show_unsafe_settings;

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
            const backendData = flattenForBackend(this.categories);
            backendData.changed_modules = Array.from(this.changedModuleSettings);

            await simpleApiPost('/api/settings/save', backendData);

            // Reconnect API if API settings changed
            if (
                (JSON.stringify(this.categories.api) !== JSON.stringify(this.originalCategories.api))
            ) {
                try {
                    console.log("reconnecting API");
                    await simpleApiPost('/api/reconnect', {});
                    this.apiError = null;
                } catch (reconnectErr) {
                    this.apiError = reconnectErr;
                    console.warn('Reconnect failed:', reconnectErr);
                }
            }

            this.settings = backendData;
            this.originalCategories = JSON.parse(JSON.stringify(this.categories));
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
