# Core: The Manager (`core.Manager`)

The `Manager` is the central nervous system of OpenLumara. It is responsible for the initialization, orchestration, and lifecycle management of the entire framework.

## Responsibilities

### 1. Initialization and Startup
When the application starts, the `Manager` performs several critical tasks:
- **Config Loading**: Reads the configuration from `config.yml`.
- **Storage Initialization**: Initializes the `StorageDict` for persistent data.
- **Channel Loading**: Identifies and instantiates all enabled channels (e.g., WebUI, Telegram, CLI) from the `channels/` directory.
- **Module Loading**: Loads both core modules and user-defined modules from the `modules/` and `user_modules/` directories.
- **API Connection**: Attempts to establish a connection to the configured AI provider.

### 2. Lifecycle Management
The `Manager` controls the execution flow:
- **The Main Loop**: Runs the asynchronous task loop that keeps all channels and background module tasks active.
- **Task Management**: Tracks all running asynchronous tasks (channels, background modules, etc.) and ensures they are properly managed.
- **Shutdown**: Handles graceful shutdown, ensuring all modules and channels are notified and their resources are cleaned up.
- **Restart**: Provides a mechanism to restart the entire server (useful after configuration changes).

### 3. Orchestration
The `Manager` acts as the bridge between different components:
- **Module/Channel Bridge**: When a module is loaded, the `Manager` ensures it has access to the currently active channel.
- **Tool Provisioning**: As modules are loaded, the `Manager` scans them for functions that should be exposed as tools to the AI.
- **System Prompt Assembly**: The `Manager` coordinates with all active modules to build the complete system prompt used for AI requests.

## Key Methods

| Method | Description |
| :--- | :--- |
| `run()` | The main entry point that starts the entire system. |
| `shutdown()` | Gracefully stops all channels, modules, and background tasks. |
| `restart()` | Triggers a full system restart. |
| `add_module_class()` | Dynamically loads a module and extracts its tools. |
| `get_system_prompt()` | Aggregates system prompt fragments from all active modules. |
| `get_status()` | Returns a summary of the current server state (API status, context size, etc.). |
| `toggle_module()` | Enables or disables a module at runtime. |

## Internal Workflow (Startup)

1.  `Manager.__init__` is called with command-line arguments.
2.  `Manager.run()` is invoked.
3.  Channels are loaded and their `.run()` methods are scheduled as tasks.
4.  Core modules are loaded and their `._start()` methods are awaited.
5.  User modules are loaded and their `._start()` methods are awaited.
6.  The API connection is initialized.
7.  `asyncio.gather()` is called to run all tasks concurrently.
