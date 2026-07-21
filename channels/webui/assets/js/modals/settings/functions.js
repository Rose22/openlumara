function formatLabel(key) {
    if (typeof key !== 'string') return key;
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function detectType(value, key = '') {
    // special keys that should be displayed in a special way
    if (key === 'model.name') return 'model_select';
    if (key.endsWith('reasoning_effort')) return 'reasoning_effort_slider';

    // standard types
    if (value === null || value === undefined) return 'text';
    else if (typeof value === 'boolean') return 'boolean';
    else if (typeof value === 'number' && !key.toLowerCase().endsWith('id')) return 'number';
    else if (Array.isArray(value)) return 'array';
    else if (typeof value === 'string') {
        if (value.match(/^https?:\/\//)) return 'url';
        else if (value.includes('\n')) return 'textarea';
    } else {
        return 'text';
    }
}

function isToggleList(data) {
    if (typeof data !== 'object' || data === null) return false;
    return Array.isArray(data.enabled) && Array.isArray(data.disabled);
}

function buildSettingsStructure(originalData, moduleInfo = {}) {
    const categories = {};
    let order = 0;

    categories.appearance = {
        title: 'Appearance',
        description: 'Theme and interface customization',
        order: order++,
        isThemeCategory: true
    };
    categories.audio = {
        title: 'Audio',
        description: 'Audio settings',
        order: order++,
        isThemeCategory: true
    };

    for (const [topKey, topValue] of Object.entries(originalData)) {
        if (topKey.toLowerCase() === 'theme' || topKey.toLowerCase() === 'theme_mode') {
            continue;
        }

        const category = {
            title: formatLabel(topKey),
            description: `Configure ${formatLabel(topKey).toLowerCase()}`,
            order: order++
        };

        if (topKey === 'modules' || topKey === 'user_modules' || 
            topKey === 'channels' || topKey === 'user_channels') {
            category.isModuleCategory = true;
            category.enabled = topValue.enabled || [];
            category.disabled = topValue.disabled || [];
            
            const descriptions = {};
            const unsafeModules = {};
            for (const [itemName, info] of Object.entries(moduleInfo)) {
                if (info.description) descriptions[itemName] = info.description;
                if (info.unsafe) unsafeModules[itemName] = true;
            }
            category.descriptions = descriptions;
            category.unsafeModules = unsafeModules;

            category.settings = {};
            if (topValue.settings && typeof topValue.settings === 'object') {
                for (const [itemName, itemSettings] of Object.entries(topValue.settings)) {
                    if (!itemSettings) continue;
                    const itemInfo = moduleInfo[itemName] || {};
                    const itemSchema = itemInfo.settings_schema || {};
                    category.settings[itemName] = {
                        title: formatLabel(itemName),
                        description: itemInfo.description || '',
                        unsafe: itemInfo.unsafe || false,
                        value: buildFieldSettings(itemSettings, itemSchema, itemName)
                    };
                }
            }
        } else {
            category.settings = (topValue && typeof topValue === 'object') ? 
                buildFieldSettings(topValue, {}, topKey) : {};
        }

        categories[topKey] = category;
    }

    return categories;
}

function buildFieldSettings(obj, schema, prefix = '') {
    if (!obj || typeof obj !== 'object') return {};
    
    const settings = {};

    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        const fieldSchema = schema[key] || {};

        // Check if schema defines this field with metadata
        const hasSchemaDefinition = fieldSchema && (fieldSchema.type !== undefined || fieldSchema.default !== undefined || fieldSchema.description !== undefined);

        if (hasSchemaDefinition) {
            // Schema defines the field - use schema for metadata, value for current value
            const schemaValue = fieldSchema.default !== undefined ? fieldSchema.default : value;
            settings[key] = {
                title: formatLabel(key),
                type: fieldSchema.type === 'long_text' ? 'textarea' : (fieldSchema.type || detectType(schemaValue, fullKey)),
                description: fieldSchema.description || null,
                unsafe: fieldSchema.unsafe || false,
                value: value,
                options: fieldSchema.options || null,
                min: fieldSchema.min,
                max: fieldSchema.max,
                step: fieldSchema.step
            };
        } else if (typeof value === 'object' && value !== null && !Array.isArray(value) && !isToggleList(value)) {
            // Nested object without schema definition - recurse
            settings[key] = {
                type: 'object',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                settings: buildFieldSettings(value, fieldSchema, fullKey)
            };
        } else if (isToggleList(value)) {
            settings[key] = {
                type: 'toggle_list',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                value: value
            };
        } else if (Array.isArray(value)) {
            settings[key] = {
                type: 'array',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                value: value
            };
        } else if (typeof value === 'object') {
            settings[key] = {
                type: 'object',
                title: formatLabel(key),
                description: fieldSchema.description || null,
                settings: buildFieldSettings(value, fieldSchema, fullKey)
            };
        } else {
            // Primitive value without schema definition
            settings[key] = {
                title: formatLabel(key),
                type: detectType(value, fullKey),
                description: fieldSchema.description || null,
                unsafe: fieldSchema.unsafe || false,
                value: value,
                options: fieldSchema.options || null,
                min: fieldSchema.min,
                max: fieldSchema.max,
                step: fieldSchema.step
            };
        }
    }

    return settings;
}

function flattenForBackend(categories) {
    const result = {};

    for (const [catKey, category] of Object.entries(categories)) {
        if (!category.settings && !category.enabled && !category.disabled) continue;
        
        result[catKey] = {};
        
        // Handle modules/channels
        if (category.isModuleCategory) {
            if (category.enabled !== undefined) result[catKey].enabled = category.enabled;
            if (category.disabled !== undefined) result[catKey].disabled = category.disabled;
            
            if (category.settings) {
                result[catKey].settings = {};
                for (const [name, module] of Object.entries(category.settings)) {
                    if (module.value) {
                        result[catKey].settings[name] = flattenModuleSettings(module.value);
                    }
                }
            }
        } else {
            // Regular category - flatten all settings
            result[catKey] = flattenCategorySettings(category.settings);
        }
    }

    return result;
}

function flattenModuleSettings(settings) {
    const result = {};
    for (const [key, setting] of Object.entries(settings)) {
        if (setting.type === 'object' && setting.settings) {
            result[key] = flattenModuleSettings(setting.settings);
        } else {
            result[key] = setting.value;
        }
    }
    return result;
}

function flattenCategorySettings(settings) {
    const result = {};
    for (const [key, setting] of Object.entries(settings)) {
        if (setting.type === 'object' && setting.settings) {
            result[key] = flattenCategorySettings(setting.settings);
        } else {
            result[key] = setting.value;
        }
    }
    return result;
}

