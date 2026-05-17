# Core: The Command System (`core.Commands`)

The `Commands` class is responsible for intercepting user input in a channel, identifying if it is a command (e.g., starting with `/`), and executing the appropriate logic. This system allows users to bypass the AI to control the framework directly.

## Command Types

OpenLumara distinguishes between two main types of commands:

1.  **Built-in Commands**: These are hardcoded into the `Commands` class and provide fundamental control over the system (e.g., `/restart`, `/help`, `/config`, `/status`).
2.  **Module Commands**: These are dynamically discovered from the loaded modules. Developers can register custom commands using the `@core.module.command` decorator.

## Command Execution Flow

1.  **Input Interception**: When a message is sent to a channel, the `Channel` passes it to `Commands.process_input()`.
2.  **Parsing**: The input is parsed to extract the command name and its arguments.
3.  **Temporary/Ghost Flagging**: The system checks if the command is "temporary" (meaning it shouldn't be sent to the AI's context). This is determined by:
    - Whether the command is in the hardcoded `GHOST` list.
    - Whether the module decorator marked it as `send_to_ai=False`.
    - Whether tool usage is currently disabled.
4.  **Routing**:
    - If it's a built-in command, the `match` statement executes the corresponding logic.
    - If it's a module command, the system scans the `_command_registry` to find the correct module instance and method to call.
5.  **Context Insertion**: To ensure the user can see what they did, the command and its result are added to the chat history, but they are flagged as "ghost" messages so they don't clutter the AI's context window. They can, however, be added to context if the user wants the AI to be able to respond to the commands, by setting send_to_ai to True in the command decorator.

## Key Features

### Hierarchical Configuration (`/config`)
The `/config` command allows users to modify settings at runtime. It supports nested paths (e.g., `/config api url http://localhost:5001/v1`), which are then automatically persisted to the `config.yml` file.

### Dynamic Module Help
The `/help` command is context-aware. It doesn't just show a list of built-in commands; it also queries all loaded modules to display their custom registered commands, grouped by module.

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

## Built-in Command Examples

| Command | Description |
| :--- | :--- |
| `/help` | Shows all available built-in and module commands. |
| `/status` | Displays the current API connection status and context size. |
| `/config set <path> <value>` | Updates a configuration setting. |
| `/module <name>` | Toggles a module on or off (requires a restart). |
| `/restart` | Restarts the entire OpenLumara server. |
| `/chat <ID>` | Loads a specific chat from history. |
| `/new` | Starts a completely new chat session. |
