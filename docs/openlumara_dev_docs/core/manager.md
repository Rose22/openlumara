# Core: The Manager (`core.Manager`)

The `Manager` is the central nervous system of OpenLumara. It is responsible for the initialization, orchestration, and lifecycle management of the entire framework.

## Responsibilities

### 1. Initialization and Startup
When the application starts, the `Manager` performs several critical tasks:
- **Config Loading**: Reads the configuration from `config.yml`.
- **Storage Initialization**: Initializes the `StorageDict` for persistent data (`save.msgpack`).
- **Channel Loading**: Identifies and instantiates all enabled channels (e.g., WebUI, Telegram, CLI) from the `channels/` directory. Always loads the `logger` channel first.
- **Module Loading**: Loads both core modules and user-defined modules from the `modules/` and `user_modules/` directories.
- **Auto-Installer**: Installs/uninstalls Python dependencies for enabled/disabled modules and channels (unless `--disable-auto-installer` is passed).
- **API Connection**: Attempts to establish a connection to the configured AI provider (non-fatal — continues in disconnected mode on failure).

### 2. Execution Modes
The `Manager` supports special execution modes via command-line arguments:
- **Pure Mode** (`--pure`): Disables all modules. No tools, no AI logic — just the channel.
- **Coder Mode** (`--coder`): Loads only the `coder` module, disabling all others.

### 3. Lifecycle Management
The `Manager` controls the execution flow:
- **The Main Loop**: Runs the asynchronous task loop (`asyncio.gather()`) that keeps all channels and background module tasks active.
- **Task Management**: Tracks all running asynchronous tasks in `self._async_tasks`. Each task has a done callback (`_remove_async_task`) for cleanup.
- **Shutdown**: Handles graceful shutdown with double-shutdown prevention (`_prevent_double_shutdown`). Calls `on_shutdown()` on all modules and channels, then cancels all async tasks.
- **Restart**: Sets `_restart_requested` flag, triggers shutdown, and returns `"restart"` from `run()`.

### 4. Orchestration
The `Manager` acts as the bridge between different components:
- **Module/Channel Bridge**: When a module is loaded, the `Manager` ensures it has access to the currently active channel via `_set_as_active_channel()`.
- **Tool Provisioning**: As modules are loaded, the `Manager` scans them for functions that should be exposed as tools to the AI (via `load_module_tools()`).
- **System Prompt Assembly**: The `Manager` coordinates with all active modules to build the complete system prompt used for AI requests, categorizing prompts into top/middle/bottom sections.

### 5. Logging
- **Broadcast Logging**: `log()` propagates messages to **all** channels via `on_log()`.
- **Error Logging**: `log_error()` includes full tracebacks in debug mode.
- **Log Buffer**: During early initialization (before channels are loaded), log messages are buffered in `core.modules.log_buffer` and drained once channels are ready.

## Key Methods

| Method | Description |
| :--- | :--- |
| `run()` | The main entry point that starts the entire system. Loads channels, modules, connects API, and runs the async loop. |
| `shutdown()` | Gracefully stops all channels, modules, and background tasks. Double-shutdown safe. |
| `restart()` | Triggers a full system restart by setting a flag and calling shutdown. |
| `toggle_module(module_name, autorestart=True)` | Enables or disables a module at runtime. Auto-restarts by default. |
| `reload_module(module_name)` | Reloads a specific module: unloads tools → runs `on_shutdown()` → runs `on_ready()` → reloads tools. |
| `add_module_class(module, is_user_module=False)` | Instantiates a module class and returns it. Handles pure/coder mode checks. |
| `load_module_tools(module)` | Scans a module for callable methods and registers them as AI tools. |
| `unload_module_tools(module)` | Removes all tools belonging to a module from the manager's tool list. |
| `get_system_prompt()` | Aggregates system prompt fragments from all active modules, categorized into top/middle/bottom sections. Respects `disabled_prompts` config and character module overrides. |
| `get_end_prompt(prevent_recursion=False)` | Aggregates end prompt fragments from all active modules. Prevents recursion for `token_threshold` module. |
| `get_status()` | Returns a summary of the current server state (API status, context size, etc.). |
| `get_settings_structure()` | Returns the settings structure for all loaded modules (for WebUI settings editor). |
| `get_api_status()` | Returns current API connection status (connected, error, URL, model, etc.). |
| `reconnect_api()` | Manually triggers API reconnection. Returns a status dict. |
| `parse_tool_docstring(docstring)` | Parses Google-style docstrings to extract parameter descriptions and returns a cleaned docstring. |

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `API` | `APIClient` | The API client instance (connected later via `_initialize_api_connection()`). |
| `savedata` | `StorageDict` | Persistent storage for app-wide data (`save.msgpack`). |
| `channels` | `dict` | Dictionary of all loaded channel instances, keyed by name. |
| `channel` | `Channel \| None` | The currently active channel (dynamically switched). |
| `modules` | `dict` | Dictionary of all loaded module instances, keyed by name. |
| `broken_modules` | `list` | Tracks module names that threw errors during prompt generation (skipped in future). |
| `tools` | `list` | List of all registered tool definitions (JSON schema objects). |
| `tool_names` | `list` | List of all registered tool names (strings). |
| `_async_tasks` | `set` | Set of all running async tasks (channels, background modules, etc.). |
| `pure_mode` | `bool` | If True, disables all modules. |
| `coding_mode` | `bool` | If True, loads only the `coder` module. |

## System Prompt Categorization

The `get_system_prompt()` method categorizes module prompts into three sections:
- **Top**: `agent_framework_awareness`, `identity`, `memory`, `writing_style`
- **Bottom**: `time`, `system`
- **Middle**: All other modules

Modules can override their header via a `header` class attribute. Disabled prompts are listed in `config.modules.disabled_prompts`.

## Tool Registration Flow

1. `load_module_tools()` iterates over all public methods of a module (excluding `_`-prefixed, `result`, and `on_*` methods).
2. Skips methods decorated with `@core.module.command`.
3. Parses the docstring for parameter descriptions.
4. Inspects the function signature to determine parameter types (`str`→`string`, `int`→`integer`, `bool`→`boolean`, `list`→`array`, `dict`→`object`).
5. Builds a JSON schema tool object with `strict: true`.
6. Appends to `self.tools` and `self.tool_names`.

## Global Instance

The `Manager` exposes a global instance via `core.manager.global_instance`, allowing early-stage code (e.g., during config loading) to access the manager for logging before it's fully initialized.

## Internal Workflow (Startup)

1.  `Manager.__init__` is called with command-line arguments.
2.  `Manager.run()` is invoked.
3.  Channels are loaded, dependencies installed, and sorted with `logger` first.
4.  Each channel is instantiated and its `run()` task is scheduled.
5.  Core modules are loaded, dependencies installed, and `._start()` awaited.
6.  User modules are loaded, dependencies installed, and `._start()` awaited.
7.  Disabled module/channel dependencies are uninstalled.
8.  API connection is attempted (non-fatal).
9.  `on_ready()` is called on all channels.
10. `asyncio.gather()` runs all tasks concurrently.
11. On exit, `shutdown()` is called (graceful), and restart is checked.
