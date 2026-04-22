import core
import textwrap
import asyncio

def get_commands_help(modules_dict):
    """
    Builds a help string grouped by module instance.
    """
    output = []
    cmd_prefix = core.config.get("cmd_prefix", "/")

    for module_name, instance in modules_dict.items():
        module_cmds = []

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
                            module_cmds.append(f"{cmd_prefix}{full_cmd:<20} {subdesc}")
                    else:
                        # Handle standard string description
                        module_cmds.append(f"{cmd_prefix}{cmd_name:<20} {desc}")

                    break # Only take the first matching handler

        # If this module has any commands, add them to the output
        if module_cmds:
            # Sort alphabetically
            module_cmds.sort()

            # Retrieve class docstring
            doc = instance.__class__.__doc__

            if doc:
                clean_doc = textwrap.dedent(doc).strip()
                section = f"== {module_name} ==\n{clean_doc}\n\n" + "\n".join(module_cmds)
            else:
                section = f"== {module_name} ==\n" + "\n".join(module_cmds)

            output.append(section)

    return "\n\n".join(output)

def _convert_type(value: str):
    """
    Converts string inputs from the CLI/Chat into appropriate Python types.
    """
    if value.lower() == "true":
        return True
    if value.lower() == "false":
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

def _set_config_value(path: list, value: str):
    """
    Sets a configuration value at a nested path.

    Args:
        path: A list of keys representing the nested path (e.g., ["api", "url"]).
        value: The value to set (as a string, will be type-converted).
    """
    if not path:
        return "error: Path cannot be empty"

    typed_value = _convert_type(value)

    try:
        # Access the StorageDict instance from the config module
        target = core.config.config
        if target is None:
            return "error: Configuration is not loaded. Please restart or wait for system initialization."

        # Traverse the dictionary following the path
        current = target
        for i, key in enumerate(path[:-1]):
            # If the key doesn't exist or the current level isn't a dictionary,
            # create a new dictionary to allow for deep nesting.
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]

        # Set the final value
        current[path[-1]] = typed_value

        # Persist changes to the YAML file
        core.config.config.save()

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
            sub_keys = ", ".join(sub_item.keys())
            sub_item = f"Available settings in {last_path_key}: {sub_keys}"

        return sub_item
    except Exception as e:
        return f"Error retrieving config: {e}"

class Commands:
    # delete these after they are shown to the user once
    TEMPORARY = ("context", "prompt", "tools", "stop")

    def __init__(self, channel):
        self.channel = channel

    async def _get_help(self):
        output = []

        help_text = """
== built in commands ==
chats:
/new                        starts a new chat
/clear                      clear current chat history
/chats                      list previous chats
/chat <ID>                  load a chat by its ID
/chat rename <name>         rename current chat
/chat category <category>   put chat in that category

modules:
/modules                    list modules
/module                     enable/disable a module by name
/tools                      list tools available to the AI

core:
/prompt                     show system prompt
/prompt <module name>       show system prompt for that module
/history                    show full chat history
/context full               show full context being sent to AI
/context raw                show full context as raw JSON
/status                     show status info
/config set <path> <value>  Example: /config set api url http://localhost:5001/v1
/config get <path>          Example: /config get api url
/restart                    restarts the server
/stop                       stops the AI in it's tracks
/connect                    attempt to connect to the API
/disconnect                 disconnect from the API
/reconnect                  reconnect to the API
/ping                       test command that echoes "Pong!"
/help                       this help
        """.strip()

        output.append(help_text)

        if self.channel.manager.modules:
            # Get automated command help grouped by module
            cmd_help = core.commands.get_commands_help(self.channel.manager.modules)
            if cmd_help:
                output.append(cmd_help)

        return "\n\n".join(output)

    def _check_if_temporary(self, cmd: str):
        # set temporary flag on temporary commands so that they disappear upon the next user message
        if (
            # manually marked as temporary
            cmd in self.TEMPORARY
            or
            # marked as temporary within the decorator (@core.module.command(name, temporary=True)
            core.module.command_is_temporary(cmd)
            or
            # just make them all temporary if tool usage is turned off
            not core.config.get("model").get("use_tools")
        ):
            return True
        return False

    async def _extract_cmd(self, message_text):
        message_content = message_text.strip()
        cmd_prefix = core.config.get("cmd_prefix", "/")
        cmd_prefix_index = message_content.lower().find(cmd_prefix.lower())+len(cmd_prefix)

        cmd = message_content[cmd_prefix_index:].split()
        args = cmd[1:]

        return (cmd_prefix, cmd, args)

    async def process_input(self, message: dict):
        """wrapper around the real _process_input, handles insertion of context"""
        content = self.channel._extract_content(message)
        cmd_prefix, cmd, args = await self._extract_cmd(content)

        # treat message as normal if it's not a command
        if cmd is None or not content.startswith(cmd_prefix):
            return False

        use_temporary = self._check_if_temporary(cmd[0])

        # insert /command into context so that it gets properly tracked and displayed
        args_display = ""
        if args:
            args_display += " "
            args_display += " ".join(args)
        await self.channel.context.chat.add({"role": "user", "content": f"{cmd_prefix}{cmd[0]}{args_display}"}, temporary=use_temporary)

        result = await self._process_input(message)

        # insert command result into context, flagging as temporary if needed
        await self.channel.context.chat.add({"role": "assistant", "content": f"[Command Output]:\n{result}"}, temporary=use_temporary)

        return result

    async def _process_input(self, message: dict):
        """processes user input and detects special commands that control opticlaw"""

        cmd_prefix, cmd, args = await self._extract_cmd(self.channel._extract_content(message))

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

                chats = await self.channel.context.chat.get_all()
                if not chats:
                    return self.result("No saved chats found.", False)

                result = f"Saved chats for {self.channel.name}:\n"
                for conv in chats[-20:]: # only the last 20 to avoid overwhelming the AI
                    result += f"- [{conv.get('id')}] {conv.get('title', 'Untitled')[:50]}\n"

                return result

    # @core.module.command("chat", temporary=True, help={
    #     "": "show information about current chat",
    #     "<ID>": "load chat using its ID",
    #     "rename <new_name>": "rename chat to <new_name>",
    #     "category <category>": "put chat in category <category>"
    # })
    # async def load(self, args: list):
            case "chat":
                """load chat using its ID"""
                if not args:
                    chat_title = await self.channel.context.chat.get_title()
                    chat_category = await self.channel.context.chat.get_category()
                    chat_tags = await self.channel.context.chat.get_tags()
                    chat_tags_str = "None"
                    if chat_tags:
                        chat_tags_str = ", ".join(chat_tags)
                    chat_data = await self.channel.context.chat.get_data() or {}
                    if chat_data:
                        chat_data_str = "\n"
                        chat_data_str += "\n".join([f"  {key}: {value}" for key, value in chat_data.items()])
                    else:
                        chat_data_str = "None"

                    return f"== chat info ==\ntitle: {chat_title}\ncategory: {chat_category}\ntags: {chat_tags_str}\ndata: {chat_data_str}"
                match args[0].lower().strip():
                    case "rename":
                        newname = " ".join(args[1:])
                        result = await self.channel.context.chat.set_title(newname)
                        if not result:
                            return "rename failed"
                        return f"chat renamed to {newname}"
                    case "category":
                        newcat = " ".join(args[1:])
                        result = await self.channel.context.chat.set_category(newcat)
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
                if not result:
                    return f"error connecting to API: {self.channel.manager.API.get_last_error()}"

                return "✓ Connected!"
            case "reconnect":
                    result = await self.channel.manager.reconnect_api()

                    if result["success"]:
                        return ["✓ ", result["message"]]
                    else:
                        response = [f"✗ Connection failed: {result['error']}"]
                        if "action" in result:
                            response.append(f"\n{result['action']}")
                        return response
            case "disconnect":
                await self.channel.manager.API.disconnect()
                return ["✓ Disconnected from API"]
            case "status":
                status = self.channel.manager.get_api_status()
                lines = ["== API Status =="]

                lines.append(f"Connected: {'Yes' if status['connected'] else 'No'}")
                lines.append(f"Model: {status['model'] or 'Not set'}")
                lines.append(f"URL configured: {'Yes' if status['url_configured'] else 'No'}")
                lines.append(f"Key configured: {'Yes' if status['key_configured'] else 'No'}")

                if status['error']:
                    lines.append(f"Last error: {status['error']}")

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

                import modules
                module_manager = modules.modules.Modules(self.channel.manager)
                found = False
                for module in modules.get_all(respect_config=False):
                    module_name = core.modules.get_name(module)
                    if args[0].lower().strip() == module_name:
                        found = True

                if not found:
                    return "module with that name doesn't exist"

                await module_manager.toggle(args[0])
                await self.channel.announce("module toggled")
                await self.channel.announce("restarting to apply module change..", "error")
                await asyncio.sleep(0.2)
                await self.channel.manager.restart()
                return
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
                    return "Usage: /config <set|get> <path> [value]"

                subcommand = args[0].lower()

                if subcommand == "set":
                    # Expected: ['set', 'key1', 'key2', 'value']
                    if len(args) < 3:
                        return "Usage: /config set <key1> <key2> ... <value>"

                    path = args[1:-1]
                    value = args[-1]
                    return str(_set_config_value(path, value))

                elif subcommand == "get":
                    # Expected: ['get', 'key1', 'key2']
                    if len(args) < 2:
                        return "Usage: /config get <key1> <key2> ..."

                    path = args[1:]
                    return str(_get_config_value(path))

                else:
                    return f"Unknown subcommand '{subcommand}'. Use 'set' or 'get'."

            case "context":
                """shows current context window"""

                if not core.config.get("api").get("context_window", True):
                    return "CONTEXT DISABLED"

                show_system_prompt = True if len(args) and args[0] == "full" else False

                context = await self.channel.context.get(system_prompt=show_system_prompt)
                if not context:
                    return "BLANK"

                if len(args) and args[0] == "raw":
                    import json
                    return json.dumps(context, indent=2)

                context_display = []

                for message in context:
                    content = message.get("content")
                    if not content:
                        if message.get("tool_calls"):
                            content = str(message.get("tool_calls"))

                    context_display.append(f"== {message.get('role')} ==\n{content}")

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
                    module_obj = self.manager.modules.get(module_name, None)
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
                return "restarting.."
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
                                        return f"error while executing command: {e}"

                return "no such command! check /help"
