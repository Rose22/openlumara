function settingsModal() {
    return {
        // --- UI State ---
        loading: false,
        error: null,
        
        // --- Settings Data ---
        settings: {},
        originalCategories: {},
        changedModuleSettings: new Set(),
        
        // --- Navigation State ---
        activeCategory: null,
        activeModule: null,
        activeChannel: null,
        categories: {},
        
        // --- Expansion State ---
        expanded: {
            modules: false,
            user_modules: false,
            channels: false,
            user_channels: false
        },
        
        // --- Feature Flags ---
        showUnsafe: localStorage.getItem('showUnsafeSettings') === 'true',
        
        // --- Model Cache ---
        cachedModels: null,
        modelsLoadError: null,
        moduleInfoCache: {},
        
        // --- Viewport ---
        mobile: window.innerWidth <= 768,

        // --- Computed Getters ---
        get hasChanges() {
            return JSON.stringify(this.categories) !== JSON.stringify(this.originalCategories);
        },

        get activeNavCategory() {
            return this.activeModule ? 'modules' : 
                   this.activeChannel ? 'channels' : this.activeCategory;
        },

        get sortedCategories() {
            return Object.entries(this.categories)
                .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));
        },

        // --- Init & Load ---
        async init() {
            window.addEventListener('resize', () => {
                clearTimeout(this.resizeTimeout);
                this.resizeTimeout = setTimeout(() => {
                    const newMobile = window.innerWidth <= 768;
                    if (newMobile !== this.mobile) {
                        this.mobile = newMobile;
                    }
                }, 150);
            });

            await this.load();
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

                const firstCategory = Object.keys(this.categories)[0];
                this.activeCategory = firstCategory;

                if (checkForModelField(this.settings)) {
                    this.fetchModels().catch(e => console.warn("Model fetch failed:", e));
                }

            } catch (err) {
                console.error('Failed to load settings:', err);
                this.error = err.message || 'Failed to load settings';
            } finally {
                this.loading = false;
            }
        },

        async fetchModels() {
            try {
                const data = simpleApiFetch('/api/models');
                this.cachedModels = data.models || [];
                this.modelsLoadError = null;
            } catch (err) {
                console.error('Failed to fetch models:', err);
                this.modelsLoadError = err.message || 'Failed to fetch models';
            }
        },

        async saveSettings() {
            this.loading = true;
            this.error = null;

            try {
                const backendData = flattenForBackend(this.categories);
                await simpleApiPost('/api/settings/save', backendData);
                this.settings = backendData;
                this.originalCategories = JSON.parse(JSON.stringify(this.categories));
                this.changedModuleSettings.clear();
            } catch (err) {
                this.error = err.message || 'Failed to save settings';
            } finally {
                this.loading = false;
            }
        },

        resetSettingsForm() {
            this.categories = JSON.parse(JSON.stringify(this.originalCategories));
            this.changedModuleSettings.clear();
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

        updateSetting(settingObj, value) {
            settingObj.value = value;
            
            // Track changed modules
            const cat = this.activeCategory;
            const module = this.activeModule || this.activeChannel;
            if (cat && module && (cat.startsWith('modules') || cat.startsWith('user_modules'))) {
                this.changedModuleSettings.add(module);
            }
        },

        switchCategory(cat) {
            this.activeCategory = cat;
            this.activeModule = null;
            this.activeChannel = null;

            for (const key in this.expanded) {
                this.expanded[key] = (cat === key);
            }
        },

        selectItem(item, cat) {
            if (cat.includes('module')) {
                this.activeModule = item;
                this.activeChannel = null;
            } else {
                this.activeChannel = item;
                this.activeModule = null;
            }
        }
    };
}
