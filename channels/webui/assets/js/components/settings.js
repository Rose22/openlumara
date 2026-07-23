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
        themeFamily: null,
        themeMode: null,

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

            this.activeCategory = "appearance";
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
