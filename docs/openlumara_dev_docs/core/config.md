# Core: The Configuration System (`core.config`)

The `config` module is the central authority for application settings. It manages the loading, synchronization, and retrieval of configuration data from `config.yml`, ensuring that the application always has a valid and complete set of settings.

## Configuration Philosophy

OpenLumara uses a "Schema-First" approach to configuration. Instead of just loading a file, the system:
1.  **Defines a Schema**: A complete template of all possible settings (including those for modules that might not currently be enabled).
2.  **Synchronizes**: Merges the user's `config.yml` with the schema, ensuring that new settings are automatically added and old/invalid settings are pruned.
3.  **Dynamic Discovery**: Automatically discovers available modules and channels from the filesystem and integrates their specific settings into the main configuration.

## Key Components

### `ConfigManager`
A helper class used to navigate the hierarchical configuration structure. It allows for easy access to nested values.

**Usage**:
```python
# Accessing a nested value
url = config.get("api", "url")

# Accessing a value with a default
timeout = config.get("api", "timeout", default=30)
```

### `get_schema()`
This function generates the master configuration schema. This schema is used as the "source of truth" during the synchronization process. It includes:
- **Core Settings**: Application-wide defaults.
- **API Settings**: Connection and model parameters.
- **Module Settings**: The default settings for every possible module discovered on disk.

### `load()`
The primary entry point for the configuration system. When called, it:
1.  Reads `config.yml`.
2.  Discovers all available modules and channels.
3.  Synchronizes the existing config with the master schema.
4.  Reconciles the `enabled` and `disabled` lists to ensure they only contain valid, existing modules/channels.
5.  Saves the updated, cleaned configuration back to disk.

## Configuration Structure

The `config.yml` file follows a hierarchical structure:

```yaml
core:
  data_folder: "data"
  auto_resume_chats: True
  cmd_prefix: "/"

api:
  url: "http://localhost:5001/v1"
  key: "KEY_HERE"
  max_context: 8192
  # ... other API settings

model:
  name: "gpt-4"
  temperature: 0.7
  use_tools: True
  # ... other model settings

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

Conversely, if a module is removed from the filesystem, its settings are automatically pruned from the `config.yml` during the next load to keep the configuration clean.
