# OpenLumara Architecture Overview

OpenLumara is designed as a modular, highly efficient AI agent framework. Its architecture is centered around a core management system that orchestrates communication, intelligence, and persistence.

## High-Level Architecture

The system is composed of five primary layers:

1.  **Core Layer (`core/`)**: The heart of the framework. It manages the lifecycle of the application, handles the main loop, orchestrates modules and channels, manages the API connection, and provides utility functions.
2.  **Module Layer (`modules/`)**: Provides extensible functionality. Modules can inject themselves into the system prompt, run background tasks, handle user/assistant messages, and provide tools (functions) for the AI to use.
3.  **Channel Layer (`channels/`)**: Defines how the user interacts with the system. Channels (like WebUI, Telegram, or CLI) handle input/output and maintain their own unique context windows.
4.  **Configuration Layer (`core.config`)**: Manages application settings using a "Schema-First" approach with dynamic module discovery, automatic synchronization, and on-disk caching.
5.  **Data/Persistence Layer (`core.storage` + `data/`)**: Handles storage of chats, characters, memories, and other persistent information using specialized classes (`StorageList`, `StorageDict`, `StorageText`) with support for JSON, YAML, MessagePack, Text, and Markdown formats.

## Key Components

### The Manager (`core.Manager`)
The central orchestrator. It is responsible for:
- Loading and starting all enabled channels and modules.
- Managing the active channel (dynamically switched).
- Handling the main execution loop via `asyncio.gather()`.
- Managing the API connection with auto-reconnect.
- Orchestrating the shutdown process with double-shutdown prevention.
- Loading and registering AI tools from modules.
- Assembling system prompts from all active modules (with top/middle/bottom categorization).
- Broadcasting logs to all channels via a log buffer system.
- Supporting special execution modes: **Pure Mode** (`--pure`, no modules) and **Coder Mode** (`--coder`, only coder module).
- Exposing a global instance (`core.manager.global_instance`) for early-stage code access.

### Modules (`core.Module`)
The extensibility mechanism. Modules are Python classes that can:
- **Inject Prompts**: Add content to the system prompt (`on_system_prompt`), end prompt (`on_end_prompt`), or user messages (`on_message_inject`).
- **Provide Tools**: Expose functions that the AI can call via function calling (auto-scanned by Manager).
- **Listen to Events**: React to user messages, assistant messages, or system readiness.
- **Run Background Tasks**: Execute continuous tasks like schedulers or monitors (checked for empty coroutines before starting).
- **Define Settings**: User-configurable settings with schema descriptions, automatically synced to config.
- **Mark as Unsafe**: Set `unsafe = True` to flag risky modules in UIs.
- **Declare Dependencies**: List Python packages that are auto-installed/uninstalled.
- **Non-Agentic Mode**: Modules in `core.modules.nonagentic` (`characters`, `writing_style`, `time`) have prompts injected even when tools are disabled.

### Channels (`core.Channel`)
The interface layer. Each channel:
- Manages its own **Context** (conversation history and token usage).
- Implements its own input/output logic (e.g., web sockets for WebUI, long polling for Telegram).
- Handles command processing via `core.Commands`.
- Provides a "push queue" for announcements and reminders.
- Supports streaming responses with token-by-token yielding.
- Merges settings from parent channel classes via `__init_subclass__`.
- Declares Python dependencies for auto-installation.

### Context (`core.Context`)
The intelligence-enabling component. It manages the "view" of the conversation that is sent to the AI, ensuring:
- **Token Efficiency**: Binary search trimming to fit within limits (with 5% safety buffer).
- **Prompt Construction**: Combining system prompts, message history, and end-prompts in the correct order.
- **Role Management**: Enforcing proper turn-taking (system -> user -> assistant) with spacer messages.
- **Message Filtering**: Removing ghost messages, signal messages, and invalid assistant messages.
- **Reasoning Control**: Stripping reasoning content based on config (`keep_reasoning_in_context`, `only_preserve_reasoning_for_current_agentic_loop`).
- **Multimodal Optimization**: Stripping non-text content from all messages except the most recent.
- **Injection Processing**: Appending module message injections (e.g., timestamps) to user messages.
- **Summarization Cutoff**: Supporting `SUMMARIZATION_CUTOFF` signals for chat summarization.
- **Max Messages Limit**: Enforcing `api.max_messages` (default 200) before token trimming.

### Chat (`core.Chat`)
The session persistence layer. It manages:
- A collection of chat sessions stored as `StorageList`.
- Automatic title generation from first user message.
- Auto-resume of the last used chat via a save file.
- Cleanup of empty chats and command-only chats on initialization.
- Token tracking (API-provided or local tiktoken estimation).
- Message operations (add, pop, delete, set, delete_from, get_last_message_with_role).
- Metadata management (title, category, tags, custom_data).
- Ghost message support (invisible to AI but visible in history).

### Configuration (`core.config`)
The settings authority. It provides:
- **Schema-First Approach**: Defines a complete template of all settings (including for disabled modules).
- **Dynamic Discovery**: Discovers available modules/channels from filesystem without importing.
- **Synchronization**: Merges user config with schema, adding new settings and pruning invalid ones.
- **On-Disk Caching**: Module schemas cached in `.module_cache.json` with MD5 checksums to detect changes.
- **ConfigManager**: Helper class for navigating hierarchical config with bracket notation support.
- **Auto-Reload**: Module settings changes trigger automatic module reloading.
- **Type Conversion**: Automatic string-to-type conversion for config values.

### Command System (`core.Commands`)
The user control layer. It provides:
- **Built-in Commands**: Hardcoded commands for system control (chat, config, modules, status, etc.).
- **Module Commands**: Dynamically discovered via `@core.module.command` decorator.
- **Authorization**: Public commands (`new`, `clear`, `status`, `stop`) accessible without auth; others require authorization.
- **Ghost Flagging**: Temporary commands (in `GHOST` list or marked `send_to_ai=False`) are invisible to AI.
- **Hierarchical Config**: `/config` command for exploring and modifying settings at runtime.
- **Type Conversion**: Automatic conversion of string inputs to booleans, integers, floats.

### API Client (`core.APIClient`)
The AI interaction layer. It provides:
- **Connection Management**: Connect, disconnect, reconnect with user-friendly error messages.
- **Request Orchestration**: Builds request bodies with all config parameters, custom fields, and reasoning settings.
- **Request Cancellation**: Uses background task monitoring to abort ongoing requests.
- **Standard Responses**: Extracts content, reasoning, and tool calls from responses.
- **Streaming Responses**: Yields typed tokens (content, reasoning, tool_call_delta, tool_calls, token_usage, prompt_progress, timings).
- **Error Handling**: Catches and categorizes API errors (auth, rate limit, connection, model not found, etc.).

### Tool Call Manager (`core.ToolcallManager`)
The function execution layer. It provides:
- **Tool Call Repair**: Uses `json_repair` to fix malformed JSON in tool call arguments.
- **Tool Resolution**: Scans modules to find the owning module by name prefix.
- **Tool Execution**: Executes functions with configurable timeout (`core.tool_timeout`, default 10s).
- **Recursive Calling**: Loops tool results back to the AI until no more tool calls are needed.
- **Display Formatting**: Formats tool calls for user display with truncated arguments.
- **Error Handling**: Catches timeouts and exceptions, wrapping results in `module.result()` format.

### Storage System (`core.storage`)
The persistence layer. It provides:
- **StorageList**: Auto-saving list for chat histories and other list data.
- **StorageDict**: Auto-saving dict for configs, save data, and complex metadata. Supports hierarchical Markdown storage.
- **StorageText**: Simple text file storage for single string values.
- **Multiple Formats**: JSON (default), YAML (configs), MessagePack (efficient binary), Text, Markdown.
- **Autoload/Autoreload**: Automatic loading on instantiation and optional re-reading on every access.

### Utility Functions (`core.functions`)
Low-level utilities for early-stage code (before Manager is ready):
- **Logging**: `log()` and `log_error()` that delegate to Manager if available, otherwise print directly.
- **Error Handling**: `detail_error()` for compact exception details with traceback in debug mode.
- **Path Management**: `get_path()`, `get_data_path()`, `sandbox_path()` with traversal attack protection.
- **Path Validation**: `validate_path_string()` handles URL decoding, normalization, and symlink blocking.

### Exception System (`core.exceptions`)
Custom exceptions:
- **DependencyMissing**: Raised when a required package is not installed.
- **UnauthorizedException**: Raised when a command requires authorization.

## Data Flow

1.  **User Input**: A user sends a message through a **Channel**.
2.  **Command Check**: The Channel checks if the input is a command. If so, `Commands.process_input()` handles it (ghost-flagged, added to history, result returned).
3.  **Auto-Reconnect**: If not connected to the API, attempts one reconnect.
4.  **Context Update**: The Channel adds the message to its **Chat** history (with auto-title, ghost flagging, and module injection).
5.  **Module Hooks**: Runs `on_user_message()` on all loaded modules.
6.  **Context Building**: The **Context** builds the full prompt:
    - Gathers system prompts from all modules (top/middle/bottom categorization).
    - Retrieves message history from Chat.
    - Applies max messages limit, token trimming (binary search), role enforcement, and injection processing.
    - Appends end prompts from modules.
7.  **AI Request**: The **APIClient** sends the context to the AI with tools, reasoning settings, and custom fields.
8.  **AI Response**: The APIClient returns the response (or streaming tokens).
9.  **Tool Execution (if needed)**: The **ToolcallManager** processes tool calls:
    - Repairs malformed JSON arguments.
    - Finds the owning module and executes the function (with timeout).
    - Adds tool results to context.
    - Recursively sends results back to the AI until no more tool calls are needed.
    - Sets `agentic_loop_start` for reasoning preservation.
10. **Module Hooks**: Runs `on_assistant_message()` on all loaded modules.
11. **Output**: The final response is formatted and sent back through the **Channel** to the user.

## Startup Sequence

1.  `Manager.__init__` is called with command-line arguments.
2.  `Manager.run()` is invoked.
3.  **Config Loading**: `core.config.load()` reads `config.yml`, discovers modules/channels, synchronizes with schema, and saves.
4.  **Storage Initialization**: Creates `save.msgpack` for persistent state.
5.  **Channel Loading**:
    - Discovers enabled channels from config.
    - Installs dependencies for newly enabled channels.
    - Loads channel classes via `core.modules.load()`.
    - Instantiates channels and schedules their `run()` tasks.
    - Starts push queue tasks.
6.  **Module Loading**:
    - Installs dependencies for newly enabled modules.
    - Loads core modules (`modules/`) via `core.modules.load()`.
    - Instantiates each module, runs `on_ready()`, and registers tools.
    - Loads user modules (`user_modules/`) the same way.
7.  **Uninstall Dependencies**: Uninstalls deps for disabled modules/channels.
8.  **API Connection**: Attempts to connect to the AI provider (non-fatal).
9.  **Channel Ready**: Calls `on_ready()` on all channels.
10. **Main Loop**: `asyncio.gather()` runs all tasks concurrently.
11. **Shutdown**: On exit, calls `shutdown()` which runs `on_shutdown()` on all modules/channels, cancels tasks, and waits.

## Module Loading Flow

1.  `core.modules.load()` iterates through package files using `pkgutil`.
2.  **Dependency Check**: Parses each module file with `ast` to extract `dependencies` list and checks installation status.
3.  **Conditional Import**: Imports only modules in the `filter` list.
4.  **Reload Support**: If `reload=True`, forces `importlib.reload()`.
5.  **Class Discovery**: Scans the module for classes inheriting from `base_class` (e.g., `core.module.Module`).
6.  **Error Handling**: Catches all exceptions; logs errors and adds failed modules to `reported_broken`.
7.  **Return**: Returns a tuple of discovered classes.

## Configuration Flow

1.  `core.config.load()` reads `config.yml` into a `StorageDict`.
2.  Discovers available modules/channels via `_discover_available_names()` (filesystem scanning, no imports).
3.  Gets the master schema via `get_schema()` (uses on-disk cache with MD5 checksums).
4.  Synchronizes user config with schema via `sync_config()` (adds missing keys).
5.  Reconciles enabled/disabled lists via `reconcile_lists()` (adds new items to enabled if they're defaults).
6.  Syncs module settings via `sync_module_settings()` (prunes deleted modules, merges enabled module defaults).
7.  Saves the updated config back to disk.
8.  On subsequent loads, the cache is checked for freshness; stale entries are refreshed by importing enabled modules.
