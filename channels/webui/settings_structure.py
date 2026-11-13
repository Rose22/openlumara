"""
Settings Structure (backend-side)

merges the raw config with module/channel/core schemas into the
render-ready category tree the settings UI consumes, and flattens
edited trees back to plain config dicts.
"""

import re

import core

# special keys that render with a bespoke widget instead of a generic field
SPECIAL_FIELD_TYPES = {
    "model.name": "model_select",
    "api.url": "api_url",
    "api.key": "api_key",
    "model.reasoning_effort": "reasoning_effort_slider",
}

MODULE_CATEGORY_KEYS = ("modules", "user_modules", "channels", "user_channels")


def format_label(key):
    if not isinstance(key, str):
        return key
    spaced = key.replace("_", " ")
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), spaced)


def is_toggle_list(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("enabled"), list)
        and isinstance(data.get("disabled"), list)
    )


def detect_field_type(value, key=""):
    if key in SPECIAL_FIELD_TYPES:
        return SPECIAL_FIELD_TYPES[key]
    if value is None:
        return "text"
    elif isinstance(value, bool):
        return "boolean"
    elif isinstance(value, (int, float)) and not key.lower().endswith("id"):
        return "number"
    elif isinstance(value, list):
        return "array"
    elif isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return "url"
        elif "\n" in value:
            return "textarea"
        else:
            return "text"
    return "text"


def build_field_settings(obj, schema, prefix=""):
    if not obj or not isinstance(obj, dict):
        return {}

    settings = {}

    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        field_schema = schema.get(key) or {}
        if not isinstance(field_schema, dict):
            field_schema = {}

        has_schema_definition = any(
            k in field_schema for k in ("type", "default", "description")
        )

        if has_schema_definition:
            # schema defines the field - use schema for metadata, value for current value
            schema_value = field_schema["default"] if "default" in field_schema else value
            raw_type = field_schema.get("type")
            if raw_type == "long_text":
                field_type = "textarea"
            elif raw_type is not None:
                field_type = raw_type
            else:
                field_type = detect_field_type(schema_value, full_key)

            settings[key] = {
                "title": format_label(key),
                "type": field_type,
                "description": field_schema.get("description") or None,
                "unsafe": field_schema.get("unsafe", False),
                "value": value,
                "options": field_schema.get("options") or None,
                "min": field_schema.get("min"),
                "max": field_schema.get("max"),
                "step": field_schema.get("step"),
                "depends": field_schema.get("depends") or None,
            }
        elif isinstance(value, dict) and not is_toggle_list(value):
            # nested object without schema definition - recurse
            settings[key] = {
                "type": "object",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "depends": field_schema.get("depends") or None,
                "settings": build_field_settings(value, field_schema, full_key),
            }
        elif is_toggle_list(value):
            settings[key] = {
                "type": "toggle_list",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "value": value,
            }
        elif isinstance(value, list):
            settings[key] = {
                "type": "array",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "value": value,
            }
        else:
            # primitive value without schema definition
            settings[key] = {
                "title": format_label(key),
                "type": detect_field_type(value, full_key),
                "description": field_schema.get("description") or None,
                "unsafe": field_schema.get("unsafe", False),
                "depends": field_schema.get("depends") or None,
                "value": value,
                "options": field_schema.get("options") or None,
                "min": field_schema.get("min"),
                "max": field_schema.get("max"),
                "step": field_schema.get("step"),
            }

    return settings


def build_settings_structure(original_data, module_info, core_sections, skills_enabled=False):
    categories = {}
    order = 0

    categories["appearance"] = {
        "title": "Appearance",
        "description": "Theme and interface customization",
        "order": order,
        "isThemeCategory": True,
    }
    order += 1
    categories["audio"] = {
        "title": "Audio",
        "description": "Audio settings",
        "order": order,
        "isThemeCategory": True,
    }
    categories["system_prompt"] = {
        "title": "System Prompt",
        "description": "See the current system prompt",
        "order": 100,
        "isThemeCategory": True,
    }
    categories["system_logs"] = {
        "title": "System Logs",
        "description": "Peek into the great unknown",
        "order": 999,
        "isThemeCategory": True,
    }

    # sidebar order: the stock sections first, then the git-installed ones
    section_order = {
        "modules": 10,
        "channels": 11,
        "user_modules": 12,
        "user_channels": 13,
    }

    # custom panel tab: install skills packs from git repos and manage the ones on disk.
    # only shown when the skills module is loaded, otherwise there is nothing to load them.
    if skills_enabled:
        categories["your_skills"] = {
            "title": "Your Skills",
            "description": "Install skills from git repos and manage the ones on disk",
            "order": 14,
            "isThemeCategory": True,
        }

    # Your Channels / Your Modules are proper sidebar entries even on a fresh
    # install: synthesize empty toggle-list sections when the config holds none
    # yet, so the clone bar is reachable before the first repo is ever installed.
    data = dict(original_data)
    for key in ("user_channels", "user_modules"):
        if not isinstance(data.get(key), dict):
            data[key] = {"enabled": [], "disabled": [], "settings": {}}

    for top_key, top_value in data.items():
        if top_key.lower() in ("theme", "theme_mode"):
            continue

        section_titles = {
            "user_channels": "Your Channels",
            "user_modules": "Your Modules",
        }

        display_title = section_titles.get(top_key, format_label(top_key))
        category = {
            "title": display_title,
            "description": f"Configure {display_title.lower()}",
            "order": section_order.get(top_key, order),
        }
        order += 1

        if top_key in MODULE_CATEGORY_KEYS:
            category["isModuleCategory"] = True
            category["enabled"] = (top_value or {}).get("enabled") or []
            category["disabled"] = (top_value or {}).get("disabled") or []

            descriptions = {}
            unsafe_modules = {}
            
            # module_name -> declared category, so the frontend can group the list
            module_categories = {}
            for item_name, info in module_info.items():
                if info.get("description"):
                    descriptions[item_name] = info["description"]
                if info.get("unsafe"):
                    unsafe_modules[item_name] = True
                if info.get("category"):
                    module_categories[item_name] = info["category"]
            category["descriptions"] = descriptions
            category["unsafeModules"] = unsafe_modules
            category["moduleCategories"] = module_categories

            category["settings"] = {}
            top_settings = (top_value or {}).get("settings")
            if isinstance(top_settings, dict):
                for item_name, item_settings in top_settings.items():
                    if not item_settings:
                        continue
                    item_info = module_info.get(item_name) or {}
                    item_schema = item_info.get("settings_schema") or {}
                    category["settings"][item_name] = {
                        "title": format_label(item_name),
                        "description": item_info.get("description") or "",
                        "unsafe": item_info.get("unsafe", False),
                        "value": build_field_settings(item_settings, item_schema, item_name),
                    }
        else:
            # core config sections (api, model, core, etc.), schema from core_sections
            section_schema = (core_sections.get(top_key) or {}).get("settings_schema") or {}
            if isinstance(top_value, dict) and top_value:
                category["settings"] = build_field_settings(top_value, section_schema, top_key)
            else:
                category["settings"] = {}

        categories[top_key] = category

    return categories


def flatten_field_settings(settings):
    """reduces a (possibly edited) field tree back to plain key -> value config"""
    result = {}
    for key, setting in settings.items():
        if not isinstance(setting, dict):
            continue
        if setting.get("type") == "object" and setting.get("settings"):
            result[key] = flatten_field_settings(setting["settings"])
        else:
            result[key] = setting.get("value")
    return result


def flatten_categories(categories):
    """inverse of build_settings_structure: category tree -> raw config dict"""
    result = {}

    for cat_key, category in categories.items():
        if not isinstance(category, dict):
            continue

        has_settings = bool(category.get("settings"))
        has_enabled = "enabled" in category
        has_disabled = "disabled" in category
        if not has_settings and not has_enabled and not has_disabled:
            continue

        if category.get("isModuleCategory"):
            entry = {}
            if has_enabled:
                entry["enabled"] = category["enabled"]
            if has_disabled:
                entry["disabled"] = category["disabled"]
            if has_settings:
                module_settings = {}
                for name, module in category["settings"].items():
                    if isinstance(module, dict) and module.get("value"):
                        module_settings[name] = flatten_field_settings(module["value"])
                entry["settings"] = module_settings
            result[cat_key] = entry
        else:
            result[cat_key] = flatten_field_settings(category.get("settings") or {})

    return result


def get_module_info():
    """schemas (descriptions, settings schemas, etc) for all modules/channels and for the core config sections"""
    module_info = {}

    for module_name, module_data in core.config.get_module_structure().items():
        metadata = module_data.get("metadata", {})
        module_info[module_name] = {
            "description": metadata.get("doc", ""),
            "unsafe": metadata.get("unsafe", False),
            "category": metadata.get("category", ""),
            "settings_schema": module_data.get("settings", {}),
        }

    core_sections = {}

    for section_name, section_data in core.config.get_core_settings_structure().items():
        core_sections[section_name] = {
            "description": section_data.get("metadata", {}).get("doc", ""),
            "unsafe": section_data.get("metadata", {}).get("unsafe", False),
            "settings_schema": section_data.get("settings", {}),
        }

    return module_info, core_sections
