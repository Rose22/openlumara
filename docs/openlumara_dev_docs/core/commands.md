# Core: The Command System (`core.Commands`)

The `Commands` class is responsible for intercepting user input in a channel, identifying if it is a command (e.g., starting with `/`), and executing the appropriate logic. This system allows users to bypass the AI to control the framework directly.

## Command Types

OpenLumara distinguishes between two main types of commands:

1.  **Built-in Commands**: These are hardcoded into the `Commands` class and provide fundamental control over the system (e.g., `/restart`, `/help`, `/config`, `/status`).
2.  **Module Commands**: These are dynamically discovered from the loaded modules. Developers can register custom commands using the `@core.module.command` decorator.

## Command Execution Flow

1.  **Input Interception**: When a message is sent to a channel, the `Channel` passes it to `Commands.process_input()`.
2.  **Parsing**: The input is parsed to extract the command name and its arguments using `shlex.split()`. The command prefix is read from `config.core.cmd_prefix` (default `/`).
3.  **Authorization Check**: Non-public commands require authorization. Only commands in `PUBLIC_COMMANDS` (`new`, `clear`, `status`, `stop`) are accessible without authorization. Raises `UnauthorizedException` otherwise.
4.  **Temporary/Ghost Flagging**: The system checks if the command is "temporary" (meaning it shouldn't be sent to the AI's context). This is determined by:
    - Whether the command is in the hardcoded `GHOST` list (`help`, `new`, `clear`, `context`, `prompt`, `tools`, `stop`).
    - Whether the module decorator marked it as `send_to_ai=False` (via `core.module.command_is_temporary()`).
    - Whether tool usage is currently disabled (`model.use_tools` is False).
5.  **Routing**:
    - If it's a built-in command, the `match` statement executes the corresponding logic.
    - If it's a module command, the system scans the `_command_registry` to find the correct module instance and method to call.
6.  **Context Insertion**: Both the command input and its result are added to the chat history, flagged as ghost if temporary.

## Key Features

### Hierarchical Configuration (`/config`)
The `/config` command allows users to modify settings at runtime. It supports:
- **GET**: `/config api` → lists available settings in `api` section
- **GET with path**: `/config api url` → returns current value
- **SET**: `/config api url http://localhost:5001/v1` → updates the value
- **Type Conversion**: Automatically converts string inputs to appropriate Python types (booleans, integers, floats, strings).
- **Module Auto-Reload**: When a module setting is changed, the module is automatically reloaded to apply the new configuration.
- **Settings Groups**: Prevents overwriting a settings group with a single value.
- **Auto-Alias**: `/config modules settings` can be shortened to `/config modules`.

### Dynamic Module Help
The `/help` command is context-aware. It doesn't just show a list of built-in commands; it also queries all loaded modules to display their custom registered commands, grouped by module. Handled by `get_commands()` which scans `_command_registry` and matches module instances.

### Command Decorator
Developers can easily add commands to their modules using the following pattern:

```python
import core

class MyModule(core.module.Module):
    
    @core.module.command("ping", help={
        "": "Checks if the module is responsive",
        "cookie": "gives you a cookie"
    })
    async def ping_command(self, args: list):
        """The actual logic of the command"""
        
        # args is split by word using shlex.split(). index 0 is the first argument to the command, not the command name itself.
        if not args:
            return "Pong!"
        elif len(args) >= 1 and args[1] == "cookie":
            return "heres a cookie! :3"
```

## Built-in Commands

### Core Commands
| Command | Description |
| :--- | :--- |
| `/prompt` | Shows the full system prompt. |
| `/prompt <module name>` | Shows the system prompt for a specific module. |
| `/history` | Shows the full context window being sent to the AI (with system prompt). |
| `/history full` | Shows the full context including system prompt. |
| `/context` | Shows the full context as pretty-printed JSON. |
| `/status` | Displays the current API connection status, model, URL, and context size breakdown. |
| `/config` | Explore, view, and set config settings (see above). |
| `/restart` | Restarts the server. |
| `/stop` | Stops the AI mid-generation (cancels the request). |
| `/connect` | Attempts to connect to the API. |
| `/disconnect` | Disconnects from the API. |
| `/reconnect` | Reconnects to the API (shows status). |
| `/ping` | Echo test: returns "pong!". |
| `/help` | Shows all available commands. |

### Chat Commands
| Command | Description |
| :--- | :--- |
| `/new` | Starts a completely new chat session. |
| `/clear` | Clears the current chat history. |
| `/chats` | Lists the last 20 saved chats with IDs and titles. |
| `/chat <ID>` | Loads a specific chat by its ID. |
| `/chat` (no args) | Shows current chat info (title, category, tags, custom data). |
| `/chat rename <name>` | Renames the current chat. |
| `/chat category <category>` | Changes the current chat's category. |

### Module Commands
| Command | Description |
| :--- | :--- |
| `/modules` | Lists loaded, enabled, and disabled modules. |
| `/module <name>` | Toggles a module on or off (auto-restarts). |
| `/tools` | Lists all tools available to the AI, grouped by module. |

### Additional Commands
| Command | Description |
| :--- | :--- |
| `/prompts` | Shows which modules have active system prompts. |

## Helper Functions

| Function | Description |
| :--- | :--- |
| `get_commands(modules_dict)` | Returns all available commands as a dict of dicts (key=command, value=description), grouped by module. |
| `_convert_type(value)` | Converts string inputs to appropriate Python types (bool, int, float, str). |
| `_set_config_value(path, value, manager)` | Sets a config value at a nested path with auto-reload for modules. |
| `_get_config_value(path)` | Gets a config value from a nested path, with special handling for module settings display (shows descriptions, options, unsafe warnings). |

## Constants

| Constant | Description |
| :--- | :--- |
| `CMD_PREFIX` | The command prefix character (from config, default `/`). |
| `BUILTIN_COMMANDS` | Dict of built-in commands grouped by category. Auto-prefixed with `CMD_PREFIX`. |
| `GHOST` | Tuple of command names that are always temporary/ghost. |
| `PUBLIC_COMMANDS` | Tuple of command names accessible without authorization. |
