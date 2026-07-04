import os
import yaml
import copy
import core
import modules
import user_modules
import channels
import user_channels
import pkgutil
import hashlib
import json
import inspect

config = None
_registry_cache = None

SCHEMA_CACHE_FILE = ".module_cache.json"

default_config = {
    "core": {
        "data_folder": "data",
        "auto_resume_chats": True,
        "cmd_prefix": "/",
        "tool_timeout": 15
    },
    "api": {
        "url": "http://localhost:5001/v1",
        "key": "KEY_HERE",
        "max_context": 8192,
        "max_output_tokens": 8192,
        "max_messages": 200,
        "use_developer_role": False,
        "custom_fields": {}
    },
    "model": {
        "name": "",
        "temperature": 0.7,
        "enable_thinking": True,
        "keep_reasoning_in_context": True,
        "only_preserve_reasoning_for_current_agentic_loop": True,
        "reasoning_effort": None,
        "use_tools": True
    },
    "channels": {
        "enabled": [],
        "disabled": [],
        "settings": {}
    },
    "user_channels": {
        "path": "user_channels",
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
    "tutorial",
    "docs",
    "identity",
    "writing_style",
    "models",
    "channel",
    "modules",
    "chats",
    "context",
    "memory",
    "notes",
    "lists",
    "scheduler",
    "calendar",
    "calculator",
    "token_threshold",
    "time",
    "auto_backup"
)

DEFAULT_CHANNELS = ["cli", "webui"]

class ConfigManager:
    def __init__(self, config, base_path=None):
        self.root_config = config
        self.base_path = base_path or []

    def get(self, *args, **kwargs):
        """Shorthand for accessing nested config values.
        Usage: config.get("api", "url") or config.get("api", "url", default_value)
        """
        # reload from disk
        self.root_config.load()

        default = kwargs.get("default", None)
        if not args:
            return default

        keys = list(args)
        # If the last argument is not a string, or is empty, treat it as an explicit default
        if keys and not isinstance(keys[-1], str) or not keys[-1]:
            default = keys.pop()

        # Start from the root config and traverse through the base path
        current = self.root_config
        for k in self.base_path:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        # Then traverse through the provided keys
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def to_dict(self):
        # reload from disk
        self.root_config.load()

        # Start from the root config and traverse through the base path
        current = self.root_config
        for k in self.base_path:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return {}

        return dict(current)

    def __getitem__(self, key):
        """Access items using bracket notation: config['key']"""
        current = self.root_config
        for k in self.base_path + [key]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                raise KeyError(key)
        return current

    def __setitem__(self, key, value):
        """Set items using bracket notation: config['key'] = value"""
        current = self.root_config
        for k in self.base_path:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[key] = value
        if hasattr(self.root_config, 'save'):
            self.root_config.save()

    def __contains__(self, key):
        """Check if key exists: 'key' in config"""
        current = self.root_config
        for k in self.base_path:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False
        return isinstance(current, dict) and key in current

def _discover_available_names(package):
    """
    Discover module names from filesystem WITHOUT importing them.
    This allows the config to know what modules exist without loading them.
    """
    if not hasattr(package, '__path__'):
        return []
    return [modname for _, modname, _ in pkgutil.iter_modules(package.__path__)]

def _get_registry_data(enabled_channels=None, enabled_user_channels=None, enabled_modules=None, enabled_user_modules=None):
    """
    Build registry data, importing ONLY enabled modules/channels.

    Available names are discovered via filesystem scanning.
    Instances are only created for enabled items.
    """
    global _registry_cache

    # Build cache key from enabled lists
    cache_key = (
        tuple(enabled_channels or []),
        tuple(enabled_user_channels or []),
        tuple(enabled_modules or []),
        tuple(enabled_user_modules or [])
    )

    if _registry_cache is not None and _registry_cache.get('key') == cache_key:
        return _registry_cache['data']

    # Discover all available names from filesystem (no imports!)
    available_channels = _discover_available_names(channels)
    available_user_channels = _discover_available_names(user_channels)
    available_modules = _discover_available_names(modules)
    available_user_modules = _discover_available_names(user_modules)

    # Only import and instantiate ENABLED items
    chan_inst = list(core.modules.load(
        channels, core.channel.Channel, filter=enabled_channels, loading_config=True
    )) if enabled_channels else []

    user_chan_inst = list(core.modules.load(
        user_channels, core.channel.Channel, filter=enabled_user_channels, loading_config=True
    )) if enabled_user_channels else []

    mod_inst = list(core.modules.load(
        modules, core.module.Module, filter=enabled_modules, loading_config=True
    )) if enabled_modules else []

    user_mod_inst = list(core.modules.load(
        user_modules, core.module.Module, filter=enabled_user_modules, loading_config=True
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
            "section_key": "user_channels",
            "instances": user_chan_inst,
            "available_names": available_user_channels,
            "names": [core.modules.get_name(m) for m in user_chan_inst],
            "default_names": []
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
            # We inject the full dict (including descriptions) into the schema.
            # sync_config will later replace these dicts with flat values
            # if the user has provided them in the config file.
            settings[name] = defaults.copy()

def _get_module_schema_cache():
    """
    Returns a dictionary containing the cached schemas and checksums for all modules/channels.
    If the cache is missing or outdated, it performs a refresh.
    """
    cache_path = os.path.abspath(os.path.join(core.get_path(), SCHEMA_CACHE_FILE))
    cache = {"channels": {}, "user_channels": {}, "modules": {}, "user_modules": {}}

    # Load existing cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                cache = json.load(f)
        except Exception as e:
            print(f"[CORE] error while loading module cache {core.detail_error(e)}")
    else:
        print(f"[CORE] creating module cache at {cache_path}")

    package_map = {
        "channels": (channels, core.channel.Channel),
        "user_channels": (user_channels, core.channel.Channel),
        "modules": (modules, core.module.Module),
        "user_modules": (user_modules, core.module.Module)
    }

    sections_to_refresh = set()

    # 1. Check for deletions or changes in existing cache
    for section_key, (package, _) in package_map.items():
        available_names = _discover_available_names(package)

        if section_key not in cache.keys():
            continue

        for name in list(cache[section_key].keys()):
            if name not in available_names:
                del cache[section_key][name]
                sections_to_refresh.add(section_key)
                continue

            # Find the file path to check checksum
            found_file = None
            for sub_path in package.__path__:
                # Try module.py
                f1 = os.path.join(sub_path, f"{name}.py")
                if os.path.exists(f1):
                    found_file = f1
                    break
                # Try module/__init__.py
                f2 = os.path.join(sub_path, name, "__init__.py")
                if os.path.exists(f2):
                    found_file = f2
                    break

            if found_file:
                if cache[section_key][name].get("checksum") != _get_file_checksum(found_file):
                    sections_to_refresh.add(section_key)
            else:
                sections_to_refresh.add(section_key)

        # 2. Check for new modules
        if section_key not in sections_to_refresh:
            for name in available_names:
                if name not in cache[section_key]:
                    sections_to_refresh.add(section_key)
                    break

    # 3. Refresh cache if needed
    if sections_to_refresh:
        for section_key in sections_to_refresh:
            package, base_class = package_map[section_key]
            try:
                # skip reloading modules because we just want the data
                classes = core.modules.load(package, base_class, reload=False, loading_config=True)

                for cls in classes:
                    name = core.modules.get_name(cls)
                    settings = getattr(cls, 'settings', {})

                    # Capture docstring and the unsafe class attribute
                    docstring = inspect.getdoc(cls) or ""
                    unsafe = getattr(cls, 'unsafe', False)

                    module = inspect.getmodule(cls)
                    checksum = ""
                    if module and hasattr(module, '__file__') and module.__file__:
                        py_file = module.__file__.replace('.pyc', '')
                        checksum = _get_file_checksum(py_file) if os.path.exists(py_file) else _get_file_checksum(module.__file__)

                    cache[section_key][name] = {
                        "schema": settings,
                        "checksum": checksum,
                        "metadata": {
                            "docstring": docstring,
                            "unsafe": unsafe  # Added to cache
                        }
                    }

            except Exception as e:
                print(f"[CORE] Failed to refresh cache for {section_key}: {core.detail_error(e)}")

        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            print(f"[CORE] failed to save module cache: {core.detail_error(e)}")

    return cache

def _get_file_checksum(filepath):
    """Calculate MD5 checksum of a file."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def get_schema(*args, **kwargs):
    """
    Returns the config schema using the on-disk cache.
    Contains all possible module settings to allow persistence for disabled modules.
    """
    schema = copy.deepcopy(default_config)
    cache = _get_module_schema_cache()

    for section_key, section_cache in cache.items():
        section = schema.setdefault(section_key, {})
        settings = section.setdefault("settings", {})
        for name, data in section_cache.items():
            # Flatten the settings here so the schema only contains values.
            # This prevents metadata (description, default) from leaking into the config file.
            settings[name] = _flatten_settings(data["schema"])

    return schema

def get_module_structure():
    """
    Returns a flat dictionary containing settings and metadata for all
    available modules, channels, and user_modules.

    Structure:
    {
        "name": {
            "settings": { ... },
            "metadata": {
                "doc": "...",
                "unsafe": True/False,
                "type": "module" | "channel" | "user_module"
            }
        }
    }
    """
    cache = _get_module_schema_cache()
    metadata_registry = {}

    # Map section keys to their descriptive type strings
    type_map = {
        "channels": "channel",
        "user_channels": "user_channel",
        "modules": "module",
        "user_modules": "user_module"
    }

    for section_key, section_cache in cache.items():
        type_str = type_map.get(section_key, "unknown")

        for name, data in section_cache.items():
            metadata = data["metadata"]

            metadata_registry[name] = {
                "settings": data["schema"],
                "metadata": {
                    "doc": metadata["docstring"],
                    "unsafe": metadata["unsafe"],
                    "type": type_str
                }
            }

    return metadata_registry

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


def _flatten_settings(settings_dict):
    """Recursively flattens a settings dictionary by extracting 'default' values."""
    if isinstance(settings_dict, dict) and "default" in settings_dict:
        return _flatten_settings(settings_dict["default"])
    if isinstance(settings_dict, dict):
        return {k: _flatten_settings(v) for k, v in settings_dict.items()}
    return settings_dict

def _merge_module_settings(current_settings, module_defaults):
    """Recursively merges current_settings with module_defaults schema."""
    if isinstance(module_defaults, dict) and "default" in module_defaults:
        if isinstance(current_settings, dict) and "default" in current_settings:
            return module_defaults["default"]
        return current_settings if current_settings is not None else module_defaults["default"]

    if not isinstance(module_defaults, dict):
        return current_settings if current_settings is not None else module_defaults

    if not isinstance(current_settings, dict):
        current_settings = {}

    new_settings = {}
    for k, v in module_defaults.items():
        if k in current_settings:
            new_settings[k] = _merge_module_settings(current_settings[k], v)
        else:
            new_settings[k] = _flatten_settings(v)
    return new_settings

def sync_module_settings(config_dict, instances, section_key, available_names):
    """
    Performs deep pruning and merging of module settings.
    - Removes settings for modules not on disk.
    - Keeps settings for disabled modules.
    - Merges defaults for enabled modules.
    """
    section = config_dict.setdefault(section_key, {})
    settings = section.setdefault("settings", {})

    # 1. Remove settings for modules that are no longer on the filesystem
    for name in list(settings.keys()):
        if name not in available_names:
            del settings[name]

    # 2. For modules that ARE on disk, handle enabled vs disabled
    for inst in instances:
        name = core.modules.get_name(inst)
        module_defaults = getattr(inst, 'settings', {})
        if not isinstance(module_defaults, dict):
            continue

        if name in settings and isinstance(settings[name], dict):
            # Module is enabled and has existing settings: merge them
            settings[name] = _merge_module_settings(settings[name], module_defaults)
            if not settings[name]:
                del settings[name]
        elif module_defaults:
            # Module is enabled but has no existing settings: provide defaults
            flat_defaults = _flatten_settings(module_defaults)
            if flat_defaults:
                settings[name] = flat_defaults

    # Note: If a module is in available_names but NOT in instances,
    # it is disabled and we leave its settings in 'settings' untouched.


def load(file_path=None):
    """
    Load config file.
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

    config = core.storage.StorageDict(filename, "yaml", path=dirname, override_temporary=True)
    if not config:
        new_config = True

    raw_config = dict(config) if config else {}

    enabled_channels = raw_config.get("channels", {}).get("enabled", [])
    if not enabled_channels and new_config:
        enabled_channels = DEFAULT_CHANNELS

    enabled_modules = raw_config.get("modules", {}).get("enabled", [])
    if not enabled_modules and new_config:
        enabled_modules = DEFAULT_MODULES

    enabled_user_modules = raw_config.get("user_modules", {}).get("enabled", [])
    enabled_user_channels = raw_config.get("user_channels", {}).get("enabled", [])

    # Use the new cached schema (contains all possible settings)
    schema = get_schema()

    # Registry only contains ENABLED instances and their available names
    registry = _get_registry_data(enabled_channels, enabled_user_channels, enabled_modules, enabled_user_modules)

    if new_config:
        target = copy.deepcopy(schema)
    else:
        target = sync_config(raw_config, schema)

    # Sync settings and reconcile lists
    for item in registry:
        # Pass available_names so we know what to prune
        sync_module_settings(target, item['instances'], item['section_key'], item['available_names'])

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
    """Shorthand for accessing nested config values.
    Usage: config.get("api", "url") or config.get("api", "url", default_value)
    """
    global config, default_config

    default = kwargs.get("default", None)
    if not args:
        return default

    keys = list(args)
    # If the last argument is not a string, or is empty, treat it as an explicit default
    if keys and not isinstance(keys[-1], str) or not keys[-1]:
        default = keys.pop()

    # Safely resolve to a dictionary
    try:
        value = dict(config) if config else dict(default_config)
    except (TypeError, ValueError):
        value = dict(default_config)

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value
