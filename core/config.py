import os
import yaml
import copy
import core
import modules
import user_modules
import channels

config = None
_registry_cache = None

default_config = {
    "core": {
        "data_folder": "data",
        "auto_resume_chats": True
    },
    "api": {
        "url": "http://localhost:5001/v1",
        "key": "KEY_HERE",
        "max_context": 8192,
        "max_output_tokens": 8192,
        "max_messages": 200,
        "custom_fields": {}
    },
    "model": {
        "name": "",
        "temperature": 0.2,
        "reasoning_effort": "medium",
        "use_tools": True
    },
    "channels": {
        "enabled": [],
        "disabled": [],
        "settings": {}
    },
    "modules": {
        "enabled": [],
        "disabled": [],
        "settings": {}
    },
    "user_modules": {
        "enabled": [],
        "disabled": [],
        "settings": {}
    }
}

# Define defaults for auto-enabling
DEFAULT_MODULES = (
    "openlumara_prompt",
    "identity",
    "models",
    "channel",
    "chats",
    "context",
    "memory",
    "notes",
    "lists",
    "system",
    "scheduler",
    "tokens",
    "time"
)

DEFAULT_CHANNELS = ["cli", "webui"]

def _get_registry_data():
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    # load instances
    mod_inst = list(core.modules.load(modules, core.module.Module))
    user_mod_inst = list(core.modules.load(user_modules, core.module.Module))
    chan_inst = list(core.modules.load(channels, core.channel.Channel))

    # define the sections to be managed
    _registry_cache = [
        {
            "section_key": "channels",
            "instances": chan_inst,
            "names": [core.modules.get_name(m) for m in chan_inst],
            "default_names": DEFAULT_CHANNELS
        },
        {
            "section_key": "modules",
            "instances": mod_inst,
            "names": [core.modules.get_name(m) for m in mod_inst],
            "default_names": DEFAULT_MODULES
        },
        {
            "section_key": "user_modules",
            "instances": user_mod_inst,
            "names": [core.modules.get_name(m) for m in user_mod_inst],
            "default_names": []
        }
    ]
    return _registry_cache

def _inject_settings_into_dict(target_dict, instances, section_key):
    """Helper to build the schema by injecting class settings defaults."""
    section = target_dict.setdefault(section_key, {})
    settings = section.setdefault("settings", {})
    for inst in instances:
        name = core.modules.get_name(inst)
        defaults = getattr(inst, 'settings', {})
        if isinstance(defaults, dict) and defaults:
            settings[name] = defaults.copy()

def get_schema():
    """returns the blueprint for a complete config file, including module and channel settings defined in their classes"""
    schema = copy.deepcopy(default_config)
    for item in _get_registry_data():
        _inject_settings_into_dict(schema, item['instances'], item['section_key'])
    return schema

def sync_config(user_config, schema):
    """Recursively syncs structural keys from the schema."""
    if not isinstance(schema, dict) or not isinstance(user_config, dict):
        return schema

    result = dict(user_config)
    for key, schema_val in schema.items():
        if key in result:
            user_val = result[key]
            if isinstance(schema_val, (dict, list)) and len(schema_val) == 0:
                continue
            if isinstance(schema_val, dict) and isinstance(user_val, dict):
                result[key] = sync_config(user_val, schema_val)
        else:
            result[key] = schema_val
    return result

def reconcile_lists(available_names, default_names, section_config):
    """
    Updates the enabled/disabled lists based on what is actually on disk
    """
    available = set(available_names)
    defaults = set(default_names)

    # 1. Get existing valid items
    enabled = set(section_config.get("enabled", [])) & available
    disabled = set(section_config.get("disabled", [])) & available

    # 2. Find items that are available but not yet in the config
    known = enabled | disabled
    new_items = available - known

    # 3. Distribute new items: those in 'defaults' are enabled, everything else is disabled
    new_enabled = new_items & defaults
    new_disabled = new_items - defaults

    return {
        "enabled": sorted(list(enabled | new_enabled)),
        "disabled": sorted(list(disabled | new_disabled))
    }

def sync_module_settings(config_dict, instances, section_key):
    """Performs deep pruning and merging of module settings."""
    section = config_dict.setdefault(section_key, {})
    settings = section.setdefault("settings", {})

    # 1. Top-level Prune: Remove settings for modules that no longer exist
    available_names = [core.modules.get_name(m) for m in instances]
    for k in [k for k in settings if k not in available_names]:
        del settings[k]

    # 2. Deep Prune & Merge
    for inst in instances:
        name = core.modules.get_name(inst)
        defaults = getattr(inst, 'settings', {})
        if not isinstance(defaults, dict):
            continue

        if name in settings and isinstance(settings[name], dict):
            curr = settings[name]
            # Remove keys that are no longer in the module's defaults
            for k in [k for k in curr if k not in defaults]:
                del curr[k]
            # Add missing keys from defaults
            for k, v in defaults.items():
                if k not in curr:
                    curr[k] = v

            # If the settings became empty after pruning, remove the entry entirely
            if not curr:
                del settings[name]

        elif defaults:  # Only insert if the module actually has settings to add
            settings[name] = defaults.copy()



def load(file_path=None):
    if file_path:
        filename = os.path.splitext(os.path.basename(file_path))[0]
        dirname = os.path.dirname(file_path)
    else:
        filename = "config"
        dirname = core.get_path()

    global config
    config = core.storage.StorageDict(filename, "yaml", path=dirname, autoreload=False)

    schema = get_schema()
    registry = _get_registry_data()

    created_new_config = False
    if not config:
        target = copy.deepcopy(schema)
        if not core.storage.TEMPORARY:
            created_new_config = True
    else:
        target = sync_config(dict(config), schema)

    # sync config with schema
    for item in registry:
        # sync module/channel settings
        sync_module_settings(target, item['instances'], item['section_key'])

        # reconcile lists (Enabled/Disabled)
        state = reconcile_lists(item['names'], item['default_names'], target.get(item['section_key'], {}))
        target[item['section_key']]['enabled'] = state['enabled']
        target[item['section_key']]['disabled'] = state['disabled']

    # load in the new edited config
    config.load(target)
    config.save()

    if created_new_config:
        print(f"A new configuration file has been created at {config.path}.")

def get(*args, **kwargs):
    """shorthand for accessing config values"""
    global config
    global default_config

    # fall back to default config if no config is loaded
    if config is None:
        try:
            val = default_config
            for arg in args: val = val[arg]
            return val
        except (KeyError, TypeError): return None

    return config.get(*args, **kwargs)
