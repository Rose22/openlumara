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

// Detect field type from value
function detectType(value, key = '') {
    if (key.endsWith('reasoning_effort')) return 'reasoning_effort_slider';
    if (value === null || value === undefined) return 'text';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number' && !key.toLowerCase().endsWith('id')) return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    if (typeof value === 'string') {
        if (key && isModelNameField(key)) return 'model';
        if (value.includes('\n')) return 'textarea';
        if (value.match(/^https?:\/\//)) return 'url';
    }
    return 'text';
}

// Format label from key
function formatLabel(key) {
    if (typeof key !== 'string') return key;
    const parts = key.split('.');
    const lastPart = parts[parts.length - 1];
    return lastPart.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Check if settings contain a model field
function checkForModelField(data, prefix = '') {
    for (const [key, value] of Object.entries(data)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        if (isModelNameField(fullKey)) return true;
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            if (checkForModelField(value, fullKey)) return true;
        }
    }
    return false;
}

// Flatten a settings object into dot-notation items
function flattenSettingsObject(obj, prefix, fieldDescriptions = {}, schema = {}, callback) {
    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        const subSchema = (schema && schema[key]) ? schema[key] : {};

        const isDefinition = (typeof value === 'object' && value !== null && !Array.isArray(value) &&
            ('default' in value || 'description' in value || 'type' in value || 'unsafe' in value));

        if (!isDefinition && !isToggleList(value) && typeof value === 'object' && value !== null && !Array.isArray(value)) {
            flattenSettingsObject(value, fullKey, fieldDescriptions, subSchema, callback);
        } else {
            let actualValue = value;
            let actualDescription = null;
            let actualType = null;
            let actualUnsafe = false;

            if (isDefinition) {
                actualValue = 'default' in value ? value.default : value;
                actualDescription = value.description || null;
                actualUnsafe = value.unsafe || false;
                if (value.type) {
                    if (value.type === 'long_text') actualType = 'textarea';
                    else if (value.type === 'select') actualType = 'select';
                    else if (value.type === 'number') actualType = 'number';
                    else if (value.type === 'slider') actualType = 'slider';
                    else actualType = value.type;
                }
            }

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

            if (!actualDescription) {
                actualDescription = fieldDescriptions[fullKey] || subSchema.description || null;
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

// Organize settings into categories, grouping by second-level key (e.g. modules.X)
function organizeSettingsIntoCategories(originalData, moduleInfo = {}, categoryDescriptions = {}, fieldDescriptions = {}) {
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
            description: categoryDescriptions[category] || `Configure ${formatLabel(category).toLowerCase()}`,
            groups: new Map(),
            order: order++
        };

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
        if (topKey === 'modules' || topKey === 'user_modules' || topKey === 'channels' || topKey === 'user_channels') {
            const hasToggleListStructure = isToggleList(topValue);
            const enabledItems = new Set(topValue.enabled || []);
            const allItems = hasToggleListStructure ? getAllToggleItems(topValue) : [];

            const unsafeModules = {};
            for (const itemName in moduleInfo) {
                console.log(moduleInfo[itemName]);
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
                        flattenSettingsObject(itemSettings, groupKey, fieldDescriptions, itemSchema, (item) => {
                            addToGroup(groupKey, groupTitle, item);
                        });
                    } else {
                        let type = detectType(itemSettings, groupKey);
                        if (itemSchema[itemName] && itemSchema[itemName].type) {
                            type = itemSchema[itemName].type;
                        }

                        let description = fieldDescriptions[groupKey] || null;
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
                        flattenSettingsObject(itemSettings, groupKey, fieldDescriptions, itemSchema, (item) => {
                            addToGroup(groupKey, groupTitle, item);
                        });
                    } else {
                        let type = detectType(itemSettings, groupKey);
                        if (itemSchema[itemName] && itemSchema[itemName].type) {
                            type = itemSchema[itemName].type;
                        }

                        let description = fieldDescriptions[groupKey] || null;
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
                    flattenSettingsObject(secondValue, groupKey, fieldDescriptions, {}, (item) => {
                        addToGroup(groupKey, groupTitle, item);
                    });
                } else {
                    addToGroup(groupKey, groupTitle, {
                        key: groupKey,
                        value: secondValue,
                        type: isToggleList(secondValue) ? 'toggle_list' : detectType(secondValue, groupKey),
                        description: fieldDescriptions[groupKey] || null
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
