THEME_STORE = {
    family: localStorage.getItem('themeFamily') || 'monochrome',
    mode: localStorage.getItem('themeMode') || 'dark',
    themeCache: {},  // Cache for loaded theme data
    themeList: [],   // List of available theme families
    themeCssStatus: {},

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

        // Apply base theme vars first. base.json is a small theme family
        // ({common, dark, light}): common holds the mode-independent values,
        // then the group for the mode in play. A legacy flat base.json is
        // still applied as-is in both modes.
        const baseTheme = this.themeCache['base'];
        if (baseTheme) {
            const baseGroups = ('common' in baseTheme)
                ? [baseTheme.common, baseTheme[effectiveMode]]
                : [baseTheme];
            for (const group of baseGroups) {
                for (const [varName, value] of Object.entries(group || {})) {
                    root.style.setProperty(varName, value);
                }
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

        // streamed-token fade duration
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

        // Button label: when the theme names its fill but not the label, derive
        // the label from the fill. Same rule in both modes, so no theme has to
        // repeat it and light themes with a saturated button keep a light label.
        if (!(finalTheme && '--button-text' in finalTheme)) {
            const label = this.buttonLabel();
            if (label) root.style.setProperty('--button-text', label);
        }

        // Switch code syntax highlighting theme based on mode
        const codeThemeLink = document.getElementById('code-theme');
        if (codeThemeLink) {
            codeThemeLink.href = effectiveMode === 'dark'
                ? '/assets/css/code-themes/github-dark.css'
                : '/assets/css/code-themes/github-light.css';
        }

        // apply this theme's sidecar css (themes/<family>.css), if it exists
        this.applyThemeCss(family);

        // Update state
        this.family = family;
        this.mode = effectiveMode;

        // Persist
        localStorage.setItem('themeFamily', family);
        localStorage.setItem('themeMode', effectiveMode);

        // Dispatch event for other components to react
        window.dispatchEvent(new CustomEvent('theme-changed', {
            detail: { family, mode: effectiveMode }
        }));
    },

    // Readable label for --button-bg: light text on saturated/dark fills, dark
    // text on pale ones. Uses the AVERAGE luminance of the fill's colour stops
    // so a gradient counts as a whole. Null when the value carries no colour
    // (then base's --button-text stays as the fallback).
    buttonLabel() {
        const raw = getComputedStyle(document.documentElement).getPropertyValue('--button-bg').trim();
        const stops = [];
        for (const m of raw.matchAll(/#([0-9a-f]{3,8})\b|rgba?\(([^)]+)\)/gi)) {
            if (m[1]) {
                let h = m[1];
                if (h.length === 3) h = h.split('').map(c => c + c).join('');
                if (h.length === 8) h = h.slice(0, 6);
                stops.push([0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255));
            } else {
                const parts = m[2].split(',').map(v => parseFloat(v));
                if (parts.length >= 3) stops.push(parts.slice(0, 3).map(v => v / 255));
            }
        }
        if (!stops.length) return null;
        const lin = (c) => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        const avg = stops
            .map(([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b))
            .reduce((a, b) => a + b, 0) / stops.length;
        return avg < 0.40 ? '#fafafa' : '#18181b';
    },

    // Apply a theme's sidecar CSS
    applyThemeCss(family) {
        const existing = document.getElementById('theme-css');

        // known to have no sidecar css: just make sure nothing is left over
        if (this.themeCssStatus[family] === false) {
            if (existing) existing.remove();
            return;
        }

        if (existing && existing.dataset.themeFamily === family) {
            return; // already applied (e.g. dark/light toggle)
        }
        if (existing) {
            existing.remove();
        }

        const link = document.createElement('link');
        link.id = 'theme-css';
        link.rel = 'stylesheet';
        link.dataset.themeFamily = family;
        link.onload = () => { this.themeCssStatus[family] = true; };
        link.onerror = () => {
            // no sidecar css for this theme: remove tag, don't retry
            this.themeCssStatus[family] = false;
            link.remove();
        };
        link.href = `/themes/${encodeURIComponent(family)}.css`;
        document.head.appendChild(link);
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
