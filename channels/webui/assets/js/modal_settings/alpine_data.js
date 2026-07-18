function settingsModal() {
    return {
        // --- UI State ---
        loading: false,
        error: null,
        
        // --- Settings Data ---
        settings: {},
        original: {},
        changedModuleSettings: new Set(),
        categoryDescriptions: {},
        fieldDescriptions: {},
        
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
            return JSON.stringify(this.settings) !== JSON.stringify(this.original);
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
            // Listen for viewport changes
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
                // Load settings
                const settings = await simpleApiFetch('/api/settings/load');
                this.settings = settings;
                this.original = JSON.parse(JSON.stringify(settings));
                this.changedModuleSettings.clear();

                // Load module info (gracefully)
                try {
                    this.moduleInfoCache = await simpleApiFetch('/api/settings/get_module_info');
                } catch (infoErr) {
                    console.warn('Failed to fetch module info:', infoErr);
                }

                console.log(this.moduleInfoCache);

                // Organize into categories
                this.categories = organizeSettingsIntoCategories(
                    this.settings, 
                    this.moduleInfoCache, 
                    this.categoryDescriptions,
                    this.fieldDescriptions
                );

                // Load first category
                const firstCategory = Object.keys(this.categories)[0];
                this.activeCategory = firstCategory;

                // Pre-fetch models if needed
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

        // --- Settings Operations ---
        async saveSettings() {
            this.loading = true;
            this.error = null;

            try {
                await simpleApiPost('/settings/save', this.settings);
                this.original = JSON.parse(JSON.stringify(this.settings));
                this.changedModuleSettings.clear();
            } catch (err) {
                this.error = err.message || 'Failed to save settings';
            } finally {
                this.loading = false;
            }
        },

        resetSettingsForm() {
            this.settings = JSON.parse(JSON.stringify(this.original));
            this.changedModuleSettings.clear();
        },

        handleChange(key, value) {
            // Set value at dot-notation path
            const parts = key.split('.');
            let current = this.settings;
            
            for (let i = 0; i < parts.length - 1; i++) {
                if (!(parts[i] in current)) {
                    current[parts[i]] = {};
                }
                current = current[parts[i]];
            }
            current[parts[parts.length - 1]] = value;

            // Track changed modules
            if (key.startsWith('modules.') || key.startsWith('user_modules.')) {
                const moduleMatch = key.match(/^(modules|user_modules)\.(.*?)\./);
                if (moduleMatch) {
                    this.changedModuleSettings.add(moduleMatch[2]);
                }
            }
        },

        // --- Navigation ---
        switchCategory(cat) {
            this.activeCategory = cat;
            this.activeModule = null;
            this.activeChannel = null;

            // Expand/collapse sub-lists
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
        },

        visibleItems(cat) {
            const category = this.categories[cat];
            if (!category || !category.groups) return [];

            const directGroup = category.groups.get('_direct_');
            if (!directGroup || !directGroup.items.length) return [];

            const item = directGroup.items[0];
            if (item.type !== 'toggle_list') return [];

            const allItems = getAllToggleItems(item.value);
            const enabledSet = new Set(item.value.enabled);

            return allItems.filter(name => {
                if (!enabledSet.has(name)) return false;
                
                // Only show items that have settings
                const settingsKey = `${cat}.settings.${name}`;
                return category.groups.has(settingsKey);
            });
        },

        sortedGroups(groups) {
            if (!groups) return [];
            return Array.from(groups.entries())
                .sort(([a], [b]) => {
                    // Sort _direct_ groups last
                    if (a === '_direct_') return 1;
                    if (b === '_direct_') return -1;
                    return 0;
                });
        }
    };
}
