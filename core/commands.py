import core
import textwrap
import asyncio
import shlex

CMD_PREFIX = core.config.get("core").get("cmd_prefix", "/")

BUILTIN_COMMANDS = {
    "core": {
        "prompt": "show system prompt",
        "prompt <module name>": "show system prompt for that module",
        "history": "show full chat history",
        "context": "show full context being sent to AI",
        "status": "show status info",
        "config": "Explore, view, and set config settings",
        "restart": "restarts the server",
        "stop": "stops the AI in it's tracks",
        "connect": "attempt to connect to the API",
        "disconnect": "disconnect from the API",
        "reconnect": "reconnect to the API",
        "ping": "test command that echoes \"Pong!\"",
        "help": "this help",
    },
    "chats": {
        "new": "starts a new chat",
        "clear": "clear current chat history",
        "chats": "list previous chats",
        "chat <ID>": "load a chat by its ID",
        "chat rename <name>": "rename current chat",
        "chat category <category>": "put chat in that category",
    },
    "modules": {
        "modules": "list modules",
        "module": "enable/disable a module by name",
        "tools": "list tools available to the AI"
    }
}

# auto add cmd prefix to the builtin commands
BUILTIN_COMMANDS = {
    module: {f"{CMD_PREFIX}{cmd}": desc for cmd, desc in commands.items()}
    for module, commands in BUILTIN_COMMANDS.items()
}

def get_commands(modules_dict: dict = None):
    """
    Return all available commands as a list of dicts (key=command, value=description)
    """
    commands = {}
    commands.update(BUILTIN_COMMANDS)

    if modules_dict:
        for module_name, instance in modules_dict.items():
            module_cmds = {}

            # Scan the global registry for commands belonging to this instance's class
            for cmd_name, handlers in core.module._command_registry.items():
                for registered_cls, method in handlers:
                    if isinstance(instance, registered_cls):
                        desc = method._command_description

                        # Handle dictionary help for subcommands
                        if isinstance(desc, dict):
                            for subcmd, subdesc in desc.items():
                                # Concatenate base command with subcommand key
                                # e.g. "identity" + " " + "set <text>" -> "identity set <text>"
                                full_cmd = f"{cmd_name} {subcmd}".strip()
                                module_cmds[f"{CMD_PREFIX}{full_cmd}"] = subdesc
                        else:
                            # Handle standard string description
                            module_cmds[f"{CMD_PREFIX}{cmd_name}"] = desc


            # If this module has any commands, add them to the output
            if module_cmds and module_name:
                if module_name not in commands:
                    commands[module_name] = {}

                # we use update() so that core command categories can be extended by modules
                commands[module_name].update(module_cmds)

    return commands

def _convert_type(value: str):
    """
    Converts string inputs from the CLI/Chat into appropriate Python types.
    """

    if value.lower() in ["true", "on"]:
        return True
    if value.lower() in ["false", "off"]:
        return False

    # Try integer conversion
    try:
        # We use a check to see if it's a valid integer representation
        if value.lstrip('-').isdigit():
            return int(value)
    except ValueError:
        pass

    # Try float conversion
    try:
        return float(value)
    except ValueError:
        pass

    # Default to string
    return value

async def _set_config_value(path: list, value: str, manager=None):
    """
    Sets a configuration value at a nested path.

    Args:
        path: A list of keys representing the nested path (e.g., ["api", "url"]).
        value: The value to set (as a string, will be type-converted).
        manager: Optional manager instance for reloading modules after settings change.
    """
    if not path:
        return "error: Path cannot be empty"

    typed_value = _convert_type(value.strip())

    try:
        # Access the StorageDict instance from the config module
        target = core.config.config
        if target is None:
            return "error: Configuration is not loaded. Please restart or wait for system initialization."

        # Traverse the dictionary following the path
        current = target
        for i, key in enumerate(path[:-1]):
            if not isinstance(current, dict):
                return f"Error: Path {path} is invalid. '{key}' is not a dictionary."
            current = current[key]

        # Check if the target key already exists and is a dictionary
        # This prevents overwriting a settings group with a single value
        if path[-1] in current and isinstance(current[path[-1]], dict):
            return "That's a settings group! Check which settings are in it instead of trying to set its value"

        # Set the final value
        if not isinstance(current, dict):
            return f"Error: Path {path} is invalid. The parent of '{path[-1]}' is not a dictionary."
        
        current[path[-1]] = typed_value

        # Persist changes to the YAML file
        core.config.config.save()

        # Check if this is a module setting change and reload the module
        module_name = None
        if manager and len(path) >= 3 and path[0] == "modules":
            module_name = path[2]

        if module_name:
            try:
                await manager.reload_module(module_name)
                return f"Config updated: {' -> '.join(path)} = {typed_value}"
            except Exception as e:
                return f"Config updated: {' -> '.join(path)} = {typed_value}\nWarning: Failed to reload module '{module_name}': {e}"

        return f"Config updated: {' -> '.join(path)} = {typed_value}"
    except Exception as e:
        return f"Failed to update config: {e}"

def _get_config_value(path: list):
    """
    Gets a configuration value from a nested path.

    Args:
        path: A list of keys representing the nested path (e.g., ["api", "url"]).
    """
    try:
        # Use the shorthand get from the config module which handles the StorageDict
        if not path:
            return "Available settings: "+", ".join(core.config.config.keys())
        root_item = core.config.get(path[0])
        if root_item == None:
            return f"{path[0]} is not a valid settings category"

        sub_item = root_item
        last_path_key = path[0]
        for path_key in path[1:]:
            sub_item = sub_item.get(path_key)
            if sub_item == None:
                return f"{path_key} is not a valid setting"
            last_path_key = path_key

        if isinstance(sub_item, dict):
            # NEW LOGIC: If we are looking at a specific module/channel/user_module's settings
            # path format: [section, 'settings', name]
            if len(path) == 3 and path[1] == "settings":
                section = path[0] # 'modules', 'channels', or 'user_modules'
                name = path[2]    # the module/channel name
                
                structure = core.config.get_module_structure()
                if name in structure:
                    mod_info = structure[name]
                    schema = mod_info["settings"]
                    lines = []
                    for s_name, s_schema in schema.items():
                        desc = ""
                        if isinstance(s_schema, dict):
                            desc = s_schema.get("description", "")
                            unsafe = s_schema.get("unsafe", False)

                            if unsafe:
                                desc += "\n  !! UNSAFE SETTING - ENABLE AT YOUR OWN RISK !!"
                            if "options" in s_schema and isinstance(s_schema["options"], dict):
                                opts = s_schema["options"]
                                opt_list = [f"{k}: {v}" for k, v in opts.items()]
                                if opt_list:
                                    desc += "\nYou can set this to one of:\n- " + "\n- ".join(opt_list)
                        
                        if desc:
                            lines.append(f"{s_name}: {desc}")
                        else:
                            lines.append(f"{s_name}")
                    
                    if lines:
                        return "\n\n".join(lines)
                    else:
                        return f"No settings found for {name}"

            # Original behavior
            sub_keys = ", ".join(sub_item.keys())
            sub_item = f"Available settings in {last_path_key}: {sub_keys}"

        return sub_item
    except Exception as e:
        return f"Error retrieving config: {e}"

class Commands:
    # delete these after they are shown to the user once
    GHOST = ("help", "new", "clear", "context", "prompt", "tools", "stop")
    PUBLIC_COMMANDS = ("new", "clear", "status", "stop")

    def __init__(self, channel):
        self.channel = channel

    async def _get_help(self):
        # Get automated command help grouped by module
        output = []

        cmd_help = core.commands.get_commands(self.channel.manager.modules)
        if cmd_help:
            for category, commands in cmd_help.items():
                output.append(f"== {category} ==")
                for command, desc in commands.items():
                    output.append(f"{command:<30} {desc}")
                output.append("") # newline

        return "\n".join(output)

    def _check_if_temporary(self, cmd: str):
        # set ghost flag on temporary commands so that they emit as ghost messages (invisible to the AI)
        if (
            # manually marked as ghost
            cmd in self.GHOST
            or
            # marked as ghost within the decorator (@core.module.command(name, send_to_ai=False)
            core.module.command_is_temporary(cmd)
            or
            # just make them all ghosted if tool usage is turned off
            not core.config.get("model").get("use_tools")
        ):
            return True
        return False

    async def _extract_cmd(self, message_text):
        message_content = message_text.strip()
        cmd_prefix = core.config.get("core").get("cmd_prefix", "/")
        
        if not message_content.startswith(cmd_prefix):
            return None, None, []
        
        try:
            cmd = shlex.split(message_content[len(cmd_prefix):])
            args = cmd[1:]
            return (cmd_prefix, cmd, args)
        except ValueError as e:
            return None, None, []

    async def process_input(self, content: str, authorized=False):
        """wrapper around the real _process_input, handles insertion of context"""
        cmd_prefix, cmd, args = await self._extract_cmd(content)

        if cmd_prefix is None or cmd is None:
            return False

        if len(cmd) <= 0:
            raise core.exceptions.UnauthorizedException("Command was somehow zero length. Aborting for security reasons.")

        if not authorized and cmd[0] not in self.PUBLIC_COMMANDS:
            raise core.exceptions.UnauthorizedException("You are not authorized to run admin commands.")

        # treat message as normal if it's not a command
        if cmd is None or not content.startswith(cmd_prefix):
            return False

        use_temporary = self._check_if_temporary(cmd[0])

        # insert /command into context so that it gets properly tracked and displayed
        args_display = ""
        if args:
            args_display += " "
            args_display += " ".join(args)
        await self.channel.context.chat.messages.add({"role": "user", "content": f"{cmd_prefix}{cmd[0]}{args_display}"}, cmd=True, ghost=use_temporary)

        result = await self._process_input(content)

        # insert command result into context, flagging as temporary if needed
        await self.channel.context.chat.messages.add({"role": "assistant", "content": f"{result}"}, cmd=True, ghost=use_temporary)

        return result

    async def _process_input(self, content: str):
        """processes user input and detects special commands that control opticlaw"""

        cmd_prefix, cmd, args = await self._extract_cmd(content)

        match cmd[0]:
            # case "undo":
            #     self.channel.manager.API._messages.pop()
            #     self.channel.manager.API._messages.pop()
            #     self._last_cmd_was_temporary = True
            #     return "Turn undone."
            case "help":
                return await self._get_help()
            case "ping":
                return "pong!"
            case "new":
                """starts a new session"""
                result = await self.channel.context.chat.new()
                if result:
                    return "New session started."
                else:
                    return "Failed to start new session"
            case "clear":
                """clear chat history"""

                result = await self.channel.context.chat.clear()
                if result:
                    return "Chat history wiped."
                else:
                    return "Failed to wipe chat history"
            case "chats":
                # if i overwrite the list builtin, it leads to really bad stuff

                """list chats"""

                chats = self.channel.context.chat.get_all()
                if not chats:
                    return self.result("No saved chats found.", False)

                result = f"Saved chats for {self.channel.name}:\n"
                for conv in chats[-20:]: # only the last 20 to avoid overwhelming the AI
                    result += f"- [{conv.get('id')}] {conv.get('title', 'Untitled')[:50]}\n"

                return result

            case "chat":
                """load chat using its ID"""
                if not args:
                    chat = self.channel.context.chat

                    chat_tags_str = "None"
                    if chat.get('tags'):
                        chat_tags_str = ", ".join(chat.get('tags'))
                    chat_data = self.channel.context.chat.get("metadata") or {}
                    if chat_data:
                        chat_data_str = "\n"
                        chat_data_str += "\n".join([f"  {key}: {value}" for key, value in chat_data.items()])
                    else:
                        chat_data_str = "None"

                    return f"== chat info ==\ntitle: {chat.get('title')}\ncategory: {chat.get('category')}\ntags: {chat_tags_str}\nmetadata: {chat_data_str}"
                match args[0].lower().strip():
                    case "rename":
                        newname = " ".join(args[1:])
                        result = await self.channel.context.chat.set("title", newname)
                        if not result:
                            return "rename failed"
                        return f"chat renamed to {newname}"
                    case "category":
                        newcat = " ".join(args[1:])
                        result = await self.channel.context.chat.set("category", newcat)
                        if not result:
                            return "setting category failed"
                        return f"chat categorised into {newcat}"
                    case _:
                        result = await self.channel.context.chat.load(args[0])
                        if not result:
                            return "failed to load chat"
                        return "chat loaded"

            case "connect":
                if self.channel.manager.API.connected:
                    return "Already connected."

                result = await self.channel.manager.API.connect()
                if isinstance(result, core.api.APIError):
                    return f"Error while connecting: {result}"

                return "Connected!"
            case "reconnect":
                result = await self.channel.manager.API.reconnect()

                if isinstance(result, core.api.APIError):
                    return f"Error while reconnecting: {result}"

                return "Reconnected"
            case "disconnect":
                await self.channel.manager.API.disconnect()
                return "Disconnected from API"
            case "status":
                status = self.channel.manager.API.get_status()
                lines = ["== API Status =="]

                lines.append(f"Connected: {'Yes' if status['connected'] else 'No'}")
                lines.append(f"Model: {status['model'] or 'Not set'}")
                lines.append(f"URL: {status['url']}")

                if self.channel.manager.API.connected:
                    lines.append("")
                    lines.append("== Context Size ==")
                    context_size = await self.channel.context.get_size()
                    ctx_string = ""
                    for key, value in context_size.items():
                        ctx_string += f"{key}: {value}\n"
                    lines.append(ctx_string)

                return "\n".join(lines)
            case "modules":
                modules_str = "\n".join(core.config.get("modules").get("enabled"))
                modules_disabled_str = "\n".join(core.config.get("modules").get("disabled"))
                modules_loaded_str = "\n".join(self.channel.manager.modules.keys())

                return f"== loaded ==\n{modules_loaded_str}\n\n== disabled ==\n{modules_disabled_str}\n"
            case "module":
                if not args:
                    return "please provide a name of the module to toggle"

                module_name = args[0]
                all_modules = core.config.get("modules", "enabled", default=[]) + core.config.get("modules", "disabled", default=[]) + core.config.get("user_modules", "enabled", default=[]) + core.config.get("user_modules", "disabled", default=[])

                if module_name not in all_modules:
                    return "module with that name doesn't exist"

                await self.channel.manager.toggle_module(module_name)
                return "module toggled"
            case "channel":
                if not args:
                    return "please provide a name of the channel to toggle"

                channel_name = args[0]
                all_channels = core.channel.get_available_channels()

                if channel_name not in all_channels:
                    return "channel with that name doesn't exist"

                await self.channel.manager.toggle_channel(channel_name)
                return "channel toggled"
            case "tools":
                if not core.config.get("model").get("use_tools", False):
                    return "tools are turned off"

                tool_map = {}
                for tool in self.channel.manager.tools:
                    tool_name = tool.get("function").get("name")
                    module_name = tool_name.split("_")[0]

                    if module_name not in tool_map.keys():
                        tool_map[module_name] = []

                    tool_map[module_name].append(tool_name)

                tool_map_display = []
                tool_map_display.append("enabled tools:")
                for module_name, tools in tool_map.items():
                    tools_display = "\n".join(tools)
                    tool_map_display.append(f"== {module_name} ==\n{tools_display}")

                return "\n\n".join(tool_map_display)
            case "config":
                if not args:
                    return str(_get_config_value([]))

                # Determine if it's a SET or a GET using type detection during traversal
                is_set = False
                path_to_use = args
                value_to_use = None

                if len(args) >= 1:
                    if args[0].strip() in ("modules", "user_modules", "channels"):
                        # automatically alias to `/config modules settings`
                        args.insert(1, "settings")

                current = core.config.config
                for i, arg in enumerate(args):
                    if arg in current:
                        if isinstance(current[arg], dict):
                            # It's a group. Continue traversing.
                            current = current[arg]
                        else:
                            # It's a value.
                            if i < len(args) - 1:
                                # We hit a value but there are more args.
                                # This means the user is trying to SET the value of this key.
                                is_set = True
                                path_to_use = args[:i+1]
                                value_to_use = " ".join(args[i+1:])
                                break
                            else:
                                # We reached the end of args and it's a value. This is a GET.
                                break
                    else:
                        # Key not found. Return an error instead of allowing a new key.
                        return f"setting '{key}' does not exist at that path."
                
                if is_set:
                    return await _set_config_value(path_to_use, value_to_use, self.channel.manager)
                else:
                    return str(_get_config_value(path_to_use))

            case "history":
                """shows current context window"""

                if not core.config.get("api").get("context_window", True):
                    return "CONTEXT DISABLED"

                show_system_prompt = True if len(args) and args[0] == "full" else False

                context = await self.channel.context.get(system_prompt=show_system_prompt)
                if not context:
                    return "BLANK"

                context_display = []

                for message in context:
                    if message.get("role") in ("tool", "developer"): continue

                    message_formatted = self.channel.format_message(message)

                    content = message_formatted.get("content")
                    context_display.append(f"== {message_formatted.get('role')} ==\n{content}")

                context_display.append("---")

                disabled_prompts = core.config.get("modules").get("disabled_prompts")
                if disabled_prompts:
                    disabled_prompts_str = "\n".join([mod_name for mod_name in disabled_prompts])
                    context_display.append(f"== disabled prompts ==\n{disabled_prompts_str}")

                ctx_string = ""
                context_size = await self.channel.context.get_size()
                for key, value in context_size.items():
                    ctx_string += f"{key}: {value}\n"
                context_display.append(f"== context size ==\n{ctx_string}")

                return "\n\n".join(context_display)

            case "context":
                context = await self.channel.context.get(system_prompt=True)
                import json
                return json.dumps(context, indent=2)

            case "prompt":
                """shows only the system prompt"""

                if not core.config.get("api").get("context_window", True):
                    return "CONTEXT DISABLED"

                if not len(args):
                    _sysprompt = await self.channel.manager.get_system_prompt()
                    if not _sysprompt:
                        _sysprompt = "BLANK"
                    sysprompt = f"=== system prompt ===\n{_sysprompt}"
                    disabled_prompts = core.config.get("modules").get("disabled_prompts")
                    if disabled_prompts:
                        sysprompt += "\n\n=== disabled prompts ===\n"
                        sysprompt += "\n".join([mod_name for mod_name in disabled_prompts])
                    endprompt = await self.channel.manager.get_end_prompt()
                    if endprompt:
                        sysprompt += f"\n\n=== end prompts ===\n{endprompt}"

                    return sysprompt if sysprompt else "BLANK"
                else:
                    module_name = args[0].strip().replace(" ", "_")
                    module_obj = self.channel.manager.modules.get(module_name, None)
                    if module_obj:
                        if hasattr(module_obj, "on_system_prompt"):
                            return await module_obj.on_system_prompt() or "BLANK"
                        else:
                            return "module does not have a system prompt defined"

                    return "module not found"

            case "prompts":
                """show which prompts are active"""

                enabled = []
                no_prompt = []
                disabled = []
                for module_name, module in self.channel.manager.modules.items():
                    has_sysprompt = True if await module.on_system_prompt() else False

                    if has_sysprompt:
                        enabled.append(module_name)
                    else:
                        disabled.append(module_name)

                enabled_str = "\n".join(enabled)
                return f"== modules with active prompts ==\n{enabled_str}"
            case "restart":
                await self.channel.manager.restart()
                return "restarting server"
            case "stop":
                await self.channel.manager.API.cancel()
                return "stopped!"
            case _:
                # handle module commands by using their decorated methods

                if self.channel.manager.modules:
                    cmd_lookup = cmd[0].lower().strip()

                    # See if this command exists in the command registry
                    if cmd_lookup in core.module._command_registry:
                        for registered_cls, method in core.module._command_registry[cmd_lookup]:
                            # Find the instance of this class in the loaded modules
                            for module_inst in self.channel.manager.modules.values():
                                if isinstance(module_inst, registered_cls):
                                    # Bind the method to the instance and call it
                                    bound_method = method.__get__(module_inst, registered_cls)
                                    try:
                                        return await bound_method(cmd[1:])
                                    except Exception as e:
                                        self.channel.log_error("error while executing command", e)

                return "no such command! check /help"
