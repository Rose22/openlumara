// =============================================================================
// Settings Management
// =============================================================================

let settingsData = {};
let settingsOriginal = {};
let settingsHasChanges = false;
let cachedModels = null;
let modelsLoadError = null;
let moduleInfoCache = {};

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

    // Process each top-level key (category)
    for (const [topKey, topValue] of Object.entries(originalData)) {
        // Skip theme keys
        if (topKey.toLowerCase() === 'theme' || topKey.toLowerCase() === 'theme_mode') {
            continue;
        }

        const category = topKey;
        categories[category] = {
            title: formatLabel(category),
            description: CATEGORY_DESCRIPTIONS[category] ||
            `Configure ${formatLabel(category).toLowerCase()}`,
            groups: new Map(),
            order: order++
        };

        // Helper to add item to the correct group
        const addToGroup = (groupKey, groupTitle, item, isDirect = false) => {
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
        if (topKey === 'modules' || topKey === 'user_modules') {
            // Get list of enabled items to filter settings
            const enabledItems = new Set(topValue.enabled || []);
            const allItems = getAllToggleItems(topValue);

            const itemDescriptions = {};
            const unsafeModules = {};
            for (const itemName in moduleInfo) {
                if (moduleInfo[itemName].description) {
                    itemDescriptions[itemName] = moduleInfo[itemName].description;
                }
                if (moduleInfo[itemName].unsafe) {
                    unsafeModules[itemName] = true;
                }
            }

            // Add the toggle list directly (ungrouped) at the top
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

            // Only show settings for enabled items
            if (topValue.settings && typeof topValue.settings === 'object') {
                for (const [itemName, itemSettings] of Object.entries(topValue.settings)) {
                    // Skip settings for disabled modules/channels
                    if (!enabledItems.has(itemName)) {
                        continue;
                    }

                    const groupKey = `${topKey}.settings.${itemName}`;
                    const groupTitle = formatLabel(itemName);

                    if (typeof itemSettings === 'object' && itemSettings !== null &&
                        !Array.isArray(itemSettings) && !isToggleList(itemSettings)) {
                        // Flatten nested settings
                        flattenSettingsObject(itemSettings, groupKey, (item) => {
                            addToGroup(groupKey, groupTitle, item);
                        });
                        } else {
                            // Simple value or toggle list
                            addToGroup(groupKey, groupTitle, {
                                key: groupKey,
                                value: itemSettings,
                                type: isToggleList(itemSettings) ? 'toggle_list' : detectType(itemSettings, groupKey),
                                       description: FIELD_DESCRIPTIONS[groupKey] || null
                            });
                        }
                }
            }

            // Add any other top-level items that aren't settings (direct, ungrouped)
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

            // If toggle list has a settings sub-object, show settings for enabled items only
            if (topValue.settings && typeof topValue.settings === 'object') {
                const enabledItems = new Set(topValue.enabled || []);
                for (const [itemName, itemSettings] of Object.entries(topValue.settings)) {
                    if (!enabledItems.has(itemName)) {
                        continue;
                    }
                    const groupKey = `${topKey}.settings.${itemName}`;
                    const groupTitle = formatLabel(itemName);

                    if (typeof itemSettings === 'object' && itemSettings !== null &&
                        !Array.isArray(itemSettings) && !isToggleList(itemSettings)) {
                        flattenSettingsObject(itemSettings, groupKey, (item) => {
                            addToGroup(groupKey, groupTitle, item);
                        });
                        } else {
                            addToGroup(groupKey, groupTitle, {
                                key: groupKey,
                                value: itemSettings,
                                type: isToggleList(itemSettings) ? 'toggle_list' : detectType(itemSettings, groupKey),
                                       description: FIELD_DESCRIPTIONS[groupKey] || null
                            });
                        }
                }
            }
            continue;
        }

        // Regular object - separate simple values from complex values
        if (typeof topValue === 'object' && topValue !== null && !Array.isArray(topValue)) {
            // Categorize children
            const simpleItems = [];
            const complexItems = [];

            for (const [secondKey, secondValue] of Object.entries(topValue)) {
                if (isToggleList(secondValue)) {
                    complexItems.push([secondKey, secondValue]);
                } else if (Array.isArray(secondValue)) {
                    complexItems.push([secondKey, secondValue]);
                } else if (typeof secondValue === 'object' && secondValue !== null) {
                    complexItems.push([secondKey, secondValue]);
                } else {
                    // Simple value (string, number, boolean, null)
                    simpleItems.push([secondKey, secondValue]);
                }
            }

            // Add simple values directly (no grouping)
            for (const [key, value] of simpleItems) {
                addToGroup('_direct_', null, {
                    key: `${category}.${key}`,
                    value: value,
                    type: detectType(value, `${category}.${key}`)
                }, true);
            }

            // Group complex values
            for (const [secondKey, secondValue] of complexItems) {
                const groupKey = `${topKey}.${secondKey}`;
                const groupTitle = formatLabel(secondKey);

                if (typeof secondValue === 'object' && secondValue !== null &&
                    !Array.isArray(secondValue) && !isToggleList(secondValue)) {
                    // It's a nested object, flatten its contents
                    flattenSettingsObject(secondValue, groupKey, (item) => {
                        addToGroup(groupKey, groupTitle, item);
                    });
                    } else {
                        // It's a toggle list or array
                        addToGroup(groupKey, groupTitle, {
                            key: groupKey,
                            value: secondValue,
                            type: isToggleList(secondValue) ? 'toggle_list' : detectType(secondValue, groupKey),
                                   description: FIELD_DESCRIPTIONS[groupKey] || null
                        });
                    }
            }
        } else {
            // Simple value at top level (no groups)
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
function flattenSettingsObject(obj, prefix, callback) {
    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;

        if (typeof value === 'object' && value !== null &&
            !Array.isArray(value) && !isToggleList(value)) {
            // Nested object - recurse
            flattenSettingsObject(value, fullKey, callback);
            } else {
                callback({
                    key: fullKey,
                    value: value,
                    type: isToggleList(value) ? 'toggle_list' : detectType(value, fullKey),
                         description: FIELD_DESCRIPTIONS[fullKey] || null
                });
            }
    }
}

// Detect field type from value
function detectType(value, key = '') {
    if (value === null || value === undefined) return 'text';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
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
    return key
    .split('.')
    .pop()
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, str => str.toUpperCase())
    .trim();
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
    const categories = organizeSettingsIntoCategories(settingsData, moduleInfoCache);
    renderSettingsForm(categories);
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
function renderSettingsNav(categories) {
    const nav = document.getElementById('settings-nav');
    nav.innerHTML = '';

    const sortedCats = Object.entries(categories)
    .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));

    sortedCats.forEach(([cat, data], index) => {
        const btn = document.createElement('button');
        btn.className = 'settings-nav-item' + (index === 0 ? ' active' : '');
        btn.dataset.category = cat;
        btn.innerHTML = `
        ${SETTINGS_ICONS[cat] || SETTINGS_ICONS.other}
        <span>${data.title}</span>
        `;
        btn.onclick = () => switchSettingsCategory(cat);
        nav.appendChild(btn);
    });
}

// Switch active settings category
function switchSettingsCategory(category) {
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.category === category);
    });

    document.querySelectorAll('.settings-section').forEach(section => {
        section.classList.toggle('active', section.dataset.category === category);
    });
}

function renderSettingsForm(categories) {
    const form = document.getElementById('settings-form');
    form.innerHTML = '';

    const sortedCats = Object.entries(categories)
    .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));

    for (const [cat, data] of sortedCats) {
        const section = document.createElement('div');
        section.className = 'settings-section';
        section.dataset.category = cat;

        section.innerHTML = `
        <h3 class="settings-section-title">${data.title}</h3>
        <p class="settings-section-desc">${data.description}</p>
        `;

        const itemsContainer = document.createElement('div');
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

        // Render groups - put direct items first
        if (data.groups) {
            // First render direct (ungrouped) items into the main vertical stack
            const directGroup = data.groups.get('_direct_');
            if (directGroup && directGroup.isDirect) {
                directGroup.items.forEach(item => {
                    const itemEl = createSettingItem(item);

                    // Apply full-width class to module/user module toggle lists
                    if (item.isModuleList) {
                        itemEl.classList.add('full-width-item');
                    }

                    itemsContainer.appendChild(itemEl);
                });
            }

            // Create the grid container for grouped items
            const groupsGrid = document.createElement('div');
            groupsGrid.className = 'settings-groups-grid';

            // Then render grouped items into the grid
            data.groups.forEach((groupData, groupKey) => {
                if (groupKey === '_direct_') return;

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
                groupsGrid.appendChild(groupContainer); // Append to the grid
            });

            itemsContainer.appendChild(groupsGrid); // Append grid to the main container
        }

        section.appendChild(itemsContainer);
        form.appendChild(section);
    }

    const firstSection = form.querySelector('.settings-section');
    if (firstSection) {
        firstSection.classList.add('active');
    }
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

    const label = document.createElement('label');
    label.className = 'setting-label';
    label.textContent = formatLabel(item.key);
    wrapper.appendChild(label);

    // Create appropriate input based on type
    let inputEl;

    switch (item.type) {
        case 'model':
            inputEl = createModelInput(item.key, item.value);
            break;
        case 'toggle_list':
            inputEl = createToggleListInput(item.key, item.value, !!item.isModuleList);
            break;
        case 'boolean':
            inputEl = createToggleInput(item.key, item.value);
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
        default:
            inputEl = createTextInput(item.key, item.value, item.type);
    }

    wrapper.appendChild(inputEl);

    if (item.description) {
        const desc = document.createElement('p');
        desc.className = 'setting-description';
        desc.textContent = item.description;
        wrapper.appendChild(desc);
    }

    return wrapper;
}

// Create model dropdown input with refresh button
function createModelInput(key, value) {
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
            if (model === value) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        // If current value not in list, add it as custom
        if (value && !cachedModels.find(m => m === value)) {
            const customOption = document.createElement('option');
            customOption.value = value;
            customOption.textContent = `${value} (custom)`;
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
                const textInput = createTextInput(key, value, 'text');
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
        input.value = value ?? '';
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
    const wrapper = document.createElement('div');
    wrapper.className = 'toggle-list';
    wrapper.dataset.key = key;

    const allItems = getAllToggleItems(value);
    const enabledSet = new Set(value.enabled || []);
    const descriptions = value.descriptions || {};
    const unsafeModules = value.unsafeModules || {};

    // Sort: enabled items first, then alphabetically within each group
    const sortedItems = allItems.sort((a, b) => {
        const aEnabled = enabledSet.has(a);
        const bEnabled = enabledSet.has(b);
        if (aEnabled && !bEnabled) return -1;
        if (!aEnabled && bEnabled) return 1;
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

            checkbox.onchange = () => {
                const newState = checkbox.checked;
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
}

// Create text input (with sensitive field detection)
function createTextInput(key, value, type = 'text') {
    const keyLower = key.toLowerCase();
    const isSensitive = keyLower.includes('token') || keyLower.includes('key') ||
    keyLower.includes('secret') || keyLower.includes('password') ||
    keyLower.includes('credential');

    // For sensitive fields, use a reveal/hide toggle
    if (isSensitive) {
        const wrapper = document.createElement('div');
        wrapper.className = 'sensitive-input-wrapper';
        wrapper.dataset.key = key;

        const input = document.createElement('input');
        input.type = 'password';
        input.className = 'setting-input sensitive-input';
        input.value = value ?? '';
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
    input.value = value ?? '';
    input.oninput = () => handleSettingChange(key, input.value);
    return input;
}

// Create password input with toggle
function createPasswordInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: relative; display: flex; align-items: center;';

    const input = document.createElement('input');
    input.type = 'password';
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = value ?? '';
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
    const textarea = document.createElement('textarea');
    textarea.className = 'setting-input setting-textarea';
    textarea.dataset.key = key;
    textarea.value = value ?? '';
    textarea.oninput = () => handleSettingChange(key, textarea.value);
    return textarea;
}

// Create number input
function createNumberInput(key, value) {
    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = value ?? 0;
    input.step = Number.isInteger(value) ? '1' : '0.01';
    input.oninput = () => handleSettingChange(key, parseFloat(input.value) || 0);
    return input;
}

// Create toggle switch (single boolean)
function createToggleInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-toggle-wrapper';

    const label = document.createElement('label');
    label.className = 'toggle-switch';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = value;

    const slider = document.createElement('span');
    slider.className = 'toggle-slider';

    const labelSpan = document.createElement('span');
    labelSpan.className = 'setting-toggle-label';
    labelSpan.textContent = value ? 'Enabled' : 'Disabled';

    // Handle change
    checkbox.onchange = () => {
        const newValue = checkbox.checked;
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

    const items = Array.isArray(value) ? [...value] : [];

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
    const entries = value && typeof value === 'object' ? Object.entries(value) : [];

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

    const categories = organizeSettingsIntoCategories(settingsData);
    renderSettingsForm(categories);
    updateUnsavedIndicator();
}

// Save settings to backend
async function saveSettings() {
    const activeCategory = document.querySelector('.settings-nav-item.active')?.dataset.category;

    // Appearance changes are local/immediate and don't trigger server saves here
    if (activeCategory === 'appearance') {
        toggleModal('settings');
        return;
    }

    if (!settingsHasChanges) return;

    const saveBtn = document.getElementById('settings-save-btn');
    const btnText = saveBtn.querySelector('.btn-text');
    const btnLoading = saveBtn.querySelector('.btn-loading');
    const hasNonThemeChanges = detectNonThemeChanges();

    saveBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';

    try {
        const response = await fetch('/settings/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsData),
                                     signal: AbortSignal.timeout(15000)
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.message || `Server returned ${response.status}`);
        }

        // Success: Update the original reference so "unsaved" indicator clears
        settingsOriginal = JSON.parse(JSON.stringify(settingsData));
        settingsHasChanges = false;

        if (hasNonThemeChanges) {
            showSettingsSuccessWithRestart();
            await restartServer();
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

        const response = await fetch('/server/restart', {
            method: 'POST',
            signal: AbortSignal.timeout(5000)
        }).catch(() => {
            // Server might disconnect during restart, which is expected
            return { ok: true };
        });

        // Show restart notification
        showRestartNotification();

    } catch (err) {
        // Expected - server is restarting
        showRestartNotification();
    }
}

// Show settings saved with restart message
function showSettingsSuccessWithRestart() {
    const form = document.getElementById('settings-form');
    const existing = form.querySelector('.setting-success-msg');
    if (existing) existing.remove();

    const success = document.createElement('div');
    success.className = 'setting-success-msg restart-pending';
    success.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
    Settings saved! Server restarting...
    `;

    form.insertBefore(success, form.firstChild);
}

// Show restart notification
function showRestartNotification() {
    const form = document.getElementById('settings-form');
    const existing = form.querySelector('.restart-notification');
    if (existing) existing.remove();

    const notification = document.createElement('div');
    notification.className = 'restart-notification';
    notification.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"></path>
    <path d="M21 3v5h-5"></path>
    </svg>
    <div class="restart-content">
    <div class="restart-title">Server Restarting</div>
    <div class="restart-desc">The server is applying your changes. The page will refresh when ready.</div>
    </div>
    `;

    form.insertBefore(notification, form.firstChild);

    // Start polling for server availability
    pollForServerRestart();
}

// Poll for server to come back up
function pollForServerRestart() {
    let attempts = 0;
    const maxAttempts = 60; // 30 seconds max

    const poll = setInterval(async () => {
        attempts++;

        if (attempts >= maxAttempts) {
            clearInterval(poll);
            showRestartFailed();
            return;
        }

        try {
            const response = await fetch('/settings/load', {
                method: 'GET',
                signal: AbortSignal.timeout(1000)
            });

            if (response.ok) {
                clearInterval(poll);
                showRestartComplete();
            }
        } catch (err) {
            // Server not ready yet, keep polling
        }
    }, 500);
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

// Show restart complete and refresh page
function showRestartComplete() {
    const notification = document.querySelector('.restart-notification');
    if (notification) {
        notification.classList.add('restart-complete');
        notification.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        <div class="restart-content">
        <div class="restart-title">Server Restarted</div>
        <div class="restart-desc">Refreshing page...</div>
        </div>
        `;
    }

    // Refresh the page after a short delay
    setTimeout(() => {
        window.location.reload();
    }, 500);
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

// Escape HTML
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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
        root.style.setProperty('--font-family', "sans-serif");
        root.style.removeProperty('--code-font'); // This allows it to fall back to :root
    } else {
        const fontFamily = `'${fontId}', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;

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
    const triggerFontFamily = currentSelection === 'default' ? 'inherit' : `'${currentSelection}', sans-serif`;

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
    const families = getThemeFamilies();

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
        if (tokenBar) {
            tokenBar.style.display = isVisible ? 'flex' : 'none';
        }

        // Add this line to toggle the class on the body
        document.body.classList.toggle('token-bar-hidden', !isVisible);
    });
    typographyControls.appendChild(tokenBarToggleRow);


    typographySection.appendChild(typographyControls);
    wrapper.appendChild(typographySection);

    // ==========================================================================
    // TYPEWRITER / AUDIO SETTINGS SECTION
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
    <h4>Typewriter Effect</h4>
    <p>Configure text streaming animation and sounds</p>
    </div>
    `;
    audioSection.appendChild(audioHeader);

    // Enable/Disable Toggle
    const savedTypewriterEnabled = localStorage.getItem('typewriterEnabled') !== 'false';

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

    // ==========================================================================
    // SWEEP FADE TOGGLE
    // ==========================================================================

    const fadeEnabled = localStorage.getItem('typewriterFadeEnabled') === 'true';

    const fadeToggleRow = document.createElement('div');
    fadeToggleRow.className = 'toggle-row';
    fadeToggleRow.innerHTML = `
    <div class="toggle-info">
    <span class="toggle-label">Fade</span>
    <span class="toggle-description">Letters fade in smoothly as they appear</span>
    </div>
    <label class="toggle-switch">
    <input type="checkbox" id="typewriter-fade-checkbox" ${fadeEnabled ? 'checked' : ''}>
    <span class="toggle-slider"></span>
    </label>
    `;

    const fadeCheckbox = fadeToggleRow.querySelector('#typewriter-fade-checkbox');
    fadeCheckbox.addEventListener('change', function() {
        localStorage.setItem('typewriterFadeEnabled', this.checked ? 'true' : 'false');
    });

    twControls.appendChild(fadeToggleRow);

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

    // Volume Control
    const currentVolume = Math.round((parseFloat(localStorage.getItem('typewriterVolume') || '1.0')) * 100);

    // Sync volume with manager on load
    if (savedTypewriterEnabled) {
        TypewriterAudioManager.setVolume(currentVolume / 100);
    }

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

    twControls.appendChild(volumeRow);

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

    const createSoundInput = (id, labelText, iconPath, savedName) => {
        const hasAudio = isAudioLoaded(id);

        const container = document.createElement('div');
        container.className = 'sound-input-card';
        container.dataset.soundId = id;

        container.innerHTML = `
        <div class="sound-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        ${iconPath}
        </svg>
        </div>
        <div class="sound-info">
        <span class="sound-label">${labelText}</span>
        <span class="sound-filename ${hasAudio ? 'loaded' : ''}" id="${id}-filename">${savedName || 'No file selected'}</span>
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
        <input type="file" accept="audio/*" id="${id}-file-input" style="display: none;">
        `;

        const previewBtn = container.querySelector(`#${id}-preview-btn`);
        const uploadBtn = container.querySelector(`#${id}-upload-btn`);
        const clearBtn = container.querySelector(`#${id}-clear-btn`);
        const fileInput = container.querySelector(`#${id}-file-input`);
        const filenameDisplay = container.querySelector(`#${id}-filename`);

        // Pre-load audio from localStorage if available
        // FIX: Defer loading to prevent UI lag
        if (hasAudio && !TypewriterAudioManager.buffers?.[id]) {
            const savedData = localStorage.getItem(`${id}SoundData`);
            if (savedData) {
                // Defer to next tick to avoid blocking main thread
                setTimeout(() => {
                    try {
                        TypewriterAudioManager.loadFromDataURL(id, savedData).catch(err => {
                            console.warn('Failed to preload audio:', err);
                        });
                    } catch (err) {
                        console.warn('Failed to preload audio:', err);
                    }
                }, 0);
            }
        }

        uploadBtn.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            try {
                await TypewriterAudioManager.saveFile(id, file);
                localStorage.setItem(`${id}SoundName`, file.name);
                filenameDisplay.textContent = file.name;
                filenameDisplay.classList.add('loaded');
                filenameDisplay.classList.remove('error');
                previewBtn.disabled = false;
                clearBtn.disabled = false;
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
            // Try to play the sound
            TypewriterAudioManager.play(id);
            previewBtn.classList.add('playing');
            setTimeout(() => previewBtn.classList.remove('playing'), 500);
        });

        clearBtn.addEventListener('click', () => {
            TypewriterAudioManager.deleteFile(id);
            localStorage.removeItem(`${id}SoundName`);
            filenameDisplay.textContent = 'No file selected';
            filenameDisplay.classList.remove('loaded');
            previewBtn.disabled = true;
            clearBtn.disabled = true;
            fileInput.value = '';
        });

        return container;
    };

    const typewriterIcon = '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>';
    const completionIcon = '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>';

    const twSoundInput = createSoundInput(
        'typewriter',
        'Typewriter Sound',
        typewriterIcon,
        localStorage.getItem("typewriterSoundName")
    );
    soundContainer.appendChild(twSoundInput);

    const compSoundInput = createSoundInput(
        'completion',
        'Completion Sound',
        completionIcon,
        localStorage.getItem("completionSoundName")
    );
    soundContainer.appendChild(compSoundInput);

    twControls.appendChild(soundContainer);
    audioSection.appendChild(twToggleRow);
    audioSection.appendChild(twControls);
    wrapper.appendChild(audioSection);

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

    families.forEach((variants, family) => {
        const previewThemeId = variants.dark || variants.light;
        const previewTheme = themes[previewThemeId];
        if (!previewTheme) return;

        const btn = document.createElement('button');
        btn.className = 'theme-btn' + (family === savedFamily ? ' active' : '');
        btn.dataset.family = family;
        btn.type = 'button';

        const bgColor = previewTheme.vars['--bg-primary'];
        const accentColor = previewTheme.vars['--accent'];
        const themeName = previewTheme.name;

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
