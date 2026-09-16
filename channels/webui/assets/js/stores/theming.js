THEME_STORE = {
    family: localStorage.getItem('themeFamily') || 'monochrome',
    mode: localStorage.getItem('themeMode') || 'dark',
    themeCache: {},  // Cache for loaded theme data
    themeList: [],   // List of available theme families

    init() {
        // Load theme list (just names and modes) - async, doesn't block
        fetch('/api/themes')
            .then(r => r.json())
            .then(data => { this.themeList = data; })
            .catch(e => console.error('Failed to load themes:', e));

        // Load base theme and current theme family - async, will apply when ready
        this.loadThemeFamily('base').then(() => {
            this.loadThemeFamily(this.family).then(() => {
                this.apply(this.family, this.mode);
            });
        });

    },

    // Load a specific theme family if not already cached
    async loadThemeFamily(family) {
        if (this.themeCache[family]) {
            return this.themeCache[family];
        }

        try {
            const response = await fetch(`/api/themes/${family}`);
            if (!response.ok) {
                throw new Error(`Failed to load theme: ${response.statusText}`);
            }
            this.themeCache[family] = await response.json();
            return this.themeCache[family];
        } catch (e) {
            console.error(`Failed to load theme family '${family}':`, e);
            return null;
        }
    },

    apply(family, mode) {
        const themeData = this.themeCache[family];
        if (!themeData) {
            console.error('Theme family not found:', family);
            return;
        }

        // Handle mode fallback
        let effectiveMode = mode;
        if (!themeData[mode]) {
            const alternateMode = mode === 'dark' ? 'light' : 'dark';
            if (themeData[alternateMode]) {
                effectiveMode = alternateMode;
            } else {
                effectiveMode = 'dark';
            }
        }

        const finalTheme = themeData[effectiveMode];
        const root = document.documentElement;

        // Apply base theme vars first
        const baseTheme = this.themeCache['base'];
        if (baseTheme) {
            for (const [varName, value] of Object.entries(baseTheme)) {
                root.style.setProperty(varName, value);
            }
        }

        // apply font family
        const fontFam = localStorage.getItem('fontFamily');
        if (fontFam) {
            this.setFont(fontFam);
        }

        // apply font size
        const fontSize = localStorage.getItem('fontSize') || 16;
        root.style.setProperty('--font-size-base', `${fontSize}px`);

        // apply chat width
        const chatWidth = localStorage.getItem('chatContentWidth') || 100;
        root.style.setProperty('--chat-content-width', `${chatWidth}%`);
        
        // apply message bubble width
        const messageWidth = localStorage.getItem('messageMaxWidth') || 70;
        root.style.setProperty('--message-max-width', `${messageWidth}%`);

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // streamed-token fade duration: keep the CSS animation duration in
        // sync with the user setting (the JS timeline reads the same keys)
        const fadeEnabled = localStorage.getItem('tokenFadeEnabled') !== 'false';
        const fadeMs = parseInt(localStorage.getItem('tokenFadeMs'), 10);
        root.style.setProperty('--token-fade-duration',
            `${fadeEnabled && !Number.isNaN(fadeMs) ? fadeMs : TOKEN_FADE_DEFAULT_MS}ms`);

        // Apply theme vars on top of base
        if (finalTheme) {
            for (const [varName, value] of Object.entries(finalTheme)) {
                root.style.setProperty(varName, value);
            }
        }

        // Switch code syntax highlighting theme based on mode
        const codeThemeLink = document.getElementById('code-theme');
        if (codeThemeLink) {
            codeThemeLink.href = effectiveMode === 'dark'
                ? '/assets/css/code-themes/github-dark.css'
                : '/assets/css/code-themes/github-light.css';
        }

        // Update state
        this.family = family;
        this.mode = effectiveMode;

        // Persist
        localStorage.setItem('themeFamily', family);
        localStorage.setItem('themeMode', effectiveMode);

        // Dispatch event for other components to react
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
        // dispatched on window (was document) so the settings modal can
        // listen via @theme-changed.window, which Alpine auto-removes when
        // the modal unmounts (document-level listeners leaked per modal open)
        window.dispatchEvent(new CustomEvent('theme-changed', {
            detail: { family, mode: effectiveMode }
        }));
    },

    // Toggle mode (dark/light)
    toggleMode() {
        this.apply(this.family, this.mode === 'dark' ? 'light' : 'dark');
    },

    // Set font
    setFont(font) {
        const root = document.documentElement;
        localStorage.setItem('fontFamily', font);

        if (font && font !== 'default') {
            this.loadGoogleFont(font);
            root.style.setProperty('--font-primary', `'${font}', sans-serif`);
            root.style.setProperty('--code-font', `'${font}', monospace`);
        } else {
            root.style.setProperty('--font-primary', "Arial, sans-serif");
        }
    },
    
    // Set font size
    setFontSize(size) {
        localStorage.setItem('fontSize', size);

        const root = document.documentElement;
        root.style.setProperty('--font-size-base', `${size}px`);
    },

    // Load Google Font
    loadGoogleFont(fontName) {
        const id = `font-${fontName.replace(/\s+/g, '-').toLowerCase()}`;
        if (document.getElementById(id)) return;

        const link = document.createElement('link');
        link.id = id;
        link.rel = 'stylesheet';
        link.href = `https://fonts.googleapis.com/css2?family=${fontName.replace(/ /g, '+')}:wght@400;500;600;700&display=swap`;
        document.head.appendChild(link);
    },

    // Get theme families for UI (grouped by prefix)
    getFamilies() {
        const groups = {};
        const others = [];
        
        for (const theme of this.themeList) {
            const themeInfo = {
                dark: theme.dark,
                light: theme.light
            };
            
            // Group by the word before the first hyphen
            const parts = theme.name.split('-');
            if (parts.length > 1) {
                const groupKey = parts[0].toLowerCase();
                if (!groups[groupKey]) {
                    groups[groupKey] = [];
                }
                groups[groupKey].push({ name: theme.name, ...themeInfo });
            } else {
                others.push({ name: theme.name, ...themeInfo });
            }
        }
        
        // Sort others alphabetically
        others.sort((a, b) => a.name.localeCompare(b.name));
        
        return { groups, others };
    },
    
    // Get sorted group names
    getGroupNames() {
        const families = this.getFamilies();
        return Object.keys(families.groups).sort();
    },
    
    // Get group name (capitalized)
    getGroupName(groupKey) {
        return groupKey.charAt(0).toUpperCase() + groupKey.slice(1);
    }
}
