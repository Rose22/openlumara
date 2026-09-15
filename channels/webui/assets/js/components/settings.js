function settingsModal() {
    return {
        // --- Navigation State ---
        activeCategory: null,
        activeModule: null,
        activeChannel: null,
        error: null,
        
        // --- Expansion State ---
        expanded: {
            modules: false,
            user_modules: false,
            channels: false,
            user_channels: false
        },
        
        // --- Viewport ---
        mobile: window.innerWidth <= 768,

        // Theme state (synced with Alpine store)
        themeFamily: localStorage.getItem('themeFamily') || 'monochrome',
        themeMode: localStorage.getItem('themeMode') || 'dark',

        // Font settings
        fontFamily: localStorage.getItem('fontFamily') || 'default',
        fontSize: localStorage.getItem('fontSize') || '16',
        chatWidth: localStorage.getItem('chatContentWidth') || '100',
        messageWidth: localStorage.getItem('messageMaxWidth') || '60',
        expandReasoning: localStorage.getItem('expandReasoning') || false,

        get activeNavCategory() {
            return this.activeModule ? 'modules' : 
                   this.activeChannel ? 'channels' : this.activeCategory;
        },

        // --- Init & Load ---
        init() {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
            // the resize + theme-changed listeners used to be attached here
            // with raw addEventListener. the modal is x-if now, so it
            // unmounts when closed - but these listeners were never removed,
            // leaking a fresh pair (pinning the dead component in memory)
            // on every single open. they now live as x-on bindings on the
            // modal root in settings/index.html, which Alpine tears down
            // together with the component.
            this.themeFamily = Alpine.store('theme').family;
            this.themeMode = Alpine.store('theme').mode;

            this.activeCategory = "appearance";
        },

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // called from @resize.window.debounce on the modal root
        checkMobile() {
            const newMobile = window.innerWidth <= 768;
            if (newMobile !== this.mobile) {
                this.mobile = newMobile;
            }
        },

        async closeAndSave() {
            // close the modal and save settings
            await Alpine.store('settings').saveSettings();
            await Alpine.store('ui').closeModal();
        },

        async switchCategory(cat) {
            // Auto-save settings to the backend when switching categories
            const settings = Alpine.store('settings');
            await settings.saveSettings();

            // Auto-fetch models if switching to the model category
            if (cat === 'model') {
                await settings.fetchModels();
            }

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

        updateSetting(settingObj, value) {
            settingObj.value = value;
            
            // Track changed modules
            const cat = this.activeCategory;
            const module = this.activeModule || this.activeChannel;
            if (cat && module && (cat.startsWith('modules') || cat.startsWith('user_modules'))) {
                Alpine.store('settings').changedModuleSettings.add(module);
            }
        },

        /**
         * Checks if a setting's dependency is satisfied.
         * @param {string|object} depends - Either a key path string (e.g., "some_field" or "parent.child") for truthy checks,
         *                                  or an object mapping keys to expected values (e.g., {"some_field": true, "other": "value"})
         * @returns {boolean} True if all dependencies are satisfied, or if depends is null/empty
         */
        checkDependency(depends) {
            if (!depends) return true;
            
            const settingsStore = Alpine.store('settings');
            const category = settingsStore.categories[this.activeCategory];
            
            if (!category) return true;
            
            let settings = null;
            
            // For modules/channels, settings are nested under the module/channel name
            if (this.activeModule || this.activeChannel) {
                const moduleName = this.activeModule || this.activeChannel;
                settings = category.settings?.[moduleName]?.value;
            } else {
                // For core config sections, settings are directly under category.settings
                settings = category.settings;
            }
            
            if (!settings) return true;
            
            // Handle object format: {"field_name": expected_value, "nested.field": 42}
            if (typeof depends === 'object' && !Array.isArray(depends)) {
                for (const [keyPath, expectedValue] of Object.entries(depends)) {
                    const keys = keyPath.split('.');
                    let currentValue = settings;
                    
                    for (const key of keys) {
                        if (currentValue === undefined || currentValue === null) return false;
                        currentValue = currentValue[key]?.value;
                    }
                    
                    if (currentValue !== expectedValue) return false;
                }
                return true;
            }
            
            // Handle string format (backward compatible): "field_name" or "parent.child"
            // Checks if the value is truthy
            const keys = depends.split('.');
            let currentValue = settings;
            
            for (const key of keys) {
                if (currentValue === undefined || currentValue === null) return false;
                currentValue = currentValue[key]?.value;
            }
            
            return !!currentValue;
        },

        /**
         * Builds a hierarchical structure from flat settings for nested rendering.
         * @returns {Array} Array of {setting, children: []} objects
         */
        getHierarchicalSettings() {
            const settingsStore = Alpine.store('settings');
            const category = settingsStore.categories[this.activeCategory];
            
            if (!category) return [];
            
            let settings = null;
            
            // For modules/channels, settings are nested under the module/channel name
            if (this.activeModule || this.activeChannel) {
                const moduleName = this.activeModule || this.activeChannel;
                settings = category.settings?.[moduleName]?.value;
            } else {
                // For core config sections, settings are directly under category.settings
                settings = category.settings;
            }
            
            if (!settings) return [];
            
            // Build hierarchical structure
            const hierarchical = [];
            const childrenMap = new Map();
            
            // First pass: identify parents and children
            for (const [key, setting] of Object.entries(settings)) {
                if (setting.unsafe && !settingsStore.showUnsafe) continue;
                
                const depends = setting.depends;
                let parentKey = null;
                
                if (depends) {
                    if (typeof depends === 'string') {
                        // Simple dependency - use the dependency key as parent
                        parentKey = depends.split('.')[0]; // Handle nested deps like "parent.child"
                    } else if (typeof depends === 'object' && !Array.isArray(depends)) {
                        // Object dependency - use first key as parent
                        const firstKey = Object.keys(depends)[0];
                        parentKey = firstKey.split('.')[0];
                    }
                }
                
                if (parentKey && settings[parentKey]) {
                    // This setting is dependent on another
                    if (!childrenMap.has(parentKey)) {
                        childrenMap.set(parentKey, []);
                    }
                    childrenMap.get(parentKey).push({ key, setting });
                } else {
                    // This setting is a parent or has no dependencies
                    hierarchical.push({ key, setting, children: [] });
                }
            }
            
            // Second pass: attach children to parents
            for (const [parentKey, children] of childrenMap) {
                const parent = hierarchical.find(h => h.key === parentKey);
                if (parent) {
                    parent.children = children;
                }
            }
            
            return hierarchical;
        },

        /*
         * ### THEME SETTINGS ###
         */
        // Alpine-reactive theme toggle
        async toggleThemeMode(isLight) {
            await Alpine.store('theme').apply(this.themeFamily, isLight ? 'light' : 'dark');
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
        async selectThemeFamily(family) {
            this.themeFamily = family;
            await Alpine.store('theme').loadThemeFamily(family);
            Alpine.store('theme').apply(family, this.themeMode);
        },
        
        // Get grouped theme families for dropdown
        getThemeFamilies() {
            return Alpine.store('theme').getFamilies();
        },

        // Get group names
        getThemeGroups() {
            return Alpine.store('theme').getGroupNames();
        },

        // Get group display name
        getThemeGroupName(groupKey) {
            return Alpine.store('theme').getGroupName(groupKey);
        },

        // Helper to get theme preview gradient
        getThemePreviewStyle(family) {
            const themeData = Alpine.store('theme').themeCache[family];
            if (!themeData) return '';
            const colors = themeData[this.themeMode] || themeData['dark'];
            const bg = colors['--bg-primary'] || '#000';
            const accent = colors['--accent'] || '#fff';
            return `background: linear-gradient(135deg, ${bg} 50%, ${accent} 50%);`;
        },

        // Helper to format theme name (remove group prefix, replace hyphens with spaces)
        formatThemeName(family) {
            const parts = family.split('-');
            // Skip the first part (group prefix) and join the rest with spaces
            const displayName = parts.length > 1 ? parts.slice(1).join(' ') : parts[0];
            // Capitalize first letter
            return displayName.charAt(0).toUpperCase() + displayName.slice(1);
        },

        // Check if theme has a specific mode variant
        themeHasMode(mode) {
            const themeData = Alpine.store('theme').themeCache[this.themeFamily];
            if (!themeData) return true; // Assume available if not loaded yet
            return !!themeData[mode];
        }
    };
}
