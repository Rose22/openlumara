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

        // Theme state (synced with Alpine store)
        themeFamily: null,
        themeMode: null,

        // Font settings
        fontFamily: localStorage.getItem('fontFamily') || 'default',
        fontSize: localStorage.getItem('fontSize') || '16',
        chatWidth: localStorage.getItem('chatContentWidth') || '100',
        messageWidth: localStorage.getItem('messageMaxWidth') || '60',

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

            // Sync theme state with Alpine store
            this.themeFamily = Alpine.store('theme').family;
            this.themeMode = Alpine.store('theme').mode;
            
            // Listen for theme changes from other parts of the app
            document.addEventListener('theme-changed', (e) => {
                this.themeFamily = e.detail.family;
                this.themeMode = e.detail.mode;
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

                await this.fetchModels();

                const firstCategory = Object.keys(this.categories)[0];
                this.activeCategory = firstCategory;
            } catch (err) {
                console.error('Failed to load settings:', err);
                this.error = err.message || 'Failed to load settings';
            } finally {
                this.loading = false;
            }
        },

        async fetchModels() {
            try {
                this.cachedModels = await simpleApiFetch('/api/models');
                // Re-render any model inputs if settings are already loaded
                if (Object.keys(this.categories).length > 0) {
                    this.$dispatch('settings-loaded');
                }
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
        },

        /*
         * ### THEME SETTINGS ###
         */
        // Alpine-reactive theme toggle
        toggleThemeMode(isLight) {
            Alpine.store('theme').apply(this.themeFamily, isLight ? 'light' : 'dark');
        },
        
        // Alpine-reactive font change
        handleFontChange(font) {
            this.fontFamily = font;
            Alpine.store('theme').setFont(font);
        },
        
        // Alpine-reactive font size change
        handleFontSize(size) {
            this.fontSize = size;
            localStorage.setItem('fontSize', size);
            document.documentElement.style.setProperty('--font-size-base', `${size}px`);
        },
        
        // Alpine-reactive chat width change
        handleChatWidth(width) {
            this.chatWidth = width;
            localStorage.setItem('chatContentWidth', width);
            document.documentElement.style.setProperty('--chat-content-width', `${width}%`);
        },
        
        // Alpine-reactive message width change
        handleMessageWidth(width) {
            this.messageWidth = width;
            localStorage.setItem('messageMaxWidth', width);
            document.documentElement.style.setProperty('--message-max-width', `${width}%`);
        },
        
        // Alpine-reactive theme family selection
        selectThemeFamily(family) {
            this.themeFamily = family;
            Alpine.store('theme').apply(family, this.themeMode);
        },
        
        // Get theme families for x-for loop
        getThemeFamilies() {
            return Alpine.store('theme').getFamilies();
        },

        // Helper to get theme preview gradient
        getThemePreviewStyle(family) {
            if (!window.themes || !window.themes[family]) return '';
            const theme = window.themes[family];
            const colors = theme[this.themeMode] || theme['dark'];
            const bg = colors['--bg-primary'] || '#000';
            const accent = colors['--accent'] || '#fff';
            return `background: linear-gradient(135deg, ${bg} 50%, ${accent} 50%);`;
        },

        // Helper to format theme name
        formatThemeName(family) {
            return family.charAt(0).toUpperCase() + family.slice(1);
        }
    };
}
