import os
import yaml
import copy
import core
import modules
import user_modules
import channels
import pkgutil

config = None
_registry_cache = None

default_config = {
    "core": {
        "data_folder": "data",
        "auto_resume_chats": True,
        "cmd_prefix": "/"
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
        "path": "user_modules",
        "enabled": [],
        "disabled": [],
        "settings": {}
    }
}

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

def _discover_available_names(package):
    """
    Discover module names from filesystem WITHOUT importing them.
    This allows the config to know what modules exist without loading them.
    """
    if not hasattr(package, '__path__'):
        return []
    return [modname for _, modname, _ in pkgutil.iter_modules(package.__path__)]

def _get_registry_data(enabled_channels=None, enabled_modules=None, enabled_user_modules=None):
    """
    Build registry data, importing ONLY enabled modules/channels.

    Available names are discovered via filesystem scanning.
    Instances are only created for enabled items.
    """
    global _registry_cache

    # Build cache key from enabled lists
    cache_key = (
        tuple(enabled_channels or []),
        tuple(enabled_modules or []),
        tuple(enabled_user_modules or [])
    )

    if _registry_cache is not None and _registry_cache.get('key') == cache_key:
        return _registry_cache['data']

    # Discover all available names from filesystem (no imports!)
    available_channels = _discover_available_names(channels)
    available_modules = _discover_available_names(modules)
    available_user_modules = _discover_available_names(user_modules)

    # Only import and instantiate ENABLED items
    chan_inst = list(core.modules.load(
        channels, core.channel.Channel, filter=enabled_channels
    )) if enabled_channels else []

    mod_inst = list(core.modules.load(
        modules, core.module.Module, filter=enabled_modules
    )) if enabled_modules else []

    user_mod_inst = list(core.modules.load(
        user_modules, core.module.Module, filter=enabled_user_modules
    )) if enabled_user_modules else []

    result = [
        {
            "section_key": "channels",
            "instances": chan_inst,
            "available_names": available_channels,
            "names": [core.modules.get_name(m) for m in chan_inst],
            "default_names": DEFAULT_CHANNELS
        },
        {
            "section_key": "modules",
            "instances": mod_inst,
            "available_names": available_modules,
            "names": [core.modules.get_name(m) for m in mod_inst],
            "default_names": DEFAULT_MODULES
        },
        {
            "section_key": "user_modules",
            "instances": user_mod_inst,
            "available_names": available_user_modules,
            "names": [core.modules.get_name(m) for m in user_mod_inst],
            "default_names": []
        }
    ]

    _registry_cache = {'key': cache_key, 'data': result}
    return result

def _inject_settings_into_dict(target_dict, instances, section_key):
    """Helper to build the schema by injecting class settings defaults."""
    section = target_dict.setdefault(section_key, {})
    settings = section.setdefault("settings", {})
    for inst in instances:
        name = core.modules.get_name(inst)
        defaults = getattr(inst, 'settings', {})
        if isinstance(defaults, dict) and defaults:
            settings[name] = defaults.copy()

def get_schema(enabled_channels=None, enabled_modules=None, enabled_user_modules=None):
    """
    Returns the config schema. Only enabled modules are imported.
    """
    schema = copy.deepcopy(default_config)
    for item in _get_registry_data(enabled_channels, enabled_modules, enabled_user_modules):
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
    Updates the enabled/disabled lists based on filesystem discovery.
    available_names comes from filesystem scanning, not imports.
    """
    available = set(available_names)
    defaults = set(default_names)

    enabled = set(section_config.get("enabled", [])) & available
    disabled = set(section_config.get("disabled", [])) & available

    known = enabled | disabled
    new_items = available - known

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

    available_names = [core.modules.get_name(m) for m in instances]
    for k in [k for k in settings if k not in available_names]:
        del settings[k]

    for inst in instances:
        name = core.modules.get_name(inst)
        defaults = getattr(inst, 'settings', {})
        if not isinstance(defaults, dict):
            continue

        if name in settings and isinstance(settings[name], dict):
            curr = settings[name]
            for k in [k for k in curr if k not in defaults]:
                del curr[k]
            for k, v in defaults.items():
                if k not in curr:
                    curr[k] = v
            if not curr:
                del settings[name]
        elif defaults:
            settings[name] = defaults.copy()

def load(file_path=None):
    """
    Load config file. Modules are only imported if they're in the enabled list.
    """
    if file_path:
        filename = os.path.splitext(os.path.basename(file_path))[0]
        dirname = os.path.dirname(file_path)
    else:
        filename = "config"
        dirname = core.get_path()

    new_config = False

    global config
    global _registry_cache
    _registry_cache = None

    # load config from disk
    config = core.storage.StorageDict(filename, "yaml", path=dirname, autoreload=False)
    if not config:
        new_config = True

    if not new_config and core.storage.TEMPORARY:
        config.load()

    # Read raw config to extract enabled lists BEFORE importing modules
    raw_config = dict(config) if config else {}

    enabled_channels = raw_config.get("channels", {}).get("enabled", [])
    if not enabled_channels and new_config:
        enabled_channels = DEFAULT_CHANNELS

    enabled_modules = raw_config.get("modules", {}).get("enabled", [])
    if not enabled_modules and new_config:
        enabled_modules = DEFAULT_MODULES

    enabled_user_modules = raw_config.get("user_modules", {}).get("enabled", [])

    # Now build schema using ONLY enabled modules
    schema = get_schema(enabled_channels, enabled_modules, enabled_user_modules)
    registry = _get_registry_data(enabled_channels, enabled_modules, enabled_user_modules)

    if new_config:
        target = copy.deepcopy(schema)
    else:
        target = sync_config(raw_config, schema)

    # Sync settings and reconcile lists
    for item in registry:
        sync_module_settings(target, item['instances'], item['section_key'])

        # Use available_names (filesystem discovered) instead of imported names
        state = reconcile_lists(
            item['available_names'],
            item['default_names'],
            target.get(item['section_key'], {})
        )
        target[item['section_key']]['enabled'] = state['enabled']
        target[item['section_key']]['disabled'] = state['disabled']

    config.load(target)
    config.save()

    if new_config:
        print(f"A new configuration file has been created at {config.path}.")

def get(*args, **kwargs):
    """shorthand for accessing config values"""
    global config
    global default_config

    if config is None:
        try:
            val = default_config
            for arg in args:
                val = val[arg]
            return val
        except (KeyError, TypeError):
            return None

    return config.get(*args, **kwargs)
