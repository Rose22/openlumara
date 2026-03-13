// =============================================================================
// Settings Management
// =============================================================================

let settingsData = {};
let settingsOriginal = {};
let settingsHasChanges = false;

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

// Organize settings into categories, grouping by second-level key (e.g. modules.X)
function organizeSettingsIntoCategories(originalData) {
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
        if (topKey === 'modules' || topKey === 'channels') {
            // Get list of enabled items to filter settings
            const enabledItems = new Set(topValue.enabled || []);
            const allItems = getAllToggleItems(topValue);

            // Add the toggle list directly (ungrouped) at the top
            addToGroup('_direct_', null, {
                key: topKey,
                value: {
                    enabled: topValue.enabled || [],
                    disabled: topValue.disabled || []
                },
                type: 'toggle_list'
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
                                type: isToggleList(itemSettings) ? 'toggle_list' : detectType(itemSettings),
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
                    type: detectType(secondValue)
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
                                type: isToggleList(itemSettings) ? 'toggle_list' : detectType(itemSettings),
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
                    type: detectType(value)
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
                            type: isToggleList(secondValue) ? 'toggle_list' : detectType(secondValue),
                                   description: FIELD_DESCRIPTIONS[groupKey] || null
                        });
                    }
            }
        } else {
            // Simple value at top level (no groups)
            addToGroup(topKey, formatLabel(topKey), {
                key: topKey,
                value: topValue,
                type: detectType(topValue)
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
                    type: isToggleList(value) ? 'toggle_list' : detectType(value),
                         description: FIELD_DESCRIPTIONS[fullKey] || null
                });
            }
    }
}

// Detect field type from value
function detectType(value) {
    if (value === null || value === undefined) return 'text';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    if (typeof value === 'string') {
        if (value.includes('\n')) return 'textarea';
        if (value.match(/^https?:\/\//)) return 'url';
    }
    return 'text';
}

// Field descriptions (optional, can be empty)
const FIELD_DESCRIPTIONS = {
    'api.key': 'API authentication key'
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

    try {
        const response = await fetch('/settings/load', {
            signal: AbortSignal.timeout(10000)
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        settingsData = await response.json();
        settingsOriginal = JSON.parse(JSON.stringify(settingsData));

        const categories = organizeSettingsIntoCategories(settingsData);

        renderSettingsForm(categories);
        renderSettingsNav(categories);

        loading.style.display = 'none';
        form.style.display = 'block';
        settingsHasChanges = false;
        updateUnsavedIndicator();

    } catch (err) {
        console.error('Failed to load settings:', err);
        loading.style.display = 'none';
        error.style.display = 'flex';
        errorMsg.textContent = err.message || 'Failed to load settings';
    }
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

// Render settings form
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
            // First render direct (ungrouped) items
            const directGroup = data.groups.get('_direct_');
            if (directGroup && directGroup.isDirect) {
                directGroup.items.forEach(item => {
                    const itemEl = createSettingItem(item);
                    itemsContainer.appendChild(itemEl);
                });
            }

            // Then render grouped items
            data.groups.forEach((groupData, groupKey) => {
                // Skip direct items - already rendered
                if (groupKey === '_direct_') return;

                const groupContainer = document.createElement('div');
                groupContainer.className = 'settings-group';
                groupContainer.dataset.group = groupKey;

                // Create header (clickable to collapse)
                const header = document.createElement('div');
                header.className = 'settings-group-header';
                header.onclick = () => toggleSettingsGroup(header);
                header.innerHTML = `
                <span class="settings-group-title">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
                ${groupData.title}
                </span>
                `;

                // Create content container
                const content = document.createElement('div');
                content.className = 'settings-group-content';
                content.style.display = 'none';

                // Render items within the group
                groupData.items.forEach(item => {
                    const itemEl = createSettingItem(item);
                    content.appendChild(itemEl);
                });

                groupContainer.appendChild(header);
                groupContainer.appendChild(content);
                itemsContainer.appendChild(groupContainer);
            });
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
        case 'toggle_list':
            inputEl = createToggleListInput(item.key, item.value);
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

// Create toggle list (for enabled/disabled arrays)
function createToggleListInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'toggle-list';
    wrapper.dataset.key = key;

    const allItems = getAllToggleItems(value);
    const enabledSet = new Set(value.enabled || []);

    // Sort: enabled items first, then alphabetically within each group
    const sortedItems = allItems.sort((a, b) => {
        const aEnabled = enabledSet.has(a);
        const bEnabled = enabledSet.has(b);
        if (aEnabled && !bEnabled) return -1;
        if (!aEnabled && bEnabled) return 1;
        return a.localeCompare(b);
    });

    // Status bar
    const status = document.createElement('div');
    status.className = 'toggle-list-status';
    status.innerHTML = `<span class="toggle-count">${enabledSet.size} of ${sortedItems.length} enabled</span>`;
    wrapper.appendChild(status);

    // Grid of toggles
    const grid = document.createElement('div');
    grid.className = 'toggle-list-grid';

    sortedItems.forEach(item => {
        const isEnabled = enabledSet.has(item);

        const itemWrapper = document.createElement('div');
        itemWrapper.className = 'toggle-list-item' + (isEnabled ? ' enabled' : '');

        const name = document.createElement('span');
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

        checkbox.onchange = () => {
            const newState = checkbox.checked;
            itemWrapper.classList.toggle('enabled', newState);

            if (newState) {
                enabledSet.add(item);
            } else {
                enabledSet.delete(item);
            }

            status.querySelector('.toggle-count').textContent =
            `${enabledSet.size} of ${sortedItems.length} enabled`;

            updateToggleListData(key, Array.from(enabledSet), sortedItems);
        };

        itemWrapper.appendChild(name);
        itemWrapper.appendChild(toggle);
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
    // Check if we're on the Appearance tab - theme changes are applied immediately
    const activeCategory = document.querySelector('.settings-nav-item.active')?.dataset.category;
    if (activeCategory === 'appearance') {
        // Just close the modal - theme changes are applied immediately
        toggleModal('settings');
        return;
    }

    if (!settingsHasChanges) return;

    const saveBtn = document.getElementById('settings-save-btn');
    const btnText = saveBtn.querySelector('.btn-text');
    const btnLoading = saveBtn.querySelector('.btn-loading');

    // Check if there are non-theme changes (require restart)
    const hasNonThemeChanges = detectNonThemeChanges();

    saveBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';

    try {
        const response = await fetch('/settings/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsData),
                                     signal: AbortSignal.timeout(30000)
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.message || `Server returned ${response.status}`);
        }

        settingsOriginal = JSON.parse(JSON.stringify(settingsData));
        settingsHasChanges = false;

        // Show appropriate success message
        if (hasNonThemeChanges) {
            showSettingsSuccessWithRestart();
            await restartServer();
        } else {
            showSettingsSuccess();
        }

    } catch (err) {
        console.error('Failed to save settings:', err);
        showSettingsError(err.message || 'Failed to save settings');
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

// Theme section
function createThemeSection() {
    const wrapper = document.createElement('div');
    wrapper.className = 'settings-theme-section';

    const savedFamily = localStorage.getItem('themeFamily') || 'monochrome';
    const savedMode = localStorage.getItem('themeMode') || 'dark';
    const families = getThemeFamilies();

    const themeLabel = document.createElement('h4');
    themeLabel.textContent = 'Color Theme';
    wrapper.appendChild(themeLabel);

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
        const hasBothModes = variants.dark && variants.light;

        btn.innerHTML = `
        <div class="theme-preview" style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);">
        ${hasBothModes ? '<span class="theme-badge">◐</span>' : ''}
        </div>
        <span class="theme-name">${family.charAt(0).toUpperCase() + family.slice(1)}</span>
        `;

        btn.onclick = () => {
            currentThemeFamily = family;
            applyTheme(family, currentThemeMode);
            updateThemeButtonsInSettings();
        };

        themeGrid.appendChild(btn);
    });

    wrapper.appendChild(themeGrid);

    const modeLabel = document.createElement('h4');
    modeLabel.textContent = 'Appearance Mode';
    modeLabel.style.marginTop = '20px';
    wrapper.appendChild(modeLabel);

    const modeToggle = document.createElement('div');
    modeToggle.className = 'theme-mode-toggle';

    modeToggle.innerHTML = `
    <span class="theme-mode-label">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
    Dark
    </span>
    <label class="theme-switch">
    <input type="checkbox" id="theme-mode-checkbox-settings" ${savedMode === 'light' ? 'checked' : ''}>
    <span class="theme-slider"></span>
    </label>
    <span class="theme-mode-label">
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

    wrapper.appendChild(modeToggle);
    return wrapper;
}

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
