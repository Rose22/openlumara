// =============================================================================
// Theme System
// =============================================================================

let currentThemeFamily = 'monochrome';
let currentThemeMode = 'dark'; // 'dark' or 'light'

// Parse theme ID to extract family and mode
function parseThemeId(themeId) {
    // Assumes format like 'dark-black', 'light-ocean', 'dark-default', etc.
    const parts = themeId.split('-');
    if (parts.length >= 2) {
        const mode = parts[0];
        const family = parts.slice(1).join('-');
        return { mode, family };
    }
    // Fallback for themes without prefix
    return { mode: 'dark', family: themeId };
}

// Build theme ID from family and mode
function buildThemeId(family, mode) {
    return `${mode}-${family}`;
}

// Get available theme families from themes object
function getThemeFamilies() {
    const families = new Map();

    Object.keys(themes).forEach(themeId => {
        const { mode, family } = parseThemeId(themeId);
        if (!families.has(family)) {
            families.set(family, { dark: null, light: null });
        }
        families.get(family)[mode] = themeId;
    });

    return families;
}

// Apply the current theme based on family and mode
function applyTheme(family, mode) {
    const themeId = buildThemeId(family, mode);
    const theme = themes[themeId];

    // If the specific variant doesn't exist, try the other mode
    if (!theme) {
        const alternateMode = mode === 'dark' ? 'light' : 'dark';
        const alternateId = buildThemeId(family, alternateMode);
        if (themes[alternateId]) {
            // Theme exists in alternate mode only
            currentThemeMode = alternateMode;
            updateModeCheckbox();
        }
    }

    const finalThemeId = buildThemeId(family, currentThemeMode);
    const finalTheme = themes[finalThemeId];

    if (!finalTheme) {
        console.error('Theme not found:', finalThemeId);
        return;
    }

    const root = document.documentElement;
    for (const [varName, value] of Object.entries(finalTheme.vars)) {
        root.style.setProperty(varName, value);
    }

    currentThemeFamily = family;
    localStorage.setItem('themeFamily', family);
    localStorage.setItem('themeMode', currentThemeMode);
    updateThemeButtons();
}

// Apply only mode change (keep same family)
function applyThemeMode(mode) {
    currentThemeMode = mode;
    applyTheme(currentThemeFamily, mode);
}

// Toggle between dark and light mode
function toggleThemeMode(isLight) {
    const mode = isLight ? 'light' : 'dark';
    applyThemeMode(mode);
}

// Update the mode checkbox to reflect current state
function updateModeCheckbox() {
    const checkbox = document.getElementById('theme-mode-checkbox');
    if (checkbox) {
        checkbox.checked = (currentThemeMode === 'light');
    }
}

// Create combined theme buttons
function createThemeButtons() {
    const grid = document.getElementById('theme-grid');
    grid.innerHTML = '';

    const families = getThemeFamilies();

    families.forEach((variants, family) => {
        // Always use dark variant for preview (or light if dark unavailable)
        const previewThemeId = variants.dark || variants.light;
        const previewTheme = themes[previewThemeId];

        if (!previewTheme) return;

        const btn = document.createElement('button');
        btn.className = 'theme-btn' + (family === currentThemeFamily ? ' active' : '');
        btn.dataset.family = family;

        const bgColor = previewTheme.vars['--bg-primary'];
        const accentColor = previewTheme.vars['--accent'];
        const hasBothModes = variants.dark && variants.light;

        // Display name
        const displayName = family.charAt(0).toUpperCase() + family.slice(1);

        btn.innerHTML = `
        <div class="theme-preview"
        style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);">
        ${hasBothModes ? '<span class="theme-badge">◐</span>' : ''}
        </div>
        <span class="theme-name">${displayName}</span>
        `;

        btn.onclick = () => {
            currentThemeFamily = family;
            applyTheme(family, currentThemeMode);
        };

        grid.appendChild(btn);
    });
}

// Update theme buttons to show active state
function updateThemeButtons() {
    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.family === currentThemeFamily);
    });
}

// Load saved theme preferences
function loadTheme() {
    const savedFamily = localStorage.getItem('themeFamily') || 'monochrome';
    const savedMode = localStorage.getItem('themeMode') || 'dark';

    // Verify the theme exists
    const themeId = buildThemeId(savedFamily, savedMode);
    if (!themes[themeId]) {
        // Fall back to default dark
        currentThemeFamily = 'monochrome';
        currentThemeMode = 'dark';
    } else {
        currentThemeFamily = savedFamily;
        currentThemeMode = savedMode;
    }

    applyTheme(currentThemeFamily, currentThemeMode);
}
