# Core: The Module System (`core.Module`)

OpenLumara is built on a highly extensible plugin architecture. The `Module` class is the base for all additional functionality, allowing developers to easily inject new capabilities into the AI agent.

## Module Architecture

Every module is a Python class that inherits from `core.Module`. Modules are loaded dynamically by the `Manager` and can interact with the rest of the system through the `Manager` and the active `Channel`.

## Key Capabilities

### 1. Prompt Injection
Modules can influence the AI's behavior by injecting text into the context window at specific points:
- **`on_system_prompt()`**: Adds content to the very beginning of the system prompt. This is ideal for defining identity, rules, or framework awareness.
- **`on_end_prompt()`**: Adds content to the end of the conversation history (just before the next user message). This is perfect for dynamic information like the current time or date, as it doesn't require reprocessing the entire history.

### 2. Tool Provisioning
Modules can expose Python functions as "tools" that the AI can call.
- Any method in a module can be converted into a tool.
- The `Manager` uses inspection to automatically generate the JSON schema required for OpenAI-compatible function calling.
- Docstrings are used to provide instructions to the AI about what the tool does and what its arguments are.

### 3. Event Hooks
Modules can react to events happening within the system:
- **`on_ready()`**: Triggered once when the module is successfully loaded.
- **`on_background()`**: Runs a continuous background task (e.g., a scheduler or a monitor).
- **`on_user_message(content)`**: Triggered whenever the user sends a message.
- **`on_assistant_message(content)`**: Triggered whenever the AI sends a response.

### 4. Command System
Modules can register custom commands that bypass the AI entirely.
- Using the `@core.module.command(name="my_cmd")` decorator, a module can define a command.
- Commands are triggered by the user via the configured command prefix (e.g., `/my_cmd`).

## Implementation Example

```python
# You must ALWAYS import core at the very top of the file
import core

class MyAwesomeModule(core.module.Module):
    """
    A sample module demonstrating core features.
    This module docstring shows up in the WebUI!
    """
    settings = {
        "enable_system_prompt": {
            "description": "Whether to enable the awesome injection into the system prompt!",
            "default": False
        },
        "sysprompt_style": {
            "type": "select",
            "description": "What system prompt to inject",
            "default": "standard",
            "options": {
                "standard": "Just your run-of-the-mill system prompt",
                "uwu": "Makes your AI say uwu all the time!",
                "nag": "Makes your AI nag you a lot"
            }
        },
        "allow_ping": {
            "description": "Whether to allow the AI to use the ping tool",
            "default": True
        }
    }

    async def on_ready(self):
        await self.manager.channel.push("Awesome Module is online!")
        
        if not self.config.get("allow_ping"):
            # disabled_tools is defined in core.module.Module and tells the framework to disable that tool
            self.disabled_tools.append("ping")

    async def on_system_prompt(self):
        match self.config.get("sysprompt_style"):
            case "standard":
                return "You are an expert in everything related to Awesome Module."
            case "uwu":
                return "You MUST say uwu a lot"
            case "nag":
                return "Nag the user about their taxes"
            case _:
                return None

    @core.module.command("ping", help={
        "": "Checks if the module is responsive",
        "cookie": "gives you a cookie"
    })
    async def ping_command(self, args: list):
        if not args:
            return "Pong!"
        elif len(args) >= 1 and args[1] == "cookie":
            return "heres a cookie! :3"
            
    async def ping(self, latency: int):
        """
        This is a tool the AI can use.
        Simulates a ping to the user.
        
        Args:
            latency: The latency to set for the simulated ping
        """
        if not self.config.get("allow_ping"):
            return self.result("Ping is disabled for security", success=False)
        
        return self.result(f"Pong! latency: {latency}", success=True)
```

## Module Configuration

Each module can define its own `settings` dictionary. These settings are:
1.  Defined in the module class.
2.  Persisted in the `config.yml` file.
3.  Accessible via `self.config.get("key")`

---

# Core: How modules are loaded (`core.Modules`)
The `core.modules` file provides the engine for OpenLumara's extensibility. It is responsible for dynamically discovering, importing, and identifying the various modules and channels that make up the system.

## Dynamic Discovery

Instead of hardcoding every possible module or channel, OpenLumara uses filesystem scanning to find them. This allows users to simply drop a new `.py` file into the `modules/`, `user_modules/`, or `channels/` directory, and the system will automatically pick it up on the next restart. Modules created by Lumara or by the user must be placed in the `user_modules/` directory.

The `load()` function performs the following steps:
1.  **Package Scanning**: Uses `pkgutil` to iterate through all sub-modules within a given package (like `modules/` or `channels/`).
2.  **Conditional Import**: Only imports modules that are present in the `filter` list (e.g., only the modules enabled in `config.yml`).
3.  **Class Inspection**: Once a module is imported, it scans the module for any classes that inherit from a specified `base_class` (like `core.module.Module` or `core.channel.Channel`).
4.  **Filtering**: Ensures that only valid, relevant classes are returned to the `Manager`.

## Naming Convention

To ensure consistency across the framework, OpenLumara automatically converts Pythonic `CamelCase` class names into `snake_case` names. This is used for:
- Identifying modules in the configuration file.
- Mapping module names to tool names.
- Creating a unified internal registry.

**Example**:
- Class: `LifeOrganizer` $\rightarrow$ Module Name: `life_organizer`
- Class: `TelegramChannel` $\rightarrow$ Channel Name: `telegram_channel`

## Key Functions

| Function | Description |
| :--- | :--- |
| `load(package, base_class, filter, reload)` | The core engine for discovering and importing classes from a package. |
| `get_name(obj)` | Converts a class name into its `snake_case` identifier. |

## Non-Agentic Modules

The `modules.nonagentic` tuple contains a list of module names that are considered "non-agentic." These modules (such as `characters` or `time`) are special because their prompts are injected into the context window even when the AI's "tool use" capability is turned off. This ensures that essential framework awareness is always present.

