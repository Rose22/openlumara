// =============================================================================
// Settings Management
// =============================================================================

let settingsData = {};
let settingsOriginal = {};
let settingsHasChanges = false;
let cachedModels = null;
let modelsLoadError = null;
let moduleInfoCache = {};
let showUnsafeSettings = localStorage.getItem('showUnsafeSettings') === 'true';
let activeModule = null; // Tracks the selected module for Desktop split view / Mobile drill-down
let activeChannel = null; // Tracks the selected channel for Desktop split view / Mobile drill-down
let categories = {}; // Global reference to settings categories
let modulesExpanded = { modules: false, user_modules: false, channels: false, user_channels: false }; // Tracks expansion state per category
let isMobile = window.innerWidth <= 768; // Tracks mobile viewport state

let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    const newIsMobile = window.innerWidth <= 768;
    if (newIsMobile !== isMobile) {
        isMobile = newIsMobile;
        // Re-render settings UI if the modal is currently open
        const overlay = document.getElementById('settings-overlay');
        if (overlay && overlay.classList.contains('show')) {
            renderSettingsNav(categories);
            if (activeSettingsCategory) {
                renderSettingsForm(categories, activeSettingsCategory);
            }
        }
    }
});

// Category icons
const SETTINGS_ICONS = {
    api: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>`,
    model: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`,
    channels: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
    modules: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>`,
    appearance: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"></path></svg>`,
    advanced: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>`,
    other: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>`
};

// Category descriptions
const CATEGORY_DESCRIPTIONS = {};

// Check if a setting is a toggle list (has enabled/disabled arrays)
function isToggleList(data) {
    if (typeof data !== 'object' || data === null) return false;
    return Array.isArray(data.enabled) && Array.isArray(data.disabled);
}

// Get all items from enabled/disabled structure
function getAllToggleItems(data) {
    if (!isToggleList(data)) return [];
    const enabled = Array.isArray(data.enabled) ? data.enabled : [];
    const disabled = Array.isArray(data.disabled) ? data.disabled : [];
    return [...new Set([...enabled, ...disabled])].sort();
}

// Check if a key is a model name field
function isModelNameField(key) {
    return key === 'model.name' || key.endsWith('.model.name') || key === 'model_name';
}

// Fetch models from the API
async function fetchModels() {
    try {
        const response = await fetch('/api/models', {
            signal: AbortSignal.timeout(10000)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Server returned ${response.status}`);
        }

        const data = await response.json();
        cachedModels = data.models || [];
        modelsLoadError = null;
        return { success: true, models: cachedModels };
    } catch (err) {
        console.error('Failed to fetch models:', err);
        modelsLoadError = err.message || 'Failed to fetch models';
        return { success: false, error: modelsLoadError, models: [] };
    }
}

// Organize settings into categories, grouping by second-level key (e.g. modules.X)
function organizeSettingsIntoCategories(originalData, moduleInfo = {}) {
    const categories = {};

    // Always add appearance first
    categories.appearance = {
        title: 'Appearance',
        description: 'Theme and interface customization',
        isTheme: true,
        groups: new Map(),
        order: 0
    };

    let order = 1;
    const itemDescriptions = {};

    for (const [topKey, topValue] of Object.entries(originalData)) {
        if (topKey.toLowerCase() === 'theme' || topKey.toLowerCase() === 'theme_mode') {
            continue;
        }

        const category = topKey;
        categories[category] = {
            title: formatLabel(category),
            description: CATEGORY_DESCRIPTIONS[category] || `Configure ${formatLabel(category).toLowerCase()}`,
            groups: new Map(),
            order: order++
        };

        const addToGroup = (groupKey, groupTitle, item, isDirect = false) => {
            if (item.unsafe && !showUnsafeSettings) return;

            if (!categories[category].groups.has(groupKey)) {
                categories[category].groups.set(groupKey, {
                    title: groupTitle,
                    items: [],
                    isDirect: isDirect
                });
            }
            categories[category].groups.get(groupKey).items.push(item);
        };

        // Special handling for modules and channels
        if (topKey === 'modules' || topKey === 'user_modules' || topKey === 'channels' || topKey === 'user_channels') {
            const hasToggleListStructure = isToggleList(topValue);
            const enabledItems = new Set(topValue.enabled || []);
            const allItems = hasToggleListStructure ? getAllToggleItems(topValue) : [];

            const unsafeModules = {};
            for (const itemName in moduleInfo) {
                if (moduleInfo[itemName].description) {
                    itemDescriptions[itemName] = moduleInfo[itemName].description;
                }
                if (moduleInfo[itemName].unsafe) {
                    unsafeModules[itemName] = true;
                }
            }

            if (hasToggleListStructure) {
                addToGroup('_direct_', null, {
                    key: topKey,
                    value: {
                        enabled: topValue.enabled || [],
                        disabled: topValue.disabled || [],
                        descriptions: itemDescriptions,
                        unsafeModules: unsafeModules
                    },
                    type: 'toggle_list',
                    isModuleList: true
                }, true);
            }

            if (topValue.settings && typeof topValue.settings === 'object') {
                const allSettingsKeys = hasToggleListStructure ? allItems : Object.keys(topValue.settings);
                
                for (const itemName of allSettingsKeys) {
                    const itemSettings = topValue.settings[itemName];
                    if (itemSettings === undefined) continue;

                    const groupKey = `${topKey}.settings.${itemName}`;
                    const groupTitle = formatLabel(itemName);
                    const itemSchema = moduleInfo[itemName]?.settings_schema || {};

                    if (typeof itemSettings === 'object' && itemSettings !== null &&
                        !Array.isArray(itemSettings) && !isToggleList(itemSettings)) {
                        flattenSettingsObject(itemSettings, groupKey, itemSchema, (item) => {
                            addToGroup(groupKey, groupTitle, item);
                        });
                    } else {
                        // Handle simple values by checking the schema for an explicit type
                        let type = detectType(itemSettings, groupKey);
                        if (itemSchema[itemName] && itemSchema[itemName].type) {
                            type = itemSchema[itemName].type;
                        }

                        let description = FIELD_DESCRIPTIONS[groupKey] || null;
                        if (!description && itemSchema[itemName] && itemSchema[itemName].description) {
                            description = itemSchema[itemName].description;
                        }

                        addToGroup(groupKey, groupTitle, {
                            key: groupKey,
                            value: itemSettings,
                            type: type,
                            description: description,
                            unsafe: itemSchema[itemName]?.unsafe || false,
                            min: itemSchema[itemName]?.min,
                            max: itemSchema[itemName]?.max,
                            step: itemSchema[itemName]?.step
                        });
                    }
                }
            }
            // ... (rest of module direct items logic remains the same)
            for (const [secondKey, secondValue] of Object.entries(topValue)) {
                if (secondKey === 'settings' || secondKey === 'enabled' ||
                    secondKey === 'disabled' || secondKey === 'disabled_prompts') {
                    continue;
                    }
                    const groupKey = `${topKey}.${secondKey}`;
                addToGroup('_direct_', null, {
                    key: groupKey,
                    value: secondValue,
                    type: detectType(secondValue, groupKey)
                }, true);
            }
            continue;
        }

        // Check if this is a toggle list at top level
        if (isToggleList(topValue)) {
            addToGroup('_direct_', null, {
                key: topKey,
                value: topValue,
                type: 'toggle_list'
            }, true);

            if (topValue.settings && typeof topValue.settings === 'object') {
                const enabledItems = new Set(topValue.enabled || []);
                for (const [itemName, itemSettings] of Object.entries(topValue.settings)) {
                    if (!enabledItems.has(itemName)) continue;
                    const groupKey = `${topKey}.settings.${itemName}`;
                    const groupTitle = formatLabel(itemName);
                    const itemSchema = moduleInfo[itemName]?.settings_schema || {};

                    if (typeof itemSettings === 'object' && itemSettings !== null &&
                        !Array.isArray(itemSettings) && !isToggleList(itemSettings)) {
                        flattenSettingsObject(itemSettings, groupKey, itemSchema, (item) => {
                            addToGroup(groupKey, groupTitle, item);
                        });
                        } else {
                            let type = detectType(itemSettings, groupKey);
                            if (itemSchema[itemName] && itemSchema[itemName].type) {
                                type = itemSchema[itemName].type;
                            }

                            let description = FIELD_DESCRIPTIONS[groupKey] || null;
                            if (!description && itemSchema[itemName] && itemSchema[itemName].description) {
                                description = itemSchema[itemName].description;
                            }

                            addToGroup(groupKey, groupTitle, {
                                key: groupKey,
                                value: itemSettings,
                                type: type,
                                description: renderMarkdown(description),
                                min: itemSchema[itemName]?.min,
                                max: itemSchema[itemName]?.max,
                                step: itemSchema[itemName]?.step
                            });
                        }
                }
            }
            continue;
        }

        // Regular object logic
        if (typeof topValue === 'object' && topValue !== null && !Array.isArray(topValue)) {
            if (topValue.type === 'group') {
                const groupKey = `${category}.${topKey}`;
                const groupTitle = formatLabel(topKey);

                if (!categories[category].groups.has(groupKey)) {
                    categories[category].groups.set(groupKey, {
                        title: groupTitle,
                        items: [],
                        description: topValue.description || null
                    });
                }

                const group = categories[category].groups.get(groupKey);

                for (const [itemKey, itemValue] of Object.entries(topValue.items)) {
                    let val = itemValue;
                    let type = detectType(itemValue, `${groupKey}.${itemKey}`);
                    let desc = null;

                    if (typeof itemValue === 'object' && itemValue !== null && !Array.isArray(itemValue) && 'default' in itemValue) {
                        val = itemValue.default;
                        desc = itemValue.description;
                    }

                    group.items.push({
                        key: `${groupKey}.${itemKey}`,
                        value: val,
                        type: type,
                        description: desc
                    });
                }
                continue;
            }

            if (topValue.type || topValue.default !== undefined) {
                let type = topValue.type || detectType(topValue.default, `${category}.${topKey}`);
                if (type === 'long_text') type = 'textarea';
                
                addToGroup('_direct_', null, {
                    key: `${category}.${topKey}`,
                    value: topValue.default,
                    type: type,
                    description: topValue.description || null,
                    options: topValue.options || null
                }, true);
                continue;
            }

            const simpleItems = [];
            const complexItems = [];

            for (const [secondKey, secondValue] of Object.entries(topValue)) {
                if (isToggleList(secondValue) || Array.isArray(secondValue) || (typeof secondValue === 'object' && secondValue !== null)) {
                    complexItems.push([secondKey, secondValue]);
                } else {
                    simpleItems.push([secondKey, secondValue]);
                }
            }

            for (const [key, value] of simpleItems) {
                addToGroup('_direct_', null, {
                    key: `${category}.${key}`,
                    value: value,
                    type: detectType(value, `${category}.${key}`)
                }, true);
            }

            for (const [secondKey, secondValue] of complexItems) {
                const groupKey = `${topKey}.${secondKey}`;
                const groupTitle = formatLabel(secondKey);

                if (typeof secondValue === 'object' && secondValue !== null &&
                    !Array.isArray(secondValue) && !isToggleList(secondValue)) {
                    flattenSettingsObject(secondValue, groupKey, {}, (item) => {
                        addToGroup(groupKey, groupTitle, item);
                    });
                    } else {
                        addToGroup(groupKey, groupTitle, {
                            key: groupKey,
                            value: secondValue,
                            type: isToggleList(secondValue) ? 'toggle_list' : detectType(secondValue, groupKey),
                                   description: FIELD_DESCRIPTIONS[groupKey] || null
                        });
                    }
            }
        } else {
            addToGroup(topKey, formatLabel(topKey), {
                key: topKey,
                value: topValue,
                type: detectType(topValue, topKey)
            });
        }
    }

    return categories;
}


// Flatten a settings object into dot-notation items
function flattenSettingsObject(obj, prefix, schema = {}, callback) {
    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        const subSchema = (schema && schema[key]) ? schema[key] : {};

        // Check if this is a "setting definition" object (has metadata)
        const isDefinition = (typeof value === 'object' && value !== null && !Array.isArray(value) &&
        ('default' in value || 'description' in value || 'type' in value || 'unsafe' in value));

        if (!isDefinition && !isToggleList(value) && typeof value === 'object' && value !== null && !Array.isArray(value)) {
            // Nested object - recurse
            flattenSettingsObject(value, fullKey, subSchema, callback);
        } else {
            // Leaf node (either it's a definition, a toggle list, or a primitive)
            let actualValue = value;
            let actualDescription = null;
            let actualType = null;
            let actualUnsafe = false;

            if (isDefinition) {
                actualValue = 'default' in value ? value.default : value;
                actualDescription = value.description || null;
                actualUnsafe = value.unsafe || false;
                if (value.type) {
                    // Map custom types to UI types
                    if (value.type === 'long_text') actualType = 'textarea';
                    else if (value.type === 'select') actualType = 'select';
                    else if (value.type === 'number') actualType = 'number';
                    else if (value.type === 'slider') actualType = 'slider';
                    else actualType = value.type;
                }
            }

            // If type is still not set, try to get it from subSchema or detect it
            if (!actualType) {
                if (subSchema.type) {
                    if (subSchema.type === 'long_text') actualType = 'textarea';
                    else if (subSchema.type === 'select') actualType = 'select';
                    else if (subSchema.type === 'number') actualType = 'number';
                    else if (subSchema.type === 'slider') actualType = 'slider';
                    else actualType = detectType(actualValue, fullKey);
                } else if (isToggleList(actualValue)) {
                    actualType = 'toggle_list';
                } else {
                    actualType = detectType(actualValue, fullKey);
                }
            }

            // Final description check
            if (!actualDescription) {
                actualDescription = FIELD_DESCRIPTIONS[fullKey] || subSchema.description || null;
            }

            callback({
                key: fullKey,
                value: actualValue,
                type: actualType,
                description: actualDescription,
                unsafe: actualUnsafe || subSchema.unsafe || false,
                min: subSchema.min || (isDefinition ? value.min : undefined),
                max: subSchema.max || (isDefinition ? value.max : undefined),
                step: subSchema.step || (isDefinition ? value.step : undefined),
                options: subSchema.options || (isDefinition ? value.options : null)
            });
        }
    }
}

// Detect field type from value
function detectType(value, key = '') {
    if (key.endsWith('reasoning_effort')) {
        return 'reasoning_effort_slider';
    }
    if (value === null || value === undefined) return 'text';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number' && !key.toLowerCase().endsWith('id')) return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    if (typeof value === 'string') {
        // Check if this is a model name field
        if (key && isModelNameField(key)) {
            return 'model';
        }
        if (value.includes('\n')) return 'textarea';
        if (value.match(/^https?:\/\//)) return 'url';
    }
    return 'text';
}

// Field descriptions (optional, can be empty)
const FIELD_DESCRIPTIONS = {
    'api.key': 'API authentication key',
    'model.name': 'The AI model to use for responses'
};

// Flatten nested object to dot-notation keys
function flattenObject(obj, prefix = '') {
    const result = {};

    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;

        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
            const nested = flattenObject(value, fullKey);
            Object.assign(result, nested);
        } else {
            result[fullKey] = value;
        }
    }

    return result;
}

// Unflatten dot-notation keys back to nested object
function unflattenObject(flat) {
    const result = {};

    for (const [key, value] of Object.entries(flat)) {
        const parts = key.split('.');
        let current = result;

        for (let i = 0; i < parts.length - 1; i++) {
            const part = parts[i];
            if (!(part in current)) {
                current[part] = {};
            }
            current = current[part];
        }

        current[parts[parts.length - 1]] = value;
    }

    return result;
}

// Format label from key
function formatLabel(key) {
    if (typeof key !== 'string') return key;

    // Extract just the last part of a dotted key for display
    const parts = key.split('.');
    const lastPart = parts[parts.length - 1];

    // Replace underscores with spaces and capitalize
    return lastPart.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Get the current value for a given key path from the live settingsData.
 * This is used during form re-renders to prevent losing unsaved changes.
 */
function getCurrentValue(key) {
    const parts = key.split('.');
    let current = settingsData;

    for (const part of parts) {
        if (current === null || current === undefined || typeof current !== 'object') {
            return undefined;
        }
        current = current[part];
    }

    return current;
}

// Load settings from backend
async function loadSettings() {
    const loading = document.getElementById('settings-loading');
    const error = document.getElementById('settings-error');
    const form = document.getElementById('settings-form');
    const errorMsg = document.getElementById('settings-error-msg');

    loading.style.display = 'flex';
    error.style.display = 'none';
    form.style.display = 'none';

    let fetchError = null;

    try {
        // 1. Attempt to fetch fresh data
        const response = await fetch('/settings/load', {
            signal: AbortSignal.timeout(5000) // Reduced timeout for better responsiveness
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const newData = await response.json();

        // 2. If successful, update the master cache and the original reference
        settingsData = newData;
        settingsOriginal = JSON.parse(JSON.stringify(settingsData));
        changedModuleSettings.clear();

        // 3. Attempt to fetch module info (gracefully)
        try {
            const infoResponse = await fetch('/settings/get_module_info', { signal: AbortSignal.timeout(3000) });
            if (infoResponse.ok) {
                const infoData = await infoResponse.json();
                moduleInfoCache = infoData.module_info || {};
            }
        } catch (infoErr) {
            console.warn('Failed to fetch module info (using cache):', infoErr);
        }

        // 4. Pre-fetch models (gracefully)
        if (checkForModelField(settingsData)) {
            fetchModels().catch(e => console.warn("Model fetch failed:", e));
        }

    } catch (err) {
        console.error('Failed to load settings from server:', err);
        fetchError = err.message;

        // 5. CHECK CACHE: If we have data in settingsData, don't show error, just use what we have
        if (Object.keys(settingsData).length === 0) {
            // No cache exists and server failed -> Hard error
            loading.style.display = 'none';
            error.style.display = 'flex';
            errorMsg.textContent = fetchError || 'Failed to load settings and no cached data available.';
            return;
        } else {
            // We have cache! We will proceed to render, but we've logged the error.
            console.warn('Proceeding with cached settings due to connection error.');
        }
    }

    // 6. Render whatever we have (either the fresh data or the cached data)
    categories = organizeSettingsIntoCategories(settingsData, moduleInfoCache);
    const firstCategory = Object.keys(categories)[0];
    activeSettingsCategory = firstCategory;
    renderSettingsForm(categories, firstCategory);
    renderSettingsNav(categories);

    loading.style.display = 'none';
    form.style.display = 'block';
    settingsHasChanges = false;
    updateUnsavedIndicator();
}

// Check if settings contain a model field
function checkForModelField(data, prefix = '') {
    for (const [key, value] of Object.entries(data)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;

        if (isModelNameField(fullKey)) {
            return true;
        }

        if (value && typeof value === 'object' && !Array.isArray(value)) {
            if (checkForModelField(value, fullKey)) {
                return true;
            }
        }
    }
    return false;
}

// Render settings navigation
// Track the currently active category for highlight persistence
let activeSettingsCategory = null;

// Render settings navigation
function renderSettingsNav(categories) {
    const nav = document.getElementById('settings-nav');
    nav.innerHTML = '';
 
    nav_top = document.createElement('div');
    nav_top.className = 'settings-nav-top';

    const sortedCats = Object.entries(categories)
    .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));

    sortedCats.forEach(([cat, data], index) => {
        const btn = document.createElement('button');
        btn.className = 'settings-nav-item';
        btn.dataset.category = cat;
        btn.innerHTML = `
        ${SETTINGS_ICONS[cat] || SETTINGS_ICONS.other}
        <span>${data.title}</span>
        `;
        btn.onclick = () => switchSettingsCategory(cat);
        nav_top.appendChild(btn);

        // Add module sub-list for Modules category on desktop only
        if (!isMobile && (cat === 'modules' || cat === 'user_modules') && data.groups && data.groups.has('_direct_')) {
            const directGroup = data.groups.get('_direct_');
            if (directGroup && directGroup.items.length > 0) {
                const moduleListData = directGroup.items[0].value;
                const allModules = getAllToggleItems({ enabled: moduleListData.enabled, disabled: moduleListData.disabled });
                const enabledSet = new Set(moduleListData.enabled);
                
                const subList = document.createElement('div');
                subList.className = 'module-sub-list' + (modulesExpanded[cat] ? ' expanded' : '');
                subList.style.display = modulesExpanded[cat] ? '' : 'none';

                allModules.forEach(moduleName => {
                    const isUnsafe = moduleListData.unsafeModules[moduleName];
                    if (isUnsafe && !showUnsafeSettings) return;
                    
                    // Only show enabled modules in the sidebar
                    if (!enabledSet.has(moduleName)) return;

                    // Check if module has settings - only show modules with actual settings
                    const moduleSettingsGroupKey = `${cat}.settings.${moduleName}`;
                    const moduleGroup = data.groups?.get(moduleSettingsGroupKey);
                    if (!moduleGroup || moduleGroup.items.length === 0) return;

                    const subBtn = document.createElement('button');
                    subBtn.textContent = formatLabel(moduleName);
                    subBtn.dataset.module = moduleName;
                    subBtn.classList.toggle('active', activeModule === moduleName);

                    subBtn.onclick = (e) => {
                        e.stopPropagation();
                        selectModule(moduleName, cat);
                    };

                    subList.appendChild(subBtn);
                });

                // Insert sub-list after the main button
                btn.parentNode.insertBefore(subList, btn.nextSibling);
            }
        }

        // Add channel sub-list for Channels category on desktop only
        if (!isMobile && (cat === 'channels' || cat === 'user_channels') && data.groups && data.groups.has('_direct_')) {
            const directGroup = data.groups.get('_direct_');
            if (directGroup && directGroup.items.length > 0) {
                const channelListData = directGroup.items[0].value;
                const allChannels = getAllToggleItems({ enabled: channelListData.enabled, disabled: channelListData.disabled });
                const enabledSet = new Set(channelListData.enabled);
                
                const subList = document.createElement('div');
                subList.className = 'module-sub-list' + (modulesExpanded[cat] ? ' expanded' : '');
                subList.style.display = modulesExpanded[cat] ? '' : 'none';

                allChannels.forEach(channelName => {
                    // Only show enabled channels in the sidebar
                    if (!enabledSet.has(channelName)) return;

                    // Check if channel has settings - only show channels with actual settings
                    const channelSettingsGroupKey = `${cat}.settings.${channelName}`;
                    const channelGroup = data.groups?.get(channelSettingsGroupKey);
                    if (!channelGroup || channelGroup.items.length === 0) return;

                    const subBtn = document.createElement('button');
                    subBtn.textContent = formatLabel(channelName);
                    subBtn.dataset.channel = channelName;
                    subBtn.classList.toggle('active', activeChannel === channelName);

                    subBtn.onclick = (e) => {
                        e.stopPropagation();
                        selectChannel(channelName, cat);
                    };

                    subList.appendChild(subBtn);
                });

                // Insert sub-list after the main button
                btn.parentNode.insertBefore(subList, btn.nextSibling);
            }
        }
    });

    // add special buttons

    nav_bottom = document.createElement('div');
    nav_bottom.className = 'settings-nav-bottom';

    const logBtn = document.createElement('button');
    logBtn.className = 'settings-nav-item';
    logBtn.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="4 17 10 11 4 5"></polyline>
    <line x1="12" y1="19" x2="20" y2="19"></line>
    </svg>
    <span>System Logs</span>
    `;
    logBtn.onclick = () => toggleModal('log');
    nav_bottom.appendChild(logBtn);

    const restartBtn = document.createElement('button');
    restartBtn.className = 'settings-nav-item restart-btn';
    restartBtn.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.78.8 6.5 2.1l.5.4"/>
    <path d="M21 3v5h-5"/>
    </svg>
    <span>Restart Server</span>
    `;
    restartBtn.onclick = async () => {
        const confirmed = await showConfirmDialog("Are you sure you want to restart the server? This will disconnect the web UI momentarily.");
        if (confirmed) {
            restartServer();
        }
    };
    nav_bottom.appendChild(restartBtn);

    nav.appendChild(nav_top);

    divider = document.createElement('div');
    divider.className = 'settings-nav-divider';
    nav.appendChild(divider);

    nav.appendChild(nav_bottom);

    // Restore active highlight after re-rendering
    if (activeSettingsCategory) {
        document.querySelectorAll('.settings-nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.category === activeSettingsCategory);
        });
    }
}

// Switch active settings category
function switchSettingsCategory(category) {
    const nav = document.getElementById('settings-nav');
    const savedScrollLeft = nav ? nav.scrollLeft : 0;
    
    activeSettingsCategory = category;
    
    const isModules = category === 'modules' || category === 'user_modules';
    const isChannels = category === 'channels' || category === 'user_channels';

    if (isModules || isChannels) {
        // Expand the clicked category's sub-list, collapse others
        for (const key in modulesExpanded) {
            modulesExpanded[key] = key === category;
        }

        document.querySelectorAll('.settings-nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.category === category);
        });

        // Reset active module/channel when switching to Modules/Channels category
        if (isModules) {
            activeModule = null;
        }
        if (isChannels) {
            activeChannel = null;
        }
    } else {
        // For other categories, clear all sidebar states
        clearSidebarSelections();
        document.querySelectorAll('.settings-nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.category === category);
        });
    }

    renderSettingsForm(categories, category);
    // Re-render nav to update sub-list active state and visibility
    renderSettingsNav(categories);
    
    // Restore scroll position to prevent mobile auto-scroll jump
    if (nav) {
        nav.scrollLeft = savedScrollLeft;
    }
}

// Handle module selection from sub-list
// Handle module selection from sub-list
function selectModule(moduleName, category = 'modules') {
    activeSettingsCategory = category;
    activeModule = moduleName;
    renderSettingsForm(categories, category);
    renderSettingsNav(categories);
}

// Handle channel selection from sub-list
function selectChannel(channelName, category = 'channels') {
    activeSettingsCategory = category;
    activeChannel = channelName;
    renderSettingsForm(categories, category);
    renderSettingsNav(categories);
}

function renderSettingsForm(categories, activeSettingsCategory = null) {
    const form = document.getElementById('settings-form');
    form.innerHTML = '';

 

    // Mobile: Show category list if none selected
    if (isMobile && !activeSettingsCategory) {
        const list = document.createElement('div');
        list.className = 'mobile-category-list';
        list.style.cssText = 'display: flex; flex-direction: column; background: var(--bg-secondary); border-radius: 12px; overflow: hidden; margin-bottom: 16px;';
        const sortedCats = Object.entries(categories).sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));
        sortedCats.forEach(([cat, data]) => {
            const btn = document.createElement('button');
            btn.className = 'mobile-category-btn';
            btn.style.cssText = 'display: flex; align-items: center; gap: 14px; padding: 16px 20px; background: none; border: none; cursor: pointer; text-align: left; font-size: 0.95rem; color: var(--text-primary); transition: background 0.15s ease; width: 100%; margin: 0;';
            btn.innerHTML = `${SETTINGS_ICONS[cat] || SETTINGS_ICONS.other} <span style="font-weight: 500; color: var(--text-primary);">${data.title}</span>`;
            btn.onclick = () => {
                activeSettingsCategory = cat;
                renderSettingsForm(categories, cat);
            };
            list.appendChild(btn);
        });
        form.appendChild(list);
        return;
    }

    const sortedCats = Object.entries(categories)
    .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));

    for (const [cat, data] of sortedCats) {
        const section = document.createElement('div');
        section.className = 'settings-section' + (cat === activeSettingsCategory ? ' active' : '');
        section.dataset.category = cat;

        const itemsContainer = document.createElement('div');
        
        // Only show main category header if not viewing a module/channel sub-page
        if (!(activeModule || activeChannel)) {
            section.innerHTML = `
            <h3 class="settings-section-title">${data.title}</h3>
            `;
        } else {
            if (isMobile) {
                // show a back button instead on mobile
                const backBtn = document.createElement('button');
                backBtn.className = 'mobile-back-btn';
                backBtn.style.cssText = 'display: flex; align-items: center; gap: 10px; border: 1px solid var(--border-color); color: var(--text-primary); font-size: 0.95rem; padding: 12px 16px; width: 100%; margin-bottom: 12px; border-radius: var(--radius-sm); transition: all 0.15s ease;';
                backBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 12H5"></path>
                <path d="M12 19l-7-7 7-7"></path>
                </svg>
                <span>Back</span>
                `;
                backBtn.onmouseenter = () => { backBtn.style.background = 'var(--bg-secondary)'; backBtn.style.borderColor = 'var(--accent)'; };
                backBtn.onmouseleave = () => { backBtn.style.background = 'var(--bg-tertiary)'; backBtn.style.borderColor = 'var(--border-color)'; };
                backBtn.onclick = () => {
                    activeModule = null;
                    activeChannel = null;
                    renderSettingsForm(categories, activeSettingsCategory);
                };
                itemsContainer.appendChild(backBtn);
            }
        }
        itemsContainer.className = 'settings-items';

        // Add theme section for appearance
        if (data.isTheme) {
            const themeSection = createThemeSection();
            itemsContainer.appendChild(themeSection);

            if (data.groups && data.groups.size > 0) {
                const separator = document.createElement('div');
                separator.className = 'settings-separator';
                separator.innerHTML = '<hr style="border: none; border-top: 1px solid var(--border-color); margin: 24px 0;">';
                itemsContainer.appendChild(separator);
            }
        }

       // Special handling for Modules category
        if (cat === 'modules' || cat === 'user_modules') {
            const directGroup = data.groups?.get('_direct_');
            if (directGroup && directGroup.items.length > 0) {
                const moduleListData = directGroup.items[0].value;
                const allModules = getAllToggleItems({ enabled: moduleListData.enabled, disabled: moduleListData.disabled });
                const enabledSet = new Set(moduleListData.enabled);

                if (isMobile) {
                    if (activeModule) {
                        // Drill-down: Show settings for selected module


                        // Render settings for the active module
                        const moduleSettingsGroupKey = `${cat}.settings.${activeModule}`;
                        const moduleGroup = data.groups?.get(moduleSettingsGroupKey);
                        if (moduleGroup) {
                            const moduleTitle = document.createElement('h3');
                            moduleTitle.className = 'settings-section-title';
                            moduleTitle.textContent = formatLabel(activeModule);
                            itemsContainer.appendChild(moduleTitle);

                            moduleGroup.items.forEach(item => {
                                const itemEl = createSettingItem(item);
                                itemsContainer.appendChild(itemEl);
                            });
                        } else {
                            // Fallback if no specific settings group exists
                            const msg = document.createElement('div');
                            msg.className = 'settings-section-desc';
                            msg.textContent = `No settings available for ${formatLabel(activeModule)}.`;
                            itemsContainer.appendChild(msg);
                        }
                    } else {
                        // Show unified module list with inline toggles
                        const unifiedList = document.createElement('div');
                        unifiedList.className = 'module-unified-list';
                        unifiedList.style.cssText = 'display: flex; flex-direction: column; gap: 1px; background: var(--bg-secondary); border-radius: var(--radius-sm); overflow: hidden; margin-bottom: 14px;';

                        // Capture the key from the toggle list item
                        const toggleListKey = directGroup.items[0].key;

                        // Filter and sort modules
                        const filteredModules = allModules.filter(moduleName => {
                            // Skip unsafe modules if not showing them
                            if (moduleListData.unsafeModules[moduleName] && !showUnsafeSettings) return false;
                            // Only show modules that have settings
                            const moduleSettingsGroupKey = `${cat}.settings.${moduleName}`;
                            const moduleGroup = data.groups?.get(moduleSettingsGroupKey);
                            return moduleGroup && moduleGroup.items.length > 0;
                        });

                        // Status bar for enabled count
                        const statusDiv = document.createElement('div');
                        statusDiv.className = 'toggle-list-status';
                        statusDiv.style.cssText = 'padding: 10px 12px; background: var(--bg-secondary); margin-bottom: 1px;';
                        statusDiv.innerHTML = `<span class="toggle-count">${enabledSet.size} of ${filteredModules.length} enabled</span>`;
                        unifiedList.appendChild(statusDiv);

                        if (filteredModules.length === 0) {
                            const emptyMsg = document.createElement('div');
                            emptyMsg.className = 'settings-section-desc';
                            emptyMsg.style.cssText = 'padding: 20px; text-align: center; color: var(--text-muted);';
                            emptyMsg.textContent = 'No modules with settings available.';
                            unifiedList.appendChild(emptyMsg);
                        } else {
                            filteredModules.forEach(moduleName => {
                                const isEnabled = enabledSet.has(moduleName);
                                const isUnsafe = !!moduleListData.unsafeModules[moduleName];

                                const card = document.createElement('button');
                                card.className = 'module-unified-card' + (isEnabled ? ' enabled' : '');
                                if (isUnsafe) card.classList.add('module-unsafe');
                                card.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: var(--bg-secondary); border: 1px solid var(--border-color); margin-bottom: 1em; width: 100%; text-align: left; color: var(--text-primary);';

                                card.innerHTML = `
                                    <div class="module-card-left">
                                        <span class="module-card-name">${formatLabel(moduleName)}${isUnsafe ? ' <span class="module-unsafe-badge" style="font-size: 0.7em; background: var(--warning); color: var(--warning-text); padding: 2px 6px; border-radius: 4px; margin-left: 8px;">UNSAFE</span>' : ''}</span>
                                    </div>
                                    <div class="module-card-right">
                                        <label class="toggle-switch">
                                            <input type="checkbox" ${isEnabled ? 'checked' : ''} class="module-toggle">
                                            <span class="toggle-slider"></span>
                                        </label>
                                        <svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
                                    </div>
                                `;

                                // Row tap → drill down (only if toggle wasn't clicked)
                                card.addEventListener('click', (e) => {
                                    if (!e.target.closest('.toggle-switch')) {
                                        activeModule = moduleName;
                                        renderSettingsForm(categories, cat);
                                    }
                                });

                                // Toggle change → update state immediately
                                const toggle = card.querySelector('.module-toggle');
                                toggle.addEventListener('change', async () => {
                                    const newState = toggle.checked;

                                    if (newState && isUnsafe) {
                                        const confirmed = await showConfirmDialog(
                                            "You are about to activate an unsafe module. This module can perform actions that could potentially harm your system! Please be very sure of what you're doing. Proceed?"
                                        );
                                        if (!confirmed) {
                                            toggle.checked = false;
                                            return;
                                        }
                                    }

                                    if (newState) {
                                        enabledSet.add(moduleName);
                                    } else {
                                        enabledSet.delete(moduleName);
                                    }

                                    // Update UI
                                    card.classList.toggle('enabled', newState);
                                    statusDiv.querySelector('.toggle-count').textContent = `${enabledSet.size} of ${filteredModules.length} enabled`;

                                    // Update data
                                    updateToggleListData(toggleListKey, Array.from(enabledSet), allModules);
                                });

                                unifiedList.appendChild(card);
                            });
                        }
                        itemsContainer.appendChild(unifiedList);
                    }
                } else {
                    // Desktop: Show sidebar sub-list or module settings
                    if (activeModule) {
                        // Show settings for selected module
                        const moduleSettingsGroupKey = `${cat}.settings.${activeModule}`;
                        const moduleGroup = data.groups?.get(moduleSettingsGroupKey);
                        if (moduleGroup) {
                            const moduleTitle = document.createElement('h3');
                            moduleTitle.className = 'settings-section-title';
                            moduleTitle.textContent = formatLabel(activeModule);
                            itemsContainer.appendChild(moduleTitle);

                            moduleGroup.items.forEach(item => {
                                const itemEl = createSettingItem(item);
                                itemsContainer.appendChild(itemEl);
                            });
                        } else {
                            // Fallback if no specific settings group exists
                            const msg = document.createElement('div');
                            msg.className = 'settings-section-desc';
                            msg.textContent = `No settings available for ${formatLabel(activeModule)}.`;
                            itemsContainer.appendChild(msg);
                        }
                    } else {
                        // Show the global toggle list
                        const itemEl = createSettingItem(directGroup.items[0]);
                        itemsContainer.appendChild(itemEl);
                    }
                }
            }
        }

        // Special handling for Channels category
        if (cat === 'channels' || cat === 'user_channels') {
            const directGroup = data.groups?.get('_direct_');
            if (directGroup && directGroup.items.length > 0) {
                const channelListData = directGroup.items[0].value;
                const allChannels = getAllToggleItems({ enabled: channelListData.enabled, disabled: channelListData.disabled });
                const enabledSet = new Set(channelListData.enabled);

                if (isMobile) {
                    if (activeChannel) {
                        // Render settings for the active channel
                        const channelSettingsGroupKey = `${cat}.settings.${activeChannel}`;
                        const channelGroup = data.groups?.get(channelSettingsGroupKey);
                        if (channelGroup) {
                            const channelTitle = document.createElement('h3');
                            channelTitle.className = 'settings-section-title';
                            channelTitle.textContent = formatLabel(activeChannel);
                            itemsContainer.appendChild(channelTitle);

                            channelGroup.items.forEach(item => {
                                const itemEl = createSettingItem(item);
                                itemsContainer.appendChild(itemEl);
                            });
                        } else {
                            // Fallback if no specific settings group exists
                            const msg = document.createElement('div');
                            msg.className = 'settings-section-desc';
                            msg.textContent = `No settings available for ${formatLabel(activeChannel)}.`;
                            itemsContainer.appendChild(msg);
                        }
                    } else {
                        // Show unified channel list with inline toggles
                        const unifiedList = document.createElement('div');
                        unifiedList.className = 'channel-unified-list';
                        unifiedList.style.cssText = 'display: flex; flex-direction: column; gap: 1px; background: var(--bg-secondary); border-radius: var(--radius-sm); overflow: hidden; margin-bottom: 14px;';

                        // Filter channels that have settings
                        const filteredChannels = allChannels.filter(channelName => {
                            const channelSettingsGroupKey = `${cat}.settings.${channelName}`;
                            const channelGroup = data.groups?.get(channelSettingsGroupKey);
                            return channelGroup && channelGroup.items.length > 0;
                        });

                        // Capture the key from the toggle list item
                        const channelListKey = directGroup.items[0].key;

                        // Status bar for enabled count
                        const statusDiv = document.createElement('div');
                        statusDiv.className = 'toggle-list-status';
                        statusDiv.style.cssText = 'padding: 10px 12px; background: var(--bg-secondary); margin-bottom: 1px; border-radius: var(--radius-sm) var(--radius-sm) 0 0;';
                        statusDiv.innerHTML = `<span class="toggle-count">${enabledSet.size} of ${filteredChannels.length} enabled</span>`;
                        unifiedList.appendChild(statusDiv);

                        if (filteredChannels.length === 0) {
                            const emptyMsg = document.createElement('div');
                            emptyMsg.className = 'settings-section-desc';
                            emptyMsg.style.cssText = 'padding: 20px; text-align: center; color: var(--text-muted);';
                            emptyMsg.textContent = 'No channels with settings available.';
                            unifiedList.appendChild(emptyMsg);
                        } else {
                            filteredChannels.forEach(channelName => {
                                const isEnabled = enabledSet.has(channelName);

                                const card = document.createElement('button');
                                card.className = 'channel-unified-card' + (isEnabled ? ' enabled' : '');
                                card.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: var(--bg-secondary); border: 1px solid var(--border-color); margin-bottom: 1em; width: 100%; text-align: left; color: var(--text-primary);';

                                card.innerHTML = `
                                    <div class="channel-card-left">
                                        <span class="channel-card-name">${formatLabel(channelName)}</span>
                                    </div>
                                    <div class="channel-card-right">
                                        <label class="toggle-switch">
                                            <input type="checkbox" ${isEnabled ? 'checked' : ''} class="channel-toggle">
                                            <span class="toggle-slider"></span>
                                        </label>
                                        <svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
                                    </div>
                                `;

                                // Row tap → drill down (only if toggle wasn't clicked)
                                card.addEventListener('click', (e) => {
                                    if (!e.target.closest('.toggle-switch')) {
                                        activeChannel = channelName;
                                        renderSettingsForm(categories, cat);
                                    }
                                });

                                // Toggle change → update state immediately
                                const toggle = card.querySelector('.channel-toggle');
                                toggle.addEventListener('change', () => {
                                    const newState = toggle.checked;

                                    if (newState) {
                                        enabledSet.add(channelName);
                                    } else {
                                        enabledSet.delete(channelName);
                                    }

                                    // Update UI
                                    card.classList.toggle('enabled', newState);
                                    statusDiv.querySelector('.toggle-count').textContent = `${enabledSet.size} of ${filteredChannels.length} enabled`;

                                    // Update data
                                    updateToggleListData(channelListKey, Array.from(enabledSet), allChannels);
                                });

                                unifiedList.appendChild(card);
                            });
                        }
                        itemsContainer.appendChild(unifiedList);
                    }
                } else {
                    // Desktop: Show sidebar sub-list or channel settings
                    if (activeChannel) {
                        // Show settings for selected channel
                        const channelSettingsGroupKey = `${cat}.settings.${activeChannel}`;
                        const channelGroup = data.groups?.get(channelSettingsGroupKey);
                        if (channelGroup) {
                            const channelTitle = document.createElement('h3');
                            channelTitle.className = 'settings-section-title';
                            channelTitle.textContent = formatLabel(activeChannel);
                            itemsContainer.appendChild(channelTitle);

                            channelGroup.items.forEach(item => {
                                const itemEl = createSettingItem(item);
                                itemsContainer.appendChild(itemEl);
                            });
                        } else {
                            // Fallback if no specific settings group exists
                            const msg = document.createElement('div');
                            msg.className = 'settings-section-desc';
                            msg.textContent = `No settings available for ${formatLabel(activeChannel)}.`;
                            itemsContainer.appendChild(msg);
                        }
                    } else {
                        // Show the global toggle list
                        const itemEl = createSettingItem(directGroup.items[0]);
                        itemsContainer.appendChild(itemEl);
                    }
                }
            }
        }
        
        // Skip generic group rendering for modules/user_modules/channels
        if (cat !== 'modules' && cat !== 'user_modules' && cat !== 'channels' && cat !== 'user_channels') {
            // Render groups - put direct items first
            if (data.groups) {
                // First render direct (ungrouped) items into the main vertical stack
                const directGroup = data.groups.get('_direct_');
                if (directGroup && directGroup.isDirect) {
                    directGroup.items.forEach(item => {
                        const itemEl = createSettingItem(item);
                        if (item.isModuleList) {
                            itemEl.classList.add('full-width-item');
                        }
                        itemsContainer.appendChild(itemEl);
                    });
                }

                // Create the grid container for grouped items
                const groupsGrid = document.createElement('div');
                groupsGrid.className = 'settings-groups-grid';

                // --- START OF SORTING LOGIC ---
                // 1. Convert Map to Array
                // 2. Filter out the '_direct_' key
                // 3. Sort the resulting array by the group's title
                const sortedGroupEntries = Array.from(data.groups.entries())
                .filter(([groupKey]) => groupKey !== '_direct_')
                .sort((a, b) => {
                    const titleA = a[1].title || '';
                    const titleB = b[1].title || '';
                    return titleA.localeCompare(titleB);
                });

                // 4. Iterate over the sorted array instead of the Map
                sortedGroupEntries.forEach(([groupKey, groupData]) => {
                    const groupContainer = document.createElement('div');
                    groupContainer.className = 'settings-group';
                    groupContainer.dataset.group = groupKey;

                    // Create header (clickable to collapse)
                    const header = document.createElement('div');
                    header.className = 'settings-group-header';
                    header.innerHTML = `
                    <span class="settings-group-title">
                    ${groupData.title}
                    </span>
                    `;

                    // Create content container
                    const content = document.createElement('div');
                    content.className = 'settings-group-content';

                    // Render items within the group
                    groupData.items.forEach(item => {
                        const itemEl = createSettingItem(item);
                        content.appendChild(itemEl);
                    });

                    groupContainer.appendChild(header);
                    groupContainer.appendChild(content);
                    groupsGrid.appendChild(groupContainer);
                });
                // --- END OF SORTING LOGIC ---

                itemsContainer.appendChild(groupsGrid);
            }
        }

        section.appendChild(itemsContainer);
        form.appendChild(section);
    }

    // Re-add the unsaved changes indicator after re-rendering
    updateUnsavedIndicator();
}


// Toggle settings group collapse
function toggleSettingsGroup(header) {
    const group = header.closest('.settings-group');
    const content = group.querySelector('.settings-group-content');
    const icon = header.querySelector('svg');
    const isExpanded = content.style.display !== 'none';

    content.style.display = isExpanded ? 'none' : 'block';
    icon.style.transform = isExpanded ? '' : 'rotate(90deg)';
}

// Create a setting item element
function createSettingItem(item) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-item';
    wrapper.dataset.key = item.key;

    if (item.type !== 'toggle_list') {
        const label = document.createElement('label');
        label.className = 'setting-label';
        label.textContent = formatLabel(item.key);
        wrapper.appendChild(label);
    }

    if (item.description) {
        const desc = document.createElement('p');
        desc.className = 'setting-description';
        desc.innerHTML = renderMarkdown(item.description);
        wrapper.appendChild(desc);
    }

    let inputEl;

    switch (item.type) {
        case 'reasoning_effort_slider':
            inputEl = createReasoningEffortSlider(item.key, item.value);
            break;
        case 'model':
            inputEl = createModelInput(item.key, item.value);
            break;
        case 'toggle_list':
            inputEl = createToggleListInput(item.key, item.value, !!item.isModuleList);
            break;
        case 'boolean':
            inputEl = createToggleInput(item.key, item.value, item.unsafe);
            break;
        case 'number':
            inputEl = createNumberInput(item.key, item.value);
            break;
        case 'array':
            inputEl = createArrayInput(item.key, item.value);
            break;
        case 'object':
            inputEl = createObjectInput(item.key, item.value);
            break;
        case 'textarea':
            inputEl = createTextareaInput(item.key, item.value);
            break;
        case 'password':
            inputEl = createPasswordInput(item.key, item.value);
            break;
        case 'slider':
            inputEl = createSliderInput(item.key, item.value, item.min, item.max, item.step);
            break;
        case 'percentage':
            inputEl = createPercentageSlider(item.key, item.value);
            break;
        case 'select':
            inputEl = createSelectInput(item.key, item.value, item.options);
            break;
        default:
            inputEl = createTextInput(item.key, item.value, item.type);
    }

    if (item.unsafe) {
        inputEl.classList.add('setting-item-unsafe');
    }

    wrapper.appendChild(inputEl);

    return wrapper;
}

// Generic Slider Input Implementation
function createSliderInput(key, value, min = 0, max = 100, step = 1) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-slider-container';

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const currentVal = parseFloat(currentValue) || parseFloat(value) || 0;
    const minVal = parseFloat(min);
    const maxVal = parseFloat(max);
    const stepVal = parseFloat(step) || 1;

    // Calculate percentage for the visual fill
    const getPercentage = (val) => ((val - minVal) / (maxVal - minVal)) * 100;
    const percentage = getPercentage(currentVal);

    const sliderRow = document.createElement('div');
    sliderRow.className = 'slider-row';
    sliderRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Value</span>
    <span class="slider-value" id="${key}-val-display">${currentVal}</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="${key}-input"
    min="${min}" max="${max}" step="${step}" value="${currentVal}">
    <div class="slider-fill" id="${key}-fill" style="width: ${percentage}%"></div>
    <div class="slider-handle" id="${key}-handle" style="left: ${percentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>${min}</span>
    <span>${max}</span>
    </div>
    </div>
    `;

    const input = sliderRow.querySelector('.slider-input');
    const fill = sliderRow.querySelector('.slider-fill');
    const handle = sliderRow.querySelector('.slider-handle');
    const display = sliderRow.querySelector('.slider-value');

    input.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        const p = getPercentage(val);
        display.textContent = val;
        fill.style.width = `${p}%`;
        handle.style.left = `${p}%`;
        handleSettingChange(key, val);
    });

    wrapper.appendChild(sliderRow);
    return wrapper;
}

// Create select dropdown input with description update
function createSelectInput(key, value, options) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-select-wrapper';
    wrapper.dataset.key = key;

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);

    const select = document.createElement('select');
    select.className = 'setting-input';
    select.dataset.key = key;

    // options is { "val1": "Label 1", "val2": "Label 2" }
    for (const [optKey, optValue] of Object.entries(options)) {
        const option = document.createElement('option');
        option.value = optKey;
        option.textContent = optKey;
        if (optKey === (currentValue !== undefined ? currentValue : value)) {
            option.selected = true;
        }
        select.appendChild(option);
    }

    const descContainer = document.createElement('div');
    descContainer.className = 'setting-select-description';
    descContainer.style.marginTop = '8px';
    descContainer.style.fontSize = '0.85em';
    descContainer.style.minHeight = '1.2em';

    const updateDescription = () => {
        descContainer.innerHTML = renderMarkdown(options[select.value]) || '';
    };

    select.onchange = () => {
        updateDescription();
        handleSettingChange(key, select.value);
    };

    wrapper.appendChild(select);
    wrapper.appendChild(descContainer);

    // Initial description update
    updateDescription();

    return wrapper;
}

// Create model dropdown input with refresh button
function createModelInput(key, value) {
    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const resolvedValue = currentValue !== undefined ? currentValue : value;

    const wrapper = document.createElement('div');
    wrapper.className = 'model-input-wrapper';
    wrapper.dataset.key = key;

    const inputContainer = document.createElement('div');
    inputContainer.className = 'model-input-container';

    // Check if we have cached models
    const hasModels = cachedModels && cachedModels.length > 0;

    if (hasModels) {
        // Create dropdown
        const select = document.createElement('select');
        select.className = 'setting-input model-select';
        select.dataset.key = key;

        // Add placeholder option
        const placeholderOption = document.createElement('option');
        placeholderOption.value = '';
        placeholderOption.textContent = '-- Select a model --';
        select.appendChild(placeholderOption);

        // Add models from cache
        cachedModels.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            if (model === resolvedValue) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        // If current value not in list, add it as custom
        if (resolvedValue && !cachedModels.find(m => m === resolvedValue)) {
            const customOption = document.createElement('option');
            customOption.value = resolvedValue;
            customOption.textContent = `${resolvedValue} (custom)`;
            customOption.selected = true;
            select.insertBefore(customOption, placeholderOption.nextSibling);
        }

        // Handle change
        select.onchange = () => {
            handleSettingChange(key, select.value);
        };

        inputContainer.appendChild(select);

        // Add refresh button
        const refreshBtn = document.createElement('button');
        refreshBtn.type = 'button';
        refreshBtn.className = 'model-refresh-btn';
        refreshBtn.title = 'Refresh model list';
        refreshBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"></path>
        <path d="M21 3v5h-5"></path>
        </svg>
        `;

        refreshBtn.onclick = async () => {
            refreshBtn.disabled = true;
            refreshBtn.classList.add('loading');

            const result = await fetchModels();

            refreshBtn.disabled = false;
            refreshBtn.classList.remove('loading');

            if (result.success) {
                // Re-render the model input
                const newInput = createModelInput(key, select.value);
                wrapper.replaceWith(newInput);
            } else {
                // Show error, fall back to text input
                const textInput = createTextInput(key, resolvedValue, 'text');
                wrapper.replaceWith(textInput);

                // Show error message
                const parent = textInput.closest('.setting-item');
                if (parent) {
                    let errorEl = parent.querySelector('.model-error-msg');
                    if (!errorEl) {
                        errorEl = document.createElement('p');
                        errorEl.className = 'model-error-msg';
                        parent.appendChild(errorEl);
                    }
                    errorEl.textContent = `Could not load models: ${result.error}`;
                }
            }
        };

        inputContainer.appendChild(refreshBtn);

    } else {
        // Fall back to text input
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'setting-input';
        input.dataset.key = key;
        input.value = resolvedValue ?? '';
        input.placeholder = 'Enter model name';
        input.oninput = () => handleSettingChange(key, input.value);

        inputContainer.appendChild(input);

        // Add refresh button to try loading models again
        const refreshBtn = document.createElement('button');
        refreshBtn.type = 'button';
        refreshBtn.className = 'model-refresh-btn';
        refreshBtn.title = 'Load models from API';
        refreshBtn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"></path>
        <path d="M21 3v5h-5"></path>
        </svg>
        `;

        refreshBtn.onclick = async () => {
            refreshBtn.disabled = true;
            refreshBtn.classList.add('loading');

            const result = await fetchModels();

            refreshBtn.disabled = false;
            refreshBtn.classList.remove('loading');

            if (result.success && result.models.length > 0) {
                // Re-render as dropdown
                const newInput = createModelInput(key, input.value);
                wrapper.replaceWith(newInput);
            } else {
                // Show error message
                const parent = wrapper.closest('.setting-item');
                if (parent) {
                    let errorEl = parent.querySelector('.model-error-msg');
                    if (!errorEl) {
                        errorEl = document.createElement('p');
                        errorEl.className = 'model-error-msg';
                        parent.appendChild(errorEl);
                    }
                    errorEl.textContent = `Could not load models: ${result.error}`;
                }
            }
        };

        inputContainer.appendChild(refreshBtn);

        // Show error if we have one
        if (modelsLoadError) {
            const errorMsg = document.createElement('p');
            errorMsg.className = 'model-error-msg';
            errorMsg.textContent = `Could not load models: ${modelsLoadError}`;
            inputContainer.appendChild(errorMsg);
        }
    }

    wrapper.appendChild(inputContainer);
    return wrapper;
}

// Create toggle list (for enabled/disabled arrays)
function createToggleListInput(key, value, isModuleList = false) {
    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const resolvedValue = currentValue !== undefined ? currentValue : value;

    const wrapper = document.createElement('div');
    wrapper.className = 'toggle-list';
    wrapper.dataset.key = key;

    // Use resolved value for getAllToggleItems to get current state
    const allItems = getAllToggleItems(resolvedValue);
    const enabledSet = new Set(resolvedValue.enabled || []);

    // descriptions and unsafeModules are computed metadata from moduleInfoCache.
    // On re-render they may be missing from the raw settingsData, so we fall back
    // to the passed-in value's metadata or recompute from the cache.
    let descriptions = resolvedValue.descriptions;
    let unsafeModules = resolvedValue.unsafeModules;

    if ((descriptions === undefined || descriptions === null) && value && value.descriptions) {
        descriptions = value.descriptions;
    }
    if ((unsafeModules === undefined || unsafeModules === null) && value && value.unsafeModules) {
        unsafeModules = value.unsafeModules;
    }
    // Final fallback: recompute from moduleInfoCache if still missing
    if (descriptions === undefined || descriptions === null) {
        descriptions = {};
        for (const itemName in moduleInfoCache) {
            if (moduleInfoCache[itemName].description) {
                descriptions[itemName] = moduleInfoCache[itemName].description;
            }
        }
    }
    if (unsafeModules === undefined || unsafeModules === null) {
        unsafeModules = {};
        for (const itemName in moduleInfoCache) {
            if (moduleInfoCache[itemName].unsafe) {
                unsafeModules[itemName] = true;
            }
        }
    }

    const sortedItems = allItems
    .filter(item => {
        // If we are in a module list and the item is unsafe, hide it if toggle is off
        if (isModuleList && unsafeModules[item] && !showUnsafeSettings) {
            return false;
        }
        return true;
    })
    .sort((a, b) => {
        const aEnabled = enabledSet.has(a);
        const bEnabled = enabledSet.has(b);
        const aUnsafe = unsafeModules[a] === true;
        const bUnsafe = unsafeModules[b] === true;

        // 1. Enabled items come first
        if (aEnabled && !bEnabled) return -1;
        if (!aEnabled && bEnabled) return 1;

        // 2. If both are disabled, unsafe ones go to the bottom
        if (!aEnabled && !bEnabled) {
            if (aUnsafe && !bUnsafe) return 1;
            if (!aUnsafe && bUnsafe) return -1;
        }

        // 3. Alphabetical sort within groups
        return a.localeCompare(b);
    });


    const status = document.createElement('div');
    status.className = 'toggle-list-status';
    status.innerHTML = `<span class="toggle-count">${enabledSet.size} of ${sortedItems.length} enabled</span>`;
    wrapper.appendChild(status);

    const grid = document.createElement('div');
    grid.className = 'toggle-list-grid';

    sortedItems.forEach(item => {
        const isEnabled = enabledSet.has(item);
        const isUnsafe = unsafeModules[item] === true;

        const itemWrapper = document.createElement('div');
        // Add 'module-card' class only if isModuleList is true
        itemWrapper.className = 'toggle-list-item' +
        (isEnabled ? ' enabled' : '') +
        (isModuleList ? ' module-card' : '') +
        (isUnsafe ? ' module-unsafe' : '');

        if (isModuleList) {
            // --- MODULE CARD STRUCTURE ---
            const topRow = document.createElement('div');
            topRow.className = 'toggle-list-top-row';

            const name = document.createElement('div');
            name.className = 'toggle-list-name';
            name.textContent = formatLabel(item);

            if (isUnsafe) {
                const unsafeBadge = document.createElement('span');
                unsafeBadge.className = 'module-unsafe-badge';
                unsafeBadge.textContent = 'UNSAFE';
                name.appendChild(unsafeBadge);
            }

            const toggle = document.createElement('label');
            toggle.className = 'toggle-switch';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = isEnabled;
            const slider = document.createElement('span');
            slider.className = 'toggle-slider';
            toggle.appendChild(checkbox);
            toggle.appendChild(slider);

            topRow.appendChild(name);
            topRow.appendChild(toggle);
            itemWrapper.appendChild(topRow);

            if (descriptions[item] !== "None") {
                const descContainer = document.createElement('div');
                descContainer.className = 'toggle-list-desc-container';

                const desc = document.createElement('div');
                desc.className = 'toggle-list-item-description';
                desc.textContent = descriptions[item];

                descContainer.appendChild(desc);
                itemWrapper.appendChild(descContainer);
            }

            checkbox.addEventListener('change', async () => {
                if (checkbox.checked && isUnsafe) {
                    const confirmed = await showConfirmDialog(
                        "You are about to activate an unsafe module. This module can perform actions that could potentially harm your system! Please be very sure of what you're doing. Proceed?"
                    );
                    if (!confirmed) {
                        checkbox.checked = false;
                        return;
                    }
                }

                const newState = checkbox.checked;
                itemWrapper.classList.toggle('enabled', newState);
                newState ? enabledSet.add(item) : enabledSet.delete(item);
                status.querySelector('.toggle-count').textContent = `${enabledSet.size} of ${sortedItems.length} enabled`;
                updateToggleListData(key, Array.from(enabledSet), sortedItems);
            });
        } else {
            // --- STANDARD LIST STRUCTURE ---
            const name = document.createElement('div');
            name.className = 'toggle-list-name';
            name.textContent = formatLabel(item);

            const toggle = document.createElement('label');
            toggle.className = 'toggle-switch';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = isEnabled;
            const slider = document.createElement('span');
            slider.className = 'toggle-slider';
            toggle.appendChild(checkbox);
            toggle.appendChild(slider);

            itemWrapper.appendChild(name);
            itemWrapper.appendChild(toggle);

            checkbox.onchange = async () => {
                const newState = checkbox.checked;

                if (newState && isUnsafe) {
                    const confirmed = await showConfirmDialog(
                        "You are about to enable an unsafe setting. This could potentially affect the stability or security of the application. Proceed?"
                    );
                    if (!confirmed) {
                        checkbox.checked = false;
                        return;
                    }
                }

                itemWrapper.classList.toggle('enabled', newState);
                newState ? enabledSet.add(item) : enabledSet.delete(item);
                status.querySelector('.toggle-count').textContent = `${enabledSet.size} of ${sortedItems.length} enabled`;
                updateToggleListData(key, Array.from(enabledSet), sortedItems);
            };
        }

        grid.appendChild(itemWrapper);
    });

    wrapper.appendChild(grid);
    return wrapper;
}


// Update toggle list data in settings
function updateToggleListData(key, enabledItems, allItems) {
    const parts = key.split('.');
    let current = settingsData;

    for (let i = 0; i < parts.length - 1; i++) {
        if (!(parts[i] in current)) {
            current[parts[i]] = {};
        }
        current = current[parts[i]];
    }

    const lastKey = parts[parts.length - 1];

    // Ensure the structure exists
    if (!current[lastKey]) {
        current[lastKey] = { enabled: [], disabled: [] };
    }

    // Update enabled and disabled arrays
    current[lastKey].enabled = enabledItems;
    current[lastKey].disabled = allItems.filter(item => !enabledItems.includes(item));

    settingsHasChanges = JSON.stringify(settingsData) !== JSON.stringify(settingsOriginal);
    updateUnsavedIndicator();

    // Note: Module enabled/disabled list changes are handled by server restart
    // (via hasChannelOrModuleChanges), so we don't track them for individual reload.
}

// Create text input (with sensitive field detection)
function createTextInput(key, value, type = 'text') {
    const keyLower = key.toLowerCase();
    const isSensitive = keyLower.includes('token') || keyLower.includes('key') ||
    keyLower.includes('secret') || keyLower.includes('password') ||
    keyLower.includes('credential');

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key) ?? '';

    // For sensitive fields, use a reveal/hide toggle
    if (isSensitive) {
        const wrapper = document.createElement('div');
        wrapper.className = 'sensitive-input-wrapper';
        wrapper.dataset.key = key;

        const input = document.createElement('input');
        input.type = 'password';
        input.className = 'setting-input sensitive-input';
        input.value = currentValue;
        input.dataset.revealed = 'false';

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'sensitive-toggle';
        toggleBtn.innerHTML = `
        <svg class="eye-closed" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
        <line x1="1" y1="1" x2="23" y2="23"></line>
        </svg>
        <svg class="eye-open" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none;">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
        <circle cx="12" cy="12" r="3"></circle>
        </svg>
        `;
        toggleBtn.onclick = () => {
            const isRevealed = input.dataset.revealed === 'true';
            if (isRevealed) {
                input.type = 'password';
                input.dataset.revealed = 'false';
                toggleBtn.querySelector('.eye-closed').style.display = '';
                toggleBtn.querySelector('.eye-open').style.display = 'none';
            } else {
                input.type = 'text';
                input.dataset.revealed = 'true';
                toggleBtn.querySelector('.eye-closed').style.display = 'none';
                toggleBtn.querySelector('.eye-open').style.display = '';
            }
        };

        input.oninput = () => handleSettingChange(key, input.value);

        wrapper.appendChild(input);
        wrapper.appendChild(toggleBtn);
        return wrapper;
    }

    // Regular text input
    const input = document.createElement('input');
    input.type = type === 'url' ? 'url' : (type === 'email' ? 'email' : 'text');
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = currentValue;
    input.oninput = () => handleSettingChange(key, input.value);
    return input;
}

// Create password input with toggle
function createPasswordInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: relative; display: flex; align-items: center;';

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key) ?? '';

    const input = document.createElement('input');
    input.type = 'password';
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = currentValue;
    input.style.paddingRight = '40px';
    input.oninput = () => handleSettingChange(key, input.value);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-toggle';
    toggle.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
    toggle.style.cssText = 'position: absolute; right: 10px; background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 4px;';
    toggle.onclick = () => {
        input.type = input.type === 'password' ? 'text' : 'password';
    };

    wrapper.appendChild(input);
    wrapper.appendChild(toggle);
    return wrapper;
}

// Create textarea
function createTextareaInput(key, value) {
    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key) ?? '';

    const textarea = document.createElement('textarea');
    textarea.className = 'setting-input setting-textarea';
    textarea.dataset.key = key;
    textarea.value = currentValue;
    textarea.oninput = () => handleSettingChange(key, textarea.value);
    return textarea;
}

// Create number input
function createNumberInput(key, value) {
    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key) ?? 0;

    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = currentValue;
    input.step = Number.isInteger(currentValue) ? '1' : '0.01';
    input.oninput = () => handleSettingChange(key, parseFloat(input.value) || 0);
    return input;
}

// Create toggle switch (single boolean)
function createToggleInput(key, value, isUnsafe = false) {
    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key) ?? value;

    const wrapper = document.createElement('div');
    wrapper.className = 'setting-toggle-wrapper';

    const label = document.createElement('label');
    label.className = 'toggle-switch';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = currentValue;

    const slider = document.createElement('span');
    slider.className = 'toggle-slider';

    const labelSpan = document.createElement('span');
    labelSpan.className = 'setting-toggle-label';
    labelSpan.textContent = currentValue ? 'Enabled' : 'Disabled';

    // Handle change
    checkbox.onchange = async () => {
        const newValue = checkbox.checked;

        if (newValue && isUnsafe) {
            const confirmed = await showConfirmDialog(
                "You are about to enable an unsafe setting. Proceed?"
            );
            if (!confirmed) {
                checkbox.checked = false;
                return;
            }
        }

        labelSpan.textContent = newValue ? 'Enabled' : 'Disabled';
        handleSettingChange(key, newValue);
    };

    label.appendChild(checkbox);
    label.appendChild(slider);

    wrapper.appendChild(label);
    wrapper.appendChild(labelSpan);
    return wrapper;
}

// Create array input
function createArrayInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-array';
    wrapper.dataset.key = key;

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const resolvedValue = currentValue !== undefined ? currentValue : value;
    const items = Array.isArray(resolvedValue) ? [...resolvedValue] : [];

    const header = document.createElement('div');
    header.className = 'setting-array-header';
    header.innerHTML = `
    <span class="setting-array-count">${items.length} item${items.length !== 1 ? 's' : ''}</span>
    <button class="setting-array-add" type="button">
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
    Add
    </button>
    `;

    const itemsContainer = document.createElement('div');
    itemsContainer.className = 'setting-array-items';

    function renderItems() {
        itemsContainer.innerHTML = '';
        header.querySelector('.setting-array-count').textContent =
        `${items.length} item${items.length !== 1 ? 's' : ''}`;

        if (items.length === 0) {
            itemsContainer.innerHTML = '<div class="setting-array-empty">No items added</div>';
            return;
        }

        items.forEach((item, index) => {
            const itemEl = document.createElement('div');
            itemEl.className = 'setting-array-item';

            const input = document.createElement('input');
            input.type = 'text';
            input.value = item;
            input.oninput = () => {
                items[index] = input.value;
                handleSettingChange(key, [...items]);
            };

            const removeBtn = document.createElement('button');
            removeBtn.className = 'setting-array-remove';
            removeBtn.type = 'button';
            removeBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
            removeBtn.onclick = () => {
                items.splice(index, 1);
                renderItems();
                handleSettingChange(key, [...items]);
            };

            itemEl.appendChild(input);
            itemEl.appendChild(removeBtn);
            itemsContainer.appendChild(itemEl);
        });
    }

    header.querySelector('.setting-array-add').onclick = () => {
        items.push('');
        renderItems();
        handleSettingChange(key, [...items]);
        const lastInput = itemsContainer.querySelector('.setting-array-item:last-child input');
        if (lastInput) lastInput.focus();
    };

        renderItems();
        wrapper.appendChild(header);
        wrapper.appendChild(itemsContainer);
        return wrapper;
}

// Create object input
function createObjectInput(key, value) {
    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const resolvedValue = currentValue !== undefined ? currentValue : value;
    const entries = resolvedValue && typeof resolvedValue === 'object' ? Object.entries(resolvedValue) : [];

    const wrapper = document.createElement('div');
    wrapper.className = 'setting-object';
    wrapper.dataset.key = key;

    const header = document.createElement('div');
    header.className = 'setting-object-header';
    header.innerHTML = `<span>${entries.length} propert${entries.length !== 1 ? 'ies' : 'y'}</span>`;

    const itemsContainer = document.createElement('div');
    itemsContainer.className = 'setting-object-items';

    function renderEntries() {
        itemsContainer.innerHTML = '';
        header.querySelector('span').textContent =
        `${entries.length} propert${entries.length !== 1 ? 'ies' : 'y'}`;

        if (entries.length === 0) {
            itemsContainer.innerHTML = '<div class="setting-array-empty">No properties</div>';
            return;
        }

        entries.forEach(([k, v], index) => {
            const itemEl = document.createElement('div');
            itemEl.className = 'setting-object-item';

            const keyInput = document.createElement('input');
            keyInput.type = 'text';
            keyInput.value = k;
            keyInput.placeholder = 'Key';
            keyInput.oninput = () => {
                entries[index][0] = keyInput.value;
                updateObjectValue();
            };

            const valueInput = document.createElement('input');
            valueInput.type = 'text';
            valueInput.value = typeof v === 'object' ? JSON.stringify(v) : String(v ?? '');
            valueInput.placeholder = 'Value';
            valueInput.oninput = () => {
                try {
                    entries[index][1] = JSON.parse(valueInput.value);
                } catch {
                    entries[index][1] = valueInput.value;
                }
                updateObjectValue();
            };

            const removeBtn = document.createElement('button');
            removeBtn.className = 'setting-array-remove';
            removeBtn.type = 'button';
            removeBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
            removeBtn.onclick = () => {
                entries.splice(index, 1);
                renderEntries();
                updateObjectValue();
            };

            itemEl.appendChild(keyInput);
            itemEl.appendChild(valueInput);
            itemEl.appendChild(removeBtn);
            itemsContainer.appendChild(itemEl);
        });
    }

    function updateObjectValue() {
        const obj = {};
        entries.forEach(([k, v]) => {
            if (k) obj[k] = v;
        });
            handleSettingChange(key, obj);
    }

    const addBtn = document.createElement('button');
    addBtn.className = 'setting-object-add';
    addBtn.type = 'button';
    addBtn.textContent = '+ Add Property';
    addBtn.onclick = () => {
        entries.push(['', '']);
        renderEntries();
    };

    renderEntries();
    wrapper.appendChild(header);
    wrapper.appendChild(itemsContainer);
    wrapper.appendChild(addBtn);
    return wrapper;
}

// Handle setting change
// Track which modules have had their settings changed (for reload-on-save)
let changedModuleSettings = new Set();

function handleSettingChange(key, value) {
    const parts = key.split('.');
    let current = settingsData;

    for (let i = 0; i < parts.length - 1; i++) {
        if (!(parts[i] in current)) {
            current[parts[i]] = {};
        }
        current = current[parts[i]];
    }

    current[parts[parts.length - 1]] = value;

    settingsHasChanges = JSON.stringify(settingsData) !== JSON.stringify(settingsOriginal);
    updateUnsavedIndicator();

    // Track which modules had settings changed
    // Module settings keys look like: "modules.settings.mymodule.something"
    // or "user_modules.settings.mymodule.something"
    if (parts.length >= 4) {
        if ((parts[0] === 'modules' || parts[0] === 'user_modules') && parts[1] === 'settings') {
            const moduleName = parts[2];
            changedModuleSettings.add(moduleName);
        }
    }
}

// Update unsaved changes indicator
function updateUnsavedIndicator() {
    const form = document.getElementById('settings-form');
    let indicator = form.querySelector('.settings-unsaved');

    if (settingsHasChanges && !indicator) {
        indicator = document.createElement('div');
        indicator.className = 'settings-unsaved';
        indicator.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        You have unsaved changes
        `;
        form.insertBefore(indicator, form.firstChild);
    } else if (!settingsHasChanges && indicator) {
        indicator.remove();
    }
}

// Reset settings form
function resetSettingsForm() {
    if (!settingsHasChanges) return;
    if (!confirm('Reset all changes to original values?')) return;

    settingsData = JSON.parse(JSON.stringify(settingsOriginal));
    settingsHasChanges = false;
    changedModuleSettings.clear();

    const categories = organizeSettingsIntoCategories(settingsData);
    renderSettingsForm(categories);
    updateUnsavedIndicator();
}

// Save settings to backend
async function saveSettings() {
    const activeSettingsCategory = document.querySelector('.settings-nav-item.active')?.dataset.category;

    // Appearance changes are local/immediate and don't trigger server saves here
    if (activeSettingsCategory === 'appearance') {
        toggleModal('settings');
        return;
    }

    if (!settingsHasChanges) return;

    const saveBtn = document.getElementById('settings-save-btn');
    const btnText = saveBtn.querySelector('.btn-text');
    const btnLoading = saveBtn.querySelector('.btn-loading');
    
    const hasChannelOrModuleChanges = detectChannelOrModuleChanges();
    const hasApiOrModelChanges = detectApiOrModelChanges();

    saveBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';

    try {
        const response = await fetch('/settings/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                settings: settingsData,
                changed_modules: Array.from(changedModuleSettings)
            }),
                                     signal: AbortSignal.timeout(15000)
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.message || `Server returned ${response.status}`);
        }

        // Success: Update the original reference so "unsaved" indicator clears
        settingsOriginal = JSON.parse(JSON.stringify(settingsData));
        settingsHasChanges = false;
        changedModuleSettings.clear();

        if (hasChannelOrModuleChanges) {
            await restartServer();
        } else if (hasApiOrModelChanges) {
            toggleModal('settings');
        } else {
            showSettingsSuccess();
        }

    } catch (err) {
        console.error('Failed to save settings:', err);

        // 7. IMPROVED ERROR HANDLING: Distinguish between server rejection and connection loss
        // If the error is a TypeError (usually happens when fetch fails due to network), it's an offline issue
        let userMessage = err.message;
        if (err instanceof TypeError || err.message.includes('Failed to fetch')) {
            userMessage = "Connection lost. Changes cannot be saved to the server, but you can still customize appearance locally.";
        }

        showSettingsError(userMessage);
    } finally {
        saveBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

// Detect if there are changes beyond just theme
// Detect if there are changes in channel or module settings
// Detect if there are changes beyond just theme
// Detect if there are changes in channel or module settings
function detectChannelOrModuleChanges() {
    for (const key of ['channels', 'user_channels', 'modules', 'user_modules']) {
        const newData = settingsData[key];
        const oldData = settingsOriginal[key];
        if (!newData || !oldData) continue;

        // Only check enabled/disabled arrays, not settings values
        const newEnabled = JSON.stringify(newData.enabled || []);
        const oldEnabled = JSON.stringify(oldData.enabled || []);
        const newDisabled = JSON.stringify(newData.disabled || []);
        const oldDisabled = JSON.stringify(oldData.disabled || []);

        if (newEnabled !== oldEnabled || newDisabled !== oldDisabled) {
            return true;
        }
    }
    return false;
}

// Detect if there are changes in channel settings specifically (for sidebar sub-items)
function detectChannelChanges() {
    if (!settingsData['channels']) return false;
    return JSON.stringify(settingsData['channels']) !== JSON.stringify(settingsOriginal['channels']);
}

// Detect if there are changes in API or model settings
function detectApiOrModelChanges() {
    for (const key of ['api', 'model']) {
        if (settingsData[key] && JSON.stringify(settingsData[key]) !== JSON.stringify(settingsOriginal[key])) {
            return true;
        }
    }
    return false;
}

function detectNonThemeChanges() {
    const themeKeys = ['theme', 'theme_mode', 'themeFamily', 'themeMode'];

    for (const key of Object.keys(settingsData)) {
        if (themeKeys.some(tk => key.toLowerCase().includes(tk.toLowerCase()))) {
            continue;
        }

        if (JSON.stringify(settingsData[key]) !== JSON.stringify(settingsOriginal[key])) {
            return true;
        }
    }

    return false;
}

// Restart the server
async function restartServer() {
    try {
        const restartMsg = document.getElementById('restart-message');
        if (restartMsg) {
            restartMsg.textContent = 'Restarting server...';
        }

        // show system logs
        closeModal('settings');
        showModal('log', true);

        const response = await fetch('/server/restart', {
            method: 'POST',
            signal: AbortSignal.timeout(5000)
        }).catch(() => {
            // Server might disconnect during restart, which is expected
            return { ok: true };
        });

        // the websocket signal handles the server's on_ready()
        // so that we can close the modal again/reload the page
    } catch (err) {
        pass
    }
}

// Show restart failed message
function showRestartFailed() {
    const notification = document.querySelector('.restart-notification');
    if (notification) {
        notification.classList.add('restart-failed');
        notification.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <div class="restart-content">
        <div class="restart-title">Restart Timeout</div>
        <div class="restart-desc">The server took too long to restart. Please refresh manually.</div>
        </div>
        `;
    }
}

// Show success message (theme only - no restart)
function showSettingsSuccess() {
    const form = document.getElementById('settings-form');
    const existing = form.querySelector('.setting-success-msg, .restart-notification');
    if (existing) existing.remove();

    const success = document.createElement('div');
    success.className = 'setting-success-msg';
    success.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
    Settings saved!
    `;

    form.insertBefore(success, form.firstChild);
    setTimeout(() => success.remove(), 3000);
    toggleModal('settings');
}

// Show error message
function showSettingsError(message) {
    const form = document.getElementById('settings-form');
    const existing = form.querySelector('.setting-error-msg');
    if (existing) existing.remove();

    const error = document.createElement('div');
    error.className = 'setting-error-msg';
    error.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
    ${escapeHtml(message)}
    `;

    form.insertBefore(error, form.firstChild);
}

// =============================================================================
// Theme Management
// =============================================================================

// System fonts that don't need external loading
const SYSTEM_FONTS = new Set([
    'default',
    'Arial',
    'Helvetica',
    'Calibri',
    'Segoe UI',
    'Times New Roman',
    'Georgia',
    'Verdana',
    'Trebuchet MS',
    'Palatino Linotype',
    'Tahoma',
    'Century Gothic',
    'Lucida Console',
    'Consolas',
    'Courier New',
    'Comic Sans MS'
]);

// Check if a font is a system font
function isSystemFont(fontId) {
    return fontId === 'default' || SYSTEM_FONTS.has(fontId);
}

// Load a font - handles both system fonts and Google Fonts
async function loadFont(fontId, weights = [400, 500, 600, 700]) {
    // System fonts don't need loading
    if (isSystemFont(fontId)) {
        return { success: true, type: 'system' };
    }

    // Try to load as Google Font
    if (typeof loadGoogleFont === 'function') {
        try {
            await loadGoogleFont(fontId, weights);
            return { success: true, type: 'google' };
        } catch (err) {
            console.warn(`Failed to load ${fontId} as Google Font, treating as system font`);
        }
    }

    // Fallback: assume it's a system font
    return { success: true, type: 'system' };
}

function applyCustomFont(fontId) {
    const root = document.documentElement;

    if (!fontId || fontId === 'default') {
        // Reset to system defaults
        root.style.setProperty('--font-family', "Arial, sans-serif");
        root.style.removeProperty('--code-font'); // This allows it to fall back to :root
    } else {
        const fontFamily = `'${fontId}', Arial, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;

        // Update UI font
        root.style.setProperty('--font-family', fontFamily);

        // OVERRIDE the code font with the user's selected font
        root.style.setProperty('--code-font', fontFamily);
    }

    // Update LocalStorage and the <link> tag as you already do...
    localStorage.setItem('fontFamily', fontId || 'default');

    const existingActiveLink = document.getElementById('font-active-link');
    if (existingActiveLink) existingActiveLink.remove();

    if (!isSystemFont(fontId)) {
        const link = document.createElement('link');
        link.id = 'font-active-link';
        link.rel = 'stylesheet';
        link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fontId)}:wght@400;500;600;700&display=swap`;
        document.head.appendChild(link);
    }
}

// Create custom font family dropdown with preview loading logic
function createFontFamilyDropdown(fontOptions, selectedFont, onChange) {
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-font-select';

    // Internal state to track selection changes
    let currentSelection = selectedFont;

    // --- Trigger Button ---
    const trigger = document.createElement('div');
    trigger.className = 'custom-font-trigger';
    trigger.setAttribute('tabindex', '0');
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-haspopup', 'listbox');

    const selectedOption = fontOptions.find(f => f.value === currentSelection) || fontOptions[0];
    const triggerFontFamily = currentSelection === 'default' ? 'inherit' : `'${currentSelection}', Arial, sans-serif`;

    // Structure: Value text + Arrow
    trigger.innerHTML = `
    <span class="custom-font-value" style="font-family: ${triggerFontFamily}">${selectedOption.label}</span>
    <svg class="custom-font-arrow" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
    `;

    // --- Dropdown List ---
    const dropdown = document.createElement('div');
    dropdown.className = 'custom-font-dropdown';
    dropdown.setAttribute('role', 'listbox');

    // Search Input
    const searchWrapper = document.createElement('div');
    searchWrapper.className = 'custom-font-search';
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search fonts...';
    searchInput.className = 'custom-font-search-input';
    searchWrapper.appendChild(searchInput);
    dropdown.appendChild(searchWrapper);

    // Options Container
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'custom-font-options';

    let filteredOptions = [...fontOptions];

    // FIX: Listener reference for cleanup
    let outsideClickListener = null;

    function renderOptions(options) {
        optionsContainer.innerHTML = '';

        options.forEach(opt => {
            const item = document.createElement('div');
            item.className = 'custom-font-option' + (opt.value === currentSelection ? ' selected' : '');
            item.dataset.value = opt.value;
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', opt.value === currentSelection);

            // Apply the font style to the item
            const fontFamily = opt.value === 'default' ? 'inherit' : `'${opt.value}', sans-serif`;
            item.style.fontFamily = fontFamily;

            // FIX: Wrap text in a span so it flexes correctly with the badge
            item.innerHTML = `<span class="option-text">${opt.label}</span>`;

            // Add Badges
            if (opt.value !== 'default') {
                if (isSystemFont(opt.value)) {
                    const badge = document.createElement('span');
                    badge.className = 'font-badge system';
                    badge.textContent = 'System';
                    item.appendChild(badge);
                } else {
                    // It's a Google Font
                    const badge = document.createElement('span');
                    badge.className = 'font-badge google';
                    badge.textContent = 'Google';
                    item.appendChild(badge);
                }
            }

            item.onclick = () => {
                // 1. Update internal state immediately
                currentSelection = opt.value;

                // 2. Update Visuals in list
                optionsContainer.querySelectorAll('.custom-font-option').forEach(el => {
                    el.classList.remove('selected');
                    el.setAttribute('aria-selected', 'false');
                });
                item.classList.add('selected');
                item.setAttribute('aria-selected', 'true');

                // 3. Update Trigger Display
                const valueSpan = trigger.querySelector('.custom-font-value');
                valueSpan.textContent = opt.label;
                valueSpan.style.fontFamily = fontFamily;

                // 4. Fire Callback (updates localStorage & main CSS)
                if (onChange) onChange(opt.value);

                // 5. Close Dropdown (triggers cleanup)
                closeDropdown();
            };

            optionsContainer.appendChild(item);
        });
    }

    renderOptions(filteredOptions);

    // Search Logic
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        filteredOptions = query
        ? fontOptions.filter(opt => opt.label.toLowerCase().includes(query) || opt.value.toLowerCase().includes(query))
        : [...fontOptions];
        renderOptions(filteredOptions);
    });

    searchInput.addEventListener('mousedown', (e) => e.stopPropagation());

    dropdown.appendChild(optionsContainer);

    // --- Open/Close Logic ---

    function openDropdown() {
        dropdown.classList.add('show');
        trigger.setAttribute('aria-expanded', 'true');

        // Load the fonts for preview
        loadPreviewFonts(fontOptions);

        // Reset search and render full list every time we open
        searchInput.value = '';
        filteredOptions = [...fontOptions];
        renderOptions(filteredOptions);

        // Focus and scroll
        setTimeout(() => searchInput.focus(), 50);
        const selectedEl = optionsContainer.querySelector('.custom-font-option.selected');
        if (selectedEl) selectedEl.scrollIntoView({ block: 'nearest' });

        // FIX: Add listener when opening
        if (!outsideClickListener) {
            outsideClickListener = (e) => {
                if (!wrapper.contains(e.target)) {
                    closeDropdown();
                }
            };
            document.addEventListener('click', outsideClickListener);
        }
    }

    function closeDropdown() {
        dropdown.classList.remove('show');
        trigger.setAttribute('aria-expanded', 'false');

        // Reset Search & Re-render (uses currentSelection state)
        searchInput.value = '';

        // FIX: Remove listener when closing to prevent accumulation
        if (outsideClickListener) {
            document.removeEventListener('click', outsideClickListener);
            outsideClickListener = null;
        }
    }

    trigger.addEventListener('click', () => {
        dropdown.classList.contains('show') ? closeDropdown() : openDropdown();
    });

    trigger.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            dropdown.classList.contains('show') ? closeDropdown() : openDropdown();
        } else if (e.key === 'Escape') {
            closeDropdown();
        }
    });

    // Note: Removed the global document.addEventListener here to prevent memory leaks.
    // It is now handled inside openDropdown/closeDropdown.

    wrapper.appendChild(trigger);
    wrapper.appendChild(dropdown);

    return wrapper;
}

// Helper: Load all fonts needed for the preview panel
function loadPreviewFonts(options) {
    // Identify Google Fonts
    const googleFonts = options
    .filter(opt => !isSystemFont(opt.value))
    .map(opt => opt.value);

    if (googleFonts.length === 0) return;

    // Create a single URL to load all fonts at once (efficient)
    const familyParam = googleFonts.map(f => `family=${f}:wght@400;500;700`).join('&');
    const href = `https://fonts.googleapis.com/css2?${familyParam}&display=swap`;

    // Check if preview link already exists
    if (document.getElementById('font-preview-batch')) return;

    const link = document.createElement('link');
    link.id = 'font-preview-batch';
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
}

// Theme section with custom font dropdown (updated createThemeSection function)
function createThemeSection() {
    const wrapper = document.createElement('div');
    wrapper.className = 'settings-theme-section';

    const savedFamily = localStorage.getItem('themeFamily') || 'monochrome';
    const savedMode = localStorage.getItem('themeMode') || 'dark';
    const savedFontSize = localStorage.getItem('fontSize') || '16';
    const savedFontFamily = localStorage.getItem('fontFamily') || 'default';

    // Font options with display names
    const fontOptions = [
        { value: 'default', label: 'System Default' },
        // System fonts
        { value: 'Arial', label: 'Arial' },
        { value: 'Helvetica', label: 'Helvetica' },
        { value: 'Calibri', label: 'Calibri' },
        { value: 'Segoe UI', label: 'Segoe UI' },
        { value: 'Georgia', label: 'Georgia' },
        { value: 'Verdana', label: 'Verdana' },
        { value: 'Trebuchet MS', label: 'Trebuchet MS' },
        { value: 'Tahoma', label: 'Tahoma' },
        { value: 'Consolas', label: 'Consolas' },
        { value: 'Courier New', label: 'Courier New' },
        { value: 'Comic Sans MS', label: 'Comic Sans MS' },
        // Google Fonts
        { value: 'Inter', label: 'Inter' },
        { value: 'Roboto', label: 'Roboto' },
        { value: 'Roboto Mono', label: 'Roboto Mono' },
        { value: 'Lato', label: 'Lato' },
        { value: 'Open Sans', label: 'Open Sans' },
        { value: 'Ubuntu', label: 'Ubuntu' },
        { value: 'Arimo', label: 'Arimo' },
        { value: 'Poppins', label: 'Poppins' },
        { value: 'Montserrat', label: 'Montserrat' },
        { value: 'Nunito', label: 'Nunito' },
        { value: 'Source Sans 3', label: 'Source Sans 3' },
        { value: 'Inconsolata', label: 'Inconsolata' },
        { value: 'Raleway', label: 'Raleway' },
        { value: 'Audiowide', label: 'Audiowide' },
        { value: 'Quantico', label: 'Quantico' },
        { value: 'Anta', label: 'Anta' },
        { value: 'Quicksand', label: 'Quicksand' },
        { value: 'Delius', label: 'Delius' },
        { value: 'Comfortaa', label: 'Comfortaa' },
        { value: 'Short Stack', label: 'Short Stack' },
        { value: 'Bubblegum Sans', label: 'Bubblegum Sans' },
        { value: 'Varela Round', label: 'Varela Round' },
        { value: 'Comic Relief', label: 'Comic Relief' },
        { value: 'Leckerli One', label: 'Leckerli One' },
        { value: 'Baloo 2', label: 'Baloo 2' },
        { value: 'Fredoka', label: 'Fredoka' },
        { value: 'Chewy', label: 'Chewy' },
        { value: 'Chonk', label: 'Chonk' },
        { value: "Jersey 10", label: "Jersey 10" },
        { value: "Jersey 15", label: "Jersey 15" },
        { value: "Jersey 20", label: "Jersey 20" },
        { value: "Jersey 25", label: "Jersey 25" },
        { value: "Jacquard 12", label: "Jacquard 12" },
        { value: "Jacquard 24", label: "Jacquard 24" },
        { value: "Jacquarda Bastarda 9", label: "Jacquarda Bastarda 9" },
        { value: "Tiny5", label: "Tiny5" },
        { value: "Micro 5", label: "Micro 5" },
        { value: "Bytesized", label: "Bytesized" },
        { value: "Bitcount Single", "label": "Bitcount Single" },
        { value: "Bitcount Grid Double", "label": "Bitcount Grid Double" },
        { value: 'Indie Flower', label: 'Indie Flower' },
        { value: 'Architects Daughter', label: 'Architects Daughter' },
        { value: 'Caveat', label: 'Caveat' },
        { value: 'Gochi Hand', label: 'Gochi Hand' },
        { value: 'Kalam', label: 'Kalam' },
        { value: 'Yellowtail', label: 'Yellowtail' },
        { value: 'Patrick Hand', label: 'Patrick Hand' },
        { value: 'Sour Gummy', label: 'Sour Gummy' },
        { value: 'Homemade Apple', label: 'Homemade Apple' },
        { value: 'Allura', label: 'Allura' },
        { value: 'Amatic SC', label: 'Amatic SC' },
        { value: 'Pacifico', label: 'Pacifico' },
        { value: 'Lobster', label: 'Lobster' },
        { value: 'Satisfy', label: 'Satisfy' },
        { value: 'Cookie', label: 'Cookie' },
        { value: 'Dancing Script', label: 'Dancing Script' },
        { value: 'Meow Script', label: 'Meow Script' },
        { value: 'Sacramento', label: 'Sacramento' },
        { value: 'Shadows Into Light', label: 'Shadows Into Light' },
        { value: 'Emilys Candy', label: 'Emilys Candy' },
    ];

    // ==========================================================================
    // TYPOGRAPHY SETTINGS SECTION (includes Reasoning Toggle)
    // ==========================================================================

    const typographySection = document.createElement('div');
    typographySection.className = 'typography-settings-section';

    const typographyHeader = document.createElement('div');
    typographyHeader.className = 'settings-section-header';
    typographyHeader.innerHTML = `
    <div class="settings-section-icon typography-icon">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="4 7 4 4 20 4 20 7"></polyline>
    <line x1="9" y1="20" x2="15" y2="20"></line>
    <line x1="12" y1="4" x2="12" y2="20"></line>
    </svg>
    </div>
    <div class="settings-section-title">
    <h4>Typography</h4>
    <p>Customize fonts and text appearance</p>
    </div>
    `;
    typographySection.appendChild(typographyHeader);

    const typographyControls = document.createElement('div');
    typographyControls.className = 'settings-control-group';

    // Font Family Selection
    const fontFamilyRow = document.createElement('div');
    fontFamilyRow.className = 'font-family-row';
    fontFamilyRow.innerHTML = `
    <label class="control-label">Font Family</label>
    <div class="font-family-wrapper" id="font-family-wrapper"></div>
    `;

    const fontDropdown = createFontFamilyDropdown(fontOptions, savedFontFamily, (font) => {
        applyCustomFont(font);
    });

    fontFamilyRow.querySelector('#font-family-wrapper').appendChild(fontDropdown);
    typographyControls.appendChild(fontFamilyRow);

    // Font Size Slider
    const fontSizeRow = document.createElement('div');
    fontSizeRow.className = 'font-size-row';

    const minSize = 12;
    const maxSize = 24;
    const sizePercentage = ((savedFontSize - minSize) / (maxSize - minSize)) * 100;

    fontSizeRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Font Size</span>
    <span class="slider-value" id="font-size-display">${savedFontSize}px</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="font-size-slider-settings"
    min="${minSize}" max="${maxSize}" value="${savedFontSize}">
    <div class="slider-fill" id="font-size-fill" style="width: ${sizePercentage}%"></div>
    <div class="slider-handle" id="font-size-handle" style="left: ${sizePercentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>Small</span>
    <span>Large</span>
    </div>
    </div>
    `;

    const fontSizeSlider = fontSizeRow.querySelector('#font-size-slider-settings');
    const fontSizeDisplay = fontSizeRow.querySelector('#font-size-display');
    const fontSizeFill = fontSizeRow.querySelector('#font-size-fill');
    const fontSizeHandle = fontSizeRow.querySelector('#font-size-handle');

    fontSizeSlider.addEventListener('input', function() {
        const size = parseInt(this.value);
        const percentage = ((size - minSize) / (maxSize - minSize)) * 100;

        fontSizeDisplay.textContent = `${size}px`;
        fontSizeFill.style.width = `${percentage}%`;
        fontSizeHandle.style.left = `${percentage}%`;

        document.documentElement.style.setProperty('--font-size-base', `${size}px`);
        localStorage.setItem('fontSize', size);
    });

    typographyControls.appendChild(fontSizeRow);

    // Chat Content Width Slider
    const chatWidthRow = document.createElement('div');
    chatWidthRow.className = 'font-size-row';
    const chatWidthMin = 20;
    const chatWidthMax = 100;
    const chatWidthVal = parseInt(localStorage.getItem('chatContentWidth') || '100');
    const chatWidthPercentage = ((chatWidthVal - chatWidthMin) / (chatWidthMax - chatWidthMin)) * 100;

    chatWidthRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Chat Width</span>
    <span class="slider-value" id="chat-width-display">${chatWidthVal}%</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="chat-width-slider-settings"
    min="${chatWidthMin}" max="${chatWidthMax}" value="${chatWidthVal}">
    <div class="slider-fill" id="chat-width-fill" style="width: ${chatWidthPercentage}%"></div>
    <div class="slider-handle" id="chat-width-handle" style="left: ${chatWidthPercentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>Narrow</span>
    <span>Full</span>
    </div>
    </div>
    `;

    const chatWidthSlider = chatWidthRow.querySelector('#chat-width-slider-settings');
    const chatWidthDisplay = chatWidthRow.querySelector('#chat-width-display');
    const chatWidthFill = chatWidthRow.querySelector('#chat-width-fill');
    const chatWidthHandle = chatWidthRow.querySelector('#chat-width-handle');

    chatWidthSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        const percentage = ((val - chatWidthMin) / (chatWidthMax - chatWidthMin)) * 100;
        chatWidthDisplay.textContent = `${val}%`;
        chatWidthFill.style.width = `${percentage}%`;
        chatWidthHandle.style.left = `${percentage}%`;
        document.documentElement.style.setProperty('--chat-content-width', `${val}%`);
        localStorage.setItem('chatContentWidth', val);
    });

    typographyControls.appendChild(chatWidthRow);

    // --- NEW: Message Bubble Width Slider ---
    const messageWidthRow = document.createElement('div');
    messageWidthRow.className = 'font-size-row'; // Reusing class for consistent styling
    const msgWidthMin = 30;
    const msgWidthMax = 100;
    const msgWidthVal = parseInt(localStorage.getItem('messageMaxWidth') || '60');
    const msgWidthPercentage = ((msgWidthVal - msgWidthMin) / (msgWidthMax - msgWidthMin)) * 100;

    messageWidthRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Message Width</span>
    <span class="slider-value" id="message-width-display">${msgWidthVal}%</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="message-width-slider-settings"
    min="${msgWidthMin}" max="${msgWidthMax}" value="${msgWidthVal}">
    <div class="slider-fill" id="message-width-fill" style="width: ${msgWidthPercentage}%"></div>
    <div class="slider-handle" id="message-width-handle" style="left: ${msgWidthPercentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>Narrow</span>
    <span>Wide</span>
    </div
    </div>
    `;

    const messageWidthSlider = messageWidthRow.querySelector('#message-width-slider-settings');
    const messageWidthDisplay = messageWidthRow.querySelector('#message-width-display');
    const messageWidthFill = messageWidthRow.querySelector('#message-width-fill');
    const messageWidthHandle = messageWidthRow.querySelector('#message-width-handle');

    messageWidthSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        const percentage = ((val - msgWidthMin) / (msgWidthMax - msgWidthMin)) * 100;
        messageWidthDisplay.textContent = `${val}%`;
        messageWidthFill.style.width = `${percentage}%`;
        messageWidthHandle.style.left = `${percentage}%`;
        document.documentElement.style.setProperty('--message-max-width', `${val}%`);
        localStorage.setItem('messageMaxWidth', val);
    });

    typographyControls.appendChild(messageWidthRow);

    // Reasoning Blocks Toggle (moved to Typography section)
    const reasoningExpandedByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';

    const reasoningToggleRow = document.createElement('div');
    reasoningToggleRow.className = 'toggle-row';
    reasoningToggleRow.innerHTML = `
    <div class="toggle-info">
    <span class="toggle-label">Expand Reasoning by Default</span>
    <span class="toggle-description">Show full thinking/reasoning blocks when messages load</span>
    </div>
    <label class="toggle-switch">
    <input type="checkbox" id="reasoning-expanded-checkbox" ${reasoningExpandedByDefault ? 'checked' : ''}>
    <span class="toggle-slider"></span>
    </label>
    `;

    const reasoningCheckbox = reasoningToggleRow.querySelector('#reasoning-expanded-checkbox');

    reasoningCheckbox.addEventListener('change', function() {
        localStorage.setItem('reasoningExpandedByDefault', this.checked ? 'true' : 'false');
    });

    typographyControls.appendChild(reasoningToggleRow);

    // --- NEW: Token Bar Visibility Toggle ---
    const isTokenBarVisible = localStorage.getItem('tokenBarVisible') !== 'false'; // Default to true
    const tokenBarToggleRow = document.createElement('div');
    tokenBarToggleRow.className = 'toggle-row';
    tokenBarToggleRow.innerHTML = `
    <div class="toggle-info">
    <span class="toggle-label">Token Usage Bar</span>
    <span class="toggle-description">Show/hide the token usage bar near input</span>
    </div>
    <label class="toggle-switch">
    <input type="checkbox" id="token-bar-visible-checkbox" ${isTokenBarVisible ? 'checked' : ''}>
    <span class="toggle-slider"></span>
    </label>
    `;

    const tokenBarCheckbox = tokenBarToggleRow.querySelector('#token-bar-visible-checkbox');
    tokenBarCheckbox.addEventListener('change', function() {
        const isVisible = this.checked;
        localStorage.setItem('tokenBarVisible', isVisible);

        const tokenBar = document.getElementById('token-usage-container');
        const tokenText = document.getElementById('token-usage-text');
        if (tokenBar) {
            tokenBar.style.display = isVisible ? 'flex' : 'none';
            tokenText.style.display = isVisible ? 'block' : 'none';
        }

        // Add this line to toggle the class on the body
        document.body.classList.toggle('token-bar-hidden', !isVisible);
    });
    typographyControls.appendChild(tokenBarToggleRow);


    typographySection.appendChild(typographyControls);
    wrapper.appendChild(typographySection);

    // ==========================================================================
    // AUDIO SETTINGS SECTION
    // ==========================================================================
    const audioSection = document.createElement('div');
    audioSection.className = 'audio-settings-section';

    const audioHeader = document.createElement('div');
    audioHeader.className = 'settings-section-header';
    audioHeader.innerHTML = `
    <div class="settings-section-icon audio-icon">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
    <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
    </svg>
    </div>
    <div class="settings-section-title">
    <h4>Sound Effects</h4>
    <p>Configure sound effects</p>
    </div>
    `;
    audioSection.appendChild(audioHeader);

    audioControls = document.createElement('div');
    audioControls.className = 'settings-control-group';

    // Volume Control
    const currentVolume = Math.round((parseFloat(localStorage.getItem('typewriterVolume') || '0.7')) * 100);

    // Sync volume with manager on load
    TypewriterAudioManager.setVolume(currentVolume / 100);

    const volumeRow = document.createElement('div');
    volumeRow.className = 'slider-row volume-row';

    const getVolumeIcon = (vol) => {
        if (vol === 0) {
            return `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <line x1="23" y1="9" x2="17" y2="15"></line>
            <line x1="17" y1="9" x2="23" y2="15"></line>
            </svg>`;
        } else if (vol < 50) {
            return `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            </svg>`;
        }
        return `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
        </svg>`;
    };

    volumeRow.innerHTML = `
    <div class="slider-header">
    <div class="volume-icon-wrapper" id="volume-icon">${getVolumeIcon(currentVolume)}</div>
    <span class="slider-label">Volume</span>
    <span class="slider-value" id="typewriter-volume-value">${currentVolume}%</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="typewriter-volume-slider"
    min="0" max="100" value="${currentVolume}">
    <div class="slider-fill" id="volume-fill" style="width: ${currentVolume}%"></div>
    <div class="slider-handle" id="volume-handle" style="left: ${currentVolume}%"></div>
    </div>
    <div class="slider-labels">
    <span>Mute</span>
    <span>Max</span>
    </div>
    </div>
    `;

    const volumeSlider = volumeRow.querySelector('#typewriter-volume-slider');
    const volumeDisplay = volumeRow.querySelector('#typewriter-volume-value');
    const volumeFill = volumeRow.querySelector('#volume-fill');
    const volumeHandle = volumeRow.querySelector('#volume-handle');
    const volumeIcon = volumeRow.querySelector('#volume-icon');

    volumeSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        volumeDisplay.textContent = `${val}%`;
        volumeFill.style.width = `${val}%`;
        volumeHandle.style.left = `${val}%`;
        volumeIcon.innerHTML = getVolumeIcon(val);
        TypewriterAudioManager.setVolume(val / 100);
        localStorage.setItem('typewriterVolume', val / 100);
    });

    audioControls.appendChild(volumeRow);

    // === SEPARATE TOKEN GENERATION VOLUME SLIDER ===
    const tokenVolumeRow = document.createElement('div');
    tokenVolumeRow.className = 'slider-row';

    const savedTokenVolume = Math.round((parseFloat(localStorage.getItem('tokenVolume') || '0.6')) * 100);

    tokenVolumeRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Token Generation Volume</span>
    <span class="slider-value" id="token-volume-value">${savedTokenVolume}%</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="token-volume-slider"
    min="0" max="100" value="${savedTokenVolume}">
    <div class="slider-fill" id="token-volume-fill" style="width: ${savedTokenVolume}%"></div>
    <div class="slider-handle" id="token-volume-handle" style="left: ${savedTokenVolume}%"></div>
    </div>
    <div class="slider-labels">
    <span>Mute</span>
    <span>Max</span>
    </div>
    </div>
    `;

    const tokenVolumeSlider = tokenVolumeRow.querySelector('#token-volume-slider');
    const tokenVolumeDisplay = tokenVolumeRow.querySelector('#token-volume-value');
    const tokenVolumeFill = tokenVolumeRow.querySelector('#token-volume-fill');
    const tokenVolumeHandle = tokenVolumeRow.querySelector('#token-volume-handle');

    tokenVolumeSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        tokenVolumeDisplay.textContent = `${val}%`;
        tokenVolumeFill.style.width = `${val}%`;
        tokenVolumeHandle.style.left = `${val}%`;
        localStorage.setItem('tokenVolume', val / 100);
        
        // Update manager if it supports specific sound volume
        if (typeof TypewriterAudioManager !== 'undefined' && TypewriterAudioManager.setTokenVolume) {
            TypewriterAudioManager.setTokenVolume(val / 100);
        }
    });

    audioControls.appendChild(tokenVolumeRow);

    // Sound File Inputs
    const soundContainer = document.createElement('div');
    soundContainer.className = 'sound-inputs-container';

    // Helper function to check if audio is loaded in manager or localStorage
    const isAudioLoaded = (id) => {
        // Check if audio buffer exists in manager
        if (TypewriterAudioManager.buffers && TypewriterAudioManager.buffers[id]) {
            return true;
        }
        // Check localStorage for saved data
        return !!localStorage.getItem(`${id}SoundData`);
    };

    const createSoundInput = (id, labelText, iconPath) => {
        // ── Safe Defaults Check ──
        let isEnabled = true;
        try {
            if (typeof localStorage !== 'undefined') {
                const stored = localStorage.getItem(`${id}Enabled`);
                if (stored !== null) {
                    isEnabled = stored === 'true';
                } else {
                    // Fallback to built-in defaults if storage is missing
                    isEnabled = (typeof SOUND_DEFAULTS !== 'undefined' && SOUND_DEFAULTS[id] !== false);
                }
            }
        } catch (e) {
            console.warn(`[Settings] Storage unavailable for ${id}, using defaults.`);
        }

        // ── Safe Audio Check ──
        let hasAudio = false;
        try {
            if (typeof TypewriterAudioManager !== 'undefined') {
                hasAudio = !!TypewriterAudioManager.buffers?.[id];
                if (!hasAudio && typeof localStorage !== 'undefined') {
                    hasAudio = !!localStorage.getItem(`${id}SoundData`);
                }
            }
        } catch (e) {
            console.warn(`[Settings] Audio manager unavailable.`);
        }

        const savedName = typeof localStorage !== 'undefined' ? localStorage.getItem(`${id}SoundName`) : null;

        const container = document.createElement('div');
        container.className = 'sound-input-card';
        container.dataset.soundId = id;

        container.innerHTML = `
        <div class="sound-header">
        <div class="sound-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        ${iconPath}
        </svg>
        </div>
        <div class="sound-info">
        <span class="sound-label">${labelText}</span>
        <span class="sound-filename ${hasAudio ? 'loaded' : ''}" id="${id}-filename">${savedName || 'Using generated sound'}</span>
        </div>
        </div>
        <div class="sound-footer">
        <div class="setting-toggle-wrapper">
        <label class="toggle-switch">
        <input type="checkbox" id="${id}-enabled-checkbox" ${isEnabled ? 'checked' : ''}>
        <span class="toggle-slider"></span>
        </label>
        <span class="setting-toggle-label">Enabled</span>
        </div>
        <div class="sound-actions">
        <button type="button" class="sound-action-btn preview" id="${id}-preview-btn" title="Preview sound" ${!hasAudio ? 'disabled' : ''}>
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        </button>
        <button type="button" class="sound-action-btn upload" id="${id}-upload-btn" title="Upload sound">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="17 8 12 3 7 8"></polyline>
        <line x1="12" y1="3" x2="12" y2="15"></line>
        </svg>
        </button>
        <button type="button" class="sound-action-btn clear" id="${id}-clear-btn" title="Remove sound" ${!hasAudio ? 'disabled' : ''}>
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
        </button>
        </div>
        </div>
        <input type="file" accept="audio/*" id="${id}-file-input" style="position: absolute; left: -9999px; top: auto; width: 1px; height: 1px; overflow: hidden;">
        `;

        const previewBtn = container.querySelector(`#${id}-preview-btn`);
        const uploadBtn = container.querySelector(`#${id}-upload-btn`);
        const clearBtn = container.querySelector(`#${id}-clear-btn`);
        const fileInput = container.querySelector(`#${id}-file-input`);
        const filenameDisplay = container.querySelector(`#${id}-filename`);

        // ── Safe Event Handlers ──
        uploadBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            try {
                if (typeof TypewriterAudioManager !== 'undefined' && typeof TypewriterAudioManager.saveFile === 'function') {
                    await TypewriterAudioManager.saveFile(id, file);
                    if (typeof localStorage !== 'undefined') localStorage.setItem(`${id}SoundName`, file.name);
                    filenameDisplay.textContent = file.name;
                    filenameDisplay.classList.add('loaded');
                    filenameDisplay.classList.remove('error');
                    previewBtn.disabled = false;
                    clearBtn.disabled = false;
                }
            } catch (err) {
                console.error('Failed to load audio:', err);
                filenameDisplay.textContent = 'Error loading file';
                filenameDisplay.classList.add('error');
                filenameDisplay.classList.remove('loaded');
                setTimeout(() => {
                    filenameDisplay.classList.remove('error');
                    filenameDisplay.textContent = savedName || 'No file selected';
                }, 2000);
            }
        });

        previewBtn.addEventListener('click', () => {
            try {
                if (typeof TypewriterAudioManager !== 'undefined' && typeof TypewriterAudioManager.play === 'function') {
                    TypewriterAudioManager.play(id);
                    previewBtn.classList.add('playing');
                    setTimeout(() => previewBtn.classList.remove('playing'), 500);
                }
            } catch (e) { console.warn('Play failed:', e); }
        });

        clearBtn.addEventListener('click', () => {
            try {
                if (typeof TypewriterAudioManager !== 'undefined' && typeof TypewriterAudioManager.deleteFile === 'function') {
                    TypewriterAudioManager.deleteFile(id);
                }
                if (typeof localStorage !== 'undefined') localStorage.removeItem(`${id}SoundName`);
                filenameDisplay.textContent = 'No file selected';
                filenameDisplay.classList.remove('loaded');
                previewBtn.disabled = true;
                clearBtn.disabled = true;
                fileInput.value = '';
            } catch (e) { console.warn('Clear failed:', e); }
        });

        enabledCheckbox = container.querySelector(`#${id}-enabled-checkbox`);
        enabledCheckbox.addEventListener('change', function() {
            const newState = this.checked;
            try {
                if (typeof localStorage !== 'undefined') {
                    localStorage.setItem(`${id}Enabled`, String(newState));
                }
            } catch (e) { console.warn(`[Settings] Failed to save ${id}Enabled:`, e); }
        });

        return container;
    };



    const typewriterIcon = '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>';
    const completionIcon = '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>';

    const sendSoundInput = createSoundInput(
        'send_message',
        'Message sent',
        typewriterIcon
    );
    soundContainer.appendChild(sendSoundInput);

    const responseSoundInput = createSoundInput(
        'response_start',
        'Message received',
        typewriterIcon
    );
    soundContainer.appendChild(responseSoundInput);

    const processingSoundInput = createSoundInput(
        'processing',
        'Prompt processing',
        typewriterIcon
    );
    soundContainer.appendChild(processingSoundInput);

    const tokenSoundInput = createSoundInput(
        'token',
        'Token generation',
        typewriterIcon
    );
    soundContainer.appendChild(tokenSoundInput);

    const twSoundInput = createSoundInput(
        'typing',
        'Typewriter',
        typewriterIcon
    );
    soundContainer.appendChild(twSoundInput);

    const reasoningSoundInput = createSoundInput(
        'reasoning_end',
        'Done thinking',
        typewriterIcon
    );
    soundContainer.appendChild(reasoningSoundInput);

    const compSoundInput = createSoundInput(
        'completion',
        'Response finished',
        completionIcon
    );

    soundContainer.appendChild(compSoundInput);

    audioControls.appendChild(soundContainer);

    // === TYPING FREQUENCY SLIDER ===
    const typingFreqRow = document.createElement('div');
    typingFreqRow.className = 'slider-row';

    const savedFreq = parseInt(localStorage.getItem('typingFreq')) || 600;
    const freqMin = 100;
    const freqMax = 8000;
    const freqStep = 100;
    const freqPercentage = ((savedFreq - freqMin) / (freqMax - freqMin)) * 100;

    typingFreqRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Typing Sound Frequency</span>
    <span class="slider-value" id="typing-freq-value">${savedFreq} Hz</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="typing-freq-slider"
    min="${freqMin}" max="${freqMax}" step="${freqStep}" value="${savedFreq}">
    <div class="slider-fill" id="freq-fill" style="width: ${freqPercentage}%"></div>
    <div class="slider-handle" id="freq-handle" style="left: ${freqPercentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>${freqMin} Hz</span>
    <span>${freqMax} Hz</span>
    </div>
    </div>
    `;

    const freqSlider = typingFreqRow.querySelector('#typing-freq-slider');
    const freqDisplay = typingFreqRow.querySelector('#typing-freq-value');
    const freqFill = typingFreqRow.querySelector('#freq-fill');
    const freqHandle = typingFreqRow.querySelector('#freq-handle');

    freqSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        const percentage = ((val - freqMin) / (freqMax - freqMin)) * 100;
        freqDisplay.textContent = `${val} Hz`;
        freqFill.style.width = `${percentage}%`;
        freqHandle.style.left = `${percentage}%`;
        localStorage.setItem('typingFreq', val);
    });

    audioControls.appendChild(typingFreqRow);

    // === TOKEN GENERATION FREQUENCY SLIDER ===
    const tokenFreqRow = document.createElement('div');
    tokenFreqRow.className = 'slider-row';

    const savedTokenFreq = parseInt(localStorage.getItem('tokenFreq')) || 9000;
    const tokenFreqMin = 100;
    const tokenFreqMax = 9000;
    const tokenFreqStep = 100;
    const tokenFreqPercentage = ((savedTokenFreq - tokenFreqMin) / (tokenFreqMax - tokenFreqMin)) * 100;

    tokenFreqRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Token Generation Sound Frequency</span>
    <span class="slider-value" id="token-freq-value">${savedTokenFreq} Hz</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="token-freq-slider"
    min="${tokenFreqMin}" max="${tokenFreqMax}" step="${tokenFreqStep}" value="${savedTokenFreq}">
    <div class="slider-fill" id="token-freq-fill" style="width: ${tokenFreqPercentage}%"></div>
    <div class="slider-handle" id="token-freq-handle" style="left: ${tokenFreqPercentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>${tokenFreqMin} Hz</span>
    <span>${tokenFreqMax} Hz</span>
    </div>
    </div>
    `;

    const tokenFreqSlider = tokenFreqRow.querySelector('#token-freq-slider');
    const tokenFreqDisplay = tokenFreqRow.querySelector('#token-freq-value');
    const tokenFreqFill = tokenFreqRow.querySelector('#token-freq-fill');
    const tokenFreqHandle = tokenFreqRow.querySelector('#token-freq-handle');

    tokenFreqSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        const percentage = ((val - tokenFreqMin) / (tokenFreqMax - tokenFreqMin)) * 100;
        tokenFreqDisplay.textContent = `${val} Hz`;
        tokenFreqFill.style.width = `${percentage}%`;
        tokenFreqHandle.style.left = `${percentage}%`;
        localStorage.setItem('tokenFreq', val);
    });

    audioControls.appendChild(tokenFreqRow);


    audioSection.appendChild(audioControls);

    wrapper.appendChild(audioSection);

    // ==========================================================================
    // TYPEWRITER SETTINGS SECTION
    // ==========================================================================

    const twSection = document.createElement('div');
    twSection.className = 'audio-settings-section';

    const twHeader = document.createElement('div');
    twHeader.className = 'settings-section-header';
    twHeader.innerHTML = `
    <div class="settings-section-icon audio-icon">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
    <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
    </svg>
    </div>
    <div class="settings-section-title">
    <h4>Typewriter Effect</h4>
    <p>Configure text streaming animation and sounds</p>
    </div>
    `;
    twSection.appendChild(twHeader);

    // Enable/Disable Toggle
    const savedTypewriterEnabled = localStorage.getItem('typewriterEnabled') === 'true';

    const twToggleRow = document.createElement('div');
    twToggleRow.className = 'toggle-row';
    twToggleRow.innerHTML = `
    <div class="toggle-info">
    <span class="toggle-label">Enable</span>
    <span class="toggle-description">Simulate typing by showing one character at a time</span>
    </div>
    <label class="toggle-switch">
    <input type="checkbox" id="typewriter-enabled-checkbox" ${savedTypewriterEnabled ? 'checked' : ''}>
    <span class="toggle-slider"></span>
    </label>
    `;

    const twCheckbox = twToggleRow.querySelector('#typewriter-enabled-checkbox');

    // Controls Container (show/hide based on toggle)
    const twControls = document.createElement('div');
    twControls.className = 'audio-control-group';
    twControls.style.display = savedTypewriterEnabled ? 'flex' : 'none';

    // Speed Slider
    const currentSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
    const minSpeed = 1;
    const maxSpeed = 200;
    const speedPercentage = ((currentSpeed - minSpeed) / (maxSpeed - minSpeed)) * 100;

    const speedRow = document.createElement('div');
    speedRow.className = 'slider-row';
    speedRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Speed</span>
    <span class="slider-value" id="typewriter-speed-value">${currentSpeed}ms</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="typewriter-speed-slider"
    min="${minSpeed}" max="${maxSpeed}" value="${currentSpeed}">
    <div class="slider-fill" id="speed-fill" style="width: ${speedPercentage}%"></div>
    <div class="slider-handle" id="speed-handle" style="left: ${speedPercentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>Fast</span>
    <span>Slow</span>
    </div>
    </div>
    `;

    const speedSlider = speedRow.querySelector('#typewriter-speed-slider');
    const speedDisplay = speedRow.querySelector('#typewriter-speed-value');
    const speedFill = speedRow.querySelector('#speed-fill');
    const speedHandle = speedRow.querySelector('#speed-handle');

    speedSlider.addEventListener('input', function() {
        const val = parseInt(this.value);
        const percentage = ((val - minSpeed) / (maxSpeed - minSpeed)) * 100;
        speedDisplay.textContent = `${val}ms`;
        speedFill.style.width = `${percentage}%`;
        speedHandle.style.left = `${percentage}%`;
        localStorage.setItem('typewriterSpeed', val);
    });

    twControls.appendChild(speedRow);
    twSection.appendChild(twToggleRow);
    twSection.appendChild(twControls);
    wrapper.appendChild(twSection);

    // Toggle handler - show/hide controls with display: none
    twCheckbox.addEventListener('change', function() {
        const isEnabled = this.checked;
        localStorage.setItem('typewriterEnabled', isEnabled ? 'true' : 'false');

        // Show/hide controls with fade animation
        if (isEnabled) {
            twControls.style.display = 'flex';
            // Trigger reflow for animation
            twControls.offsetHeight;
            twControls.classList.add('visible');
        } else {
            twControls.classList.remove('visible');
            // Wait for fade out before hiding
            setTimeout(() => {
                if (!twCheckbox.checked) {
                    twControls.style.display = 'none';
                }
            }, 200);
        }
    });

    // Initialize visibility state
    if (savedTypewriterEnabled) {
        twControls.classList.add('visible');
    }

    const advancedSettingsSection = document.createElement('div');
    const advancedSettingsLabel = document.createElement('h4');
    advancedSettingsLabel.textContent = 'Advanced Settings';
    advancedSettingsLabel.className = 'section-heading';

    const unsafeVisibilityToggleRow = document.createElement('div');
    unsafeVisibilityToggleRow.className = 'toggle-row toggle-unsafe';
    unsafeVisibilityToggleRow.style.marginTop = '16px';
    unsafeVisibilityToggleRow.style.paddingTop = '16px';
    unsafeVisibilityToggleRow.style.borderTop = '1px solid var(--border-color)';

    unsafeVisibilityToggleRow.innerHTML = `
    <div class="toggle-info">
    <span class="toggle-label">Show Unsafe Settings</span>
    <span class="toggle-description">Unsafe settings are things like total system shell access, code execution, and anything else that could easily compromise your security or data. They are hidden by default because they are risky, but they are available for power users through this toggle.</span>
    </div>
    <label class="toggle-switch">
    <input type="checkbox" id="show-unsafe-toggle">
    <span class="toggle-slider"></span>
    </label>
    `;

    const unsafeCheckbox = unsafeVisibilityToggleRow.querySelector('#show-unsafe-toggle');
    unsafeCheckbox.checked = showUnsafeSettings;

    unsafeCheckbox.addEventListener('change', function() {
        showUnsafeSettings = this.checked;
        localStorage.setItem('showUnsafeSettings', this.checked);

        // Re-render the entire form to apply the filter
        // Since loadSettings() triggers organizeSettingsIntoCategories()
        loadSettings();
    });

    advancedSettingsSection.appendChild(unsafeVisibilityToggleRow);

    wrapper.appendChild(advancedSettingsSection);

    // ==========================================================================
    // THEME MODE TOGGLE
    // ==========================================================================

    const themeModeSection = document.createElement('div');
    themeModeSection.className = 'theme-mode-section';

    const modeToggle = document.createElement('div');
    modeToggle.className = 'theme-mode-toggle';

    modeToggle.innerHTML = `
    <span class="theme-mode-label dark-label">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
    Dark
    </span>
    <label class="theme-switch">
    <input type="checkbox" id="theme-mode-checkbox-settings" ${savedMode === 'light' ? 'checked' : ''}>
    <span class="theme-slider"></span>
    </label>
    <span class="theme-mode-label light-label">
    Light
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
    </span>
    `;

    const checkbox = modeToggle.querySelector('#theme-mode-checkbox-settings');
    checkbox.addEventListener('change', function() {
        const mode = this.checked ? 'light' : 'dark';
        currentThemeMode = mode;
        applyTheme(currentThemeFamily, mode);
        updateThemeButtonsInSettings();
    });

    themeModeSection.appendChild(modeToggle);
    wrapper.appendChild(themeModeSection);

    // ==========================================================================
    // COLOR THEME GRID
    // ==========================================================================

    const colorThemeSection = document.createElement('div');
    colorThemeSection.className = 'color-theme-section';

    const themeLabel = document.createElement('h4');
    themeLabel.textContent = 'Color Theme';
    themeLabel.className = 'section-heading';
    colorThemeSection.appendChild(themeLabel);

    const themeGrid = document.createElement('div');
    themeGrid.className = 'theme-grid';
    themeGrid.id = 'theme-grid-settings';

    Object.entries(window.themes).forEach(([family, themeData]) => {
        // themeData is now { dark: { vars... }, light: { vars... } }
        const previewVars = themeData[savedMode] || themeData['dark'];
        if (!previewVars) return;

        const btn = document.createElement('button');
        btn.className = 'theme-btn' + (family === savedFamily ? ' active' : '');
        btn.dataset.family = family;
        btn.type = 'button';

        const bgColor = previewVars['--bg-primary'];
        const accentColor = previewVars['--accent'];
        const themeName = family.charAt(0).toUpperCase() + family.slice(1); // Simple title case

        btn.innerHTML = `
        <div class="theme-preview" style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);"></div>
        <span class="theme-name">${themeName}</span>
        `;

        btn.onclick = () => {
            currentThemeFamily = family;
            applyTheme(family, currentThemeMode);
            updateThemeButtonsInSettings();
        };

        themeGrid.appendChild(btn);
    });

    colorThemeSection.appendChild(themeGrid);
    wrapper.appendChild(colorThemeSection);

    return wrapper;
}




function updateThemeButtonsInSettings() {
    const grid = document.getElementById('theme-grid-settings');
    if (!grid) return;

    grid.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.family === currentThemeFamily);
    });

    const checkbox = document.getElementById('theme-mode-checkbox-settings');
    if (checkbox) {
        checkbox.checked = (currentThemeMode === 'light');
    }
}

// Helper to clear all sidebar selections and collapse sub-lists
function clearSidebarSelections() {
    activeModule = null;
    activeChannel = null;
    modulesExpanded = { modules: false, user_modules: false, channels: false, user_channels: false };

    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.classList.remove('active');
    });

    document.querySelectorAll('.module-sub-list button').forEach(btn => {
        btn.classList.remove('active');
    });

    document.querySelectorAll('.module-sub-list').forEach(list => {
        list.classList.remove('expanded');
        list.style.display = 'none';
    });
}

// Override toggleModal for settings
const originalToggleModal = toggleModal;
toggleModal = function(modalName) {
    if (modalName === 'settings') {
        const overlay = document.getElementById('settings-overlay');
        const modal = document.getElementById('settings-modal');

        if (overlay.classList.contains('show')) {
            if (settingsHasChanges) {
                if (!confirm('You have unsaved changes. Close without saving?')) {
                    return;
                }
            }
            overlay.classList.remove('show');
            modal.classList.remove('show');

            // Clear active selections from sidebar when dialog closes
            activeSettingsCategory = null;
            clearSidebarSelections();
        } else {
            overlay.classList.add('show');
            modal.classList.add('show');
            loadSettings();
        }
    } else {
        originalToggleModal(modalName);
    }
};

// Apply chat content width on script load
(function initChatWidth() {
    const width = localStorage.getItem('chatContentWidth') || '100';
    document.documentElement.style.setProperty('--chat-content-width', width + '%');
})();

// Apply message max width on script load
(function initMessageMaxWidth() {
    const val = localStorage.getItem('messageMaxWidth') || '60';
    document.documentElement.style.setProperty('--message-max-width', val + '%');
})();

// Apply token bar visibility on script load
(function initTokenBarVisibility() {
    const isVisible = localStorage.getItem('tokenBarVisible') !== 'false';
    const tokenBar = document.getElementById('token-usage-container');
    if (tokenBar) {
        tokenBar.style.display = isVisible ? 'flex' : 'none';
    }
    // Add this line to ensure the body class is correct on page load
    document.body.classList.toggle('token-bar-hidden', !isVisible);
})();

// Create reasoning effort slider
function createReasoningEffortSlider(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-item';
    wrapper.dataset.key = key;

    const container = document.createElement('div');
    container.className = 'setting-slider-container';

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const resolvedValue = currentValue !== undefined ? currentValue : value;

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.className = 'setting-slider';
    slider.min = '0';
    slider.max = '4';
    slider.step = '1';

    const mapping = {
        '0': null,
        '1': 'low',
        '2': 'medium',
        '3': 'high',
        '4': 'xhigh'
    };

    const labelMap = {
        '0': 'OFF',
        '1': 'low',
        '2': 'medium',
        '3': 'high',
        '4': 'extra high'
    };

    // Find current index from value
    let currentIndex = 0;
    if (resolvedValue === 'low') currentIndex = 1;
    else if (resolvedValue === 'medium') currentIndex = 2;
    else if (resolvedValue === 'high') currentIndex = 3;
    else if (resolvedValue === 'xhigh') currentIndex = 4;
    else currentIndex = 0;

    slider.value = currentIndex;

    const valueDisplay = document.createElement('span');
    valueDisplay.className = 'setting-slider-value';
    valueDisplay.textContent = labelMap[currentIndex];

    slider.oninput = () => {
        const idx = slider.value;
        valueDisplay.textContent = labelMap[idx];
        handleSettingChange(key, mapping[idx]);
    };

    container.appendChild(slider);
    container.appendChild(valueDisplay);

    wrapper.appendChild(container);

    const desc = document.createElement('p');
    desc.className = 'setting-description';
    desc.textContent = 'Set the reasoning effort for the model';
    wrapper.appendChild(desc);

    return wrapper;
}



// Create percentage slider (0.0 to 1.0)
function createPercentageSlider(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-slider-container';

    // Get current value from live settingsData (for re-render safety)
    const currentValue = getCurrentValue(key);
    const currentVal = parseFloat(currentValue) || parseFloat(value) || 0;
    const minVal = 0;
    const maxVal = 1;
    const stepVal = 0.01;

    const getPercentage = (val) => (val * 100);
    const percentage = getPercentage(currentVal);

    const sliderRow = document.createElement('div');
    sliderRow.className = 'slider-row';
    sliderRow.innerHTML = `
    <div class="slider-header">
    <span class="slider-label">Percentage</span>
    <span class="slider-value" id="${key}-val-display">${(currentVal * 100).toFixed(0)}%</span>
    </div>
    <div class="slider-track-wrapper">
    <div class="slider-track">
    <input type="range" class="slider-input" id="${key}-input"
    min="0" max="1" step="0.01" value="${currentVal}">
    <div class="slider-fill" id="${key}-fill" style="width: ${percentage}%"></div>
    <div class="slider-handle" id="${key}-handle" style="left: ${percentage}%"></div>
    </div>
    <div class="slider-labels">
    <span>0%</span>
    <span>100%</span>
    </div>
    </div>
    `;

    const input = sliderRow.querySelector('.slider-input');
    const fill = sliderRow.querySelector('.slider-fill');
    const handle = sliderRow.querySelector('.slider-handle');
    const display = sliderRow.querySelector('.slider-value');

    input.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        const p = getPercentage(val);
        display.textContent = `${(val * 100).toFixed(0)}%`;
        fill.style.width = `${p}%`;
        handle.style.left = `${p}%`;
        handleSettingChange(key, val);
    });

    wrapper.appendChild(sliderRow);
    return wrapper;
}
