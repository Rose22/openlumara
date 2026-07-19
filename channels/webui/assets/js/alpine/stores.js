let STREAM_STORE = {
    // one of: idle, sending, processing, streaming
    state: 'idle',

    // stores raw token data
    tokens: [],
    processing: {},

    async clearTokens() {
        this.tokens = [];
        this.processing = [];
    }
}

THEME_STORE = {
    family: localStorage.getItem('themeFamily') || 'monochrome',
    mode: localStorage.getItem('themeMode') || 'dark',

    // Load themes from API if not already loaded
    async init() {
        if (!window.themes) {
            try {
                const response = await fetch('/themes.js');
                const text = await response.text();
                eval(text);
            } catch (e) {
                console.error('Failed to load themes:', e);
                window.themes = {};
            }
        }
        this.apply(this.family, this.mode);
    },

    // Apply theme - this is the core reactive function
    apply(family, mode) {
        if (!window.themes || !window.themes[family]) {
            console.error('Theme family not found:', family);
            return;
        }

        const themeData = window.themes[family];

        // Handle mode fallback
        if (!themeData[mode]) {
            const alternateMode = mode === 'dark' ? 'light' : 'dark';
            if (themeData[alternateMode]) {
                mode = alternateMode;
            } else {
                mode = 'dark';
            }
        }

        const finalTheme = themeData[mode];
        const root = document.documentElement;

        // Reset to base vars
        for (const [varName, value] of Object.entries(BASE_THEME_VARS)) {
            root.style.setProperty(varName, value);
        }

        // Apply theme vars
        for (const [varName, value] of Object.entries(finalTheme)) {
            root.style.setProperty(varName, value);
        }

        // Update state
        this.family = family;
        this.mode = mode;

        // Persist
        localStorage.setItem('themeFamily', family);
        localStorage.setItem('themeMode', mode);

        // Dispatch event for other components to react
        document.dispatchEvent(new CustomEvent('theme-changed', {
            detail: { family, mode }
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
            root.style.setProperty('--font-family', `'${font}', sans-serif`);
            root.style.setProperty('--code-font', `'${font}', monospace`);
        } else {
            root.style.setProperty('--font-family', "Arial, sans-serif");
        }
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

    // Get theme families for UI
    getFamilies() {
        const families = {};
        const themes = window.themes || {};
        
        for (const family in themes) {
            const themeData = themes[family];
            families[family] = {
                dark: !!themeData.dark,
                light: !!themeData.light
            };
        }
        
        return families;
    }
}

// Base theme variables for reset
const BASE_THEME_VARS = {
    '--radius-sm': '4px',
    '--radius-md': '8px',
    '--radius-lg': '12px',
    '--radius-xl': '16px',
    '--bg-pattern': 'none',
    '--bg-pattern-size': '24px 24px',
    '--message-decoration': 'none',
    '--avatar-shape': '50%'
};
