# Core: The Configuration System (`core.config`)

The `config` module is the central authority for application settings. It manages the loading, synchronization, and retrieval of configuration data from `config.yml`, ensuring that the application always has a valid and complete set of settings.

## Configuration Philosophy

OpenLumara uses a "Schema-First" approach to configuration. Instead of just loading a file, the system:
1.  **Defines a Schema**: A complete template of all possible settings (including those for modules that might not currently be enabled).
2.  **Synchronizes**: Merges the user's `config.yml` with the schema, ensuring that new settings are automatically added and old/invalid settings are pruned.
3.  **Dynamic Discovery**: Automatically discovers available modules and channels from the filesystem and integrates their specific settings into the main configuration.
4.  **On-Disk Caching**: Module schemas are cached on disk (`.module_cache.json`) with MD5 checksums to detect changes without re-importing modules.

## Key Components

### `ConfigManager`
A helper class used to navigate the hierarchical configuration structure. It wraps a `StorageDict` and traverses a base path to reach nested settings.

**Usage**:
```python
# Accessing a nested value (shorthand)
url = config.get("api", "url")

# Accessing a value with a default
timeout = config.get("api", "timeout", default=30)

# Bracket notation (also reloads from disk)
value = config["api"]["url"]
config["api"]["url"] = "http://new-url"
```

**Methods**:
| Method | Description |
| :--- | :--- |
| `get(*keys, default=None)` | Retrieves a nested value by traversing keys. Reloads from disk on each call. |
| `to_dict()` | Returns the config section at the base path as a plain dict (also reloads). |
| `__getitem__(key)` | Bracket access: `config["key"]`. Raises `KeyError` if not found. |
| `__setitem__(key, value)` | Bracket assignment: `config["key"] = value`. Auto-saves if the root has a `save` method. |
| `__contains__(key)` | Membership test: `"key" in config`. |

### `get_schema()`
Generates the master configuration schema using the on-disk cache. Contains all possible module settings to allow persistence for disabled modules. The schema includes:
- **Core Settings**: Application-wide defaults.
- **API Settings**: Connection and model parameters.
- **Module Settings**: The default settings for every possible module discovered on disk.

### `get_module_structure()`
Returns a flat dictionary containing settings and metadata for all available modules, channels, and user_modules.

**Structure**:
```python
{
    "name": {
        "settings": { ... },
        "metadata": {
            "doc": "Module docstring...",
            "unsafe": True/False,
            "type": "module" | "channel" | "user_module"
        }
    }
}
```

### `load(file_path=None)`
The primary entry point for the configuration system. When called, it:
1.  Reads `config.yml` (or a custom path).
2.  Discovers all available modules and channels via filesystem scanning (no imports needed for names).
3.  Synchronizes the existing config with the master schema (via `sync_config()`).
4.  Reconciles the `enabled` and `disabled` lists to ensure they only contain valid, existing modules/channels (via `reconcile_lists()`).
5.  Syncs and prunes module settings (via `sync_module_settings()`).
6.  Saves the updated, cleaned configuration back to disk.

## Configuration Structure

The `config.yml` file follows a hierarchical structure:

```yaml
core:
  data_folder: "data"
  auto_resume_chats: True
  cmd_prefix: "/"
  tool_timeout: 15

api:
  url: "http://localhost:5001/v1"
  key: "KEY_HERE"
  max_context: 8192
  max_output_tokens: 8192
  max_messages: 200
  use_developer_role: False
  custom_fields: {}

model:
  name: "gpt-4"
  temperature: 0.7
  enable_thinking: True
  keep_reasoning_in_context: True
  only_preserve_reasoning_for_current_agentic_loop: True
  reasoning_effort: null
  use_tools: True

channels:
  enabled: ["webui", "telegram"]
  disabled: ["matrix"]
  settings:
    webui:
      host: "0.0.0.0"
      port: 8080

modules:
  enabled: ["memory", "scheduler"]
  disabled: ["tutorial"]
  settings:
    memory:
      enabled: True
    scheduler:
      interval: 60

user_modules:
  path: "user_modules"
  enabled: []
  disabled: []
  settings: {}
```

## Dynamic Module Settings

One of the most powerful features of OpenLumara is how it handles module settings. When a new module is added to the `modules/` folder, its default settings are automatically included in the `config.yml` the next time the system starts. This allows for seamless extensibility without manual configuration editing.

Conversely, if a module is removed from the filesystem, its settings are automatically pruned from the `config.yml` during the next load to keep the configuration clean. Module settings are preserved when the module is disabled - they only get pruned when the actual module .py file is removed from disk.

## Internal Functions

### `sync_config(user_config, schema)`
Recursively syncs structural keys from the schema into the user config, adding missing keys from the schema while preserving existing user values.

### `reconcile_lists(available_names, default_names, section_config)`
Updates the `enabled` and `disabled` lists based on filesystem discovery. New items not in either list are added to `enabled` if they're in the defaults, otherwise to `disabled`.

### `sync_module_settings(config_dict, instances, section_key, available_names)`
Performs deep pruning and merging of module settings:
- Removes settings for modules no longer on the filesystem.
- Keeps settings for disabled modules untouched.
- Merges defaults for enabled modules.

### `_discover_available_names(package)`
Discovers module names from the filesystem **without importing them** using `pkgutil`. This allows the config to know what modules exist without loading them.

### `_get_registry_data(enabled_channels, enabled_modules, enabled_user_modules)`
Builds registry data by importing **only enabled** modules/channels. Returns instances, available names, and default names for each section. Cached globally via `_registry_cache`.

### `_get_module_schema_cache()`
Returns a dictionary containing the cached schemas and MD5 checksums for all modules/channels. If the cache file (`.module_cache.json`) is missing, outdated (checksum mismatch), or contains deleted modules, it performs a refresh by importing enabled modules and capturing their `settings`, docstrings, and `unsafe` attribute.

### `_flatten_settings(settings_dict)`
Recursively flattens a settings dictionary by extracting `default` values. Converts nested schema dicts into plain value dicts.

### `_merge_module_settings(current_settings, module_defaults)`
Recursively merges current settings with module defaults schema, preserving user overrides while adding new defaults.

## Global Variables

| Variable | Description |
| :--- | :--- |
| `config` | The main `StorageDict` instance holding the loaded configuration. |
| `_registry_cache` | Global cache for registry data (keyed by enabled module/channel lists). |
| `SCHEMA_CACHE_FILE` | Filename for the on-disk module schema cache (`.module_cache.json`). |
| `DEFAULT_MODULES` | Tuple of default module names that should be enabled on fresh installs. |
| `DEFAULT_CHANNELS` | Tuple of default channel names (`["cli", "webui"]`). |
| `default_config` | The base configuration template with all default values. |

## Dynamic Module Settings

One of the most powerful features of OpenLumara is how it handles module settings. When a new module is added to the `modules/` folder, its default settings are automatically included in the `config.yml` the next time the system starts. This allows for seamless extensibility without manual configuration editing.

Conversely, if a module is removed from the filesystem, its settings are automatically pruned from the `config.yml` during the next load to keep the configuration clean.
