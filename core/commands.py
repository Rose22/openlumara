import core
import os
import datetime
import json
import shlex

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

def get_commands(modules_dict: dict = None):
    """
    Return all available commands as a list of dicts (key=command, value=description)
    """
    commands = {"core": {}}
    cmd_prefix = core.config.get("core").get("cmd_prefix", "/")

    # add core commands (built into Commands class) using CMD_DEFS
    for cmd_name, desc in Commands.CMD_DEFS.items():
        if desc is None:
            # spacer - insert blank line
            commands["core"][""] = ""
        elif isinstance(desc, dict):
            # subcommands - expand each one
            for subcmd, subdesc in desc.items():
                full_cmd = f"{cmd_name} {subcmd}".strip()
                commands["core"][f"{cmd_prefix}{full_cmd}"] = subdesc
        else:
            commands["core"][f"{cmd_prefix}{cmd_name}"] = desc

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
                                full_cmd = f"{cmd_name} {subcmd}".strip()
                                module_cmds[f"{cmd_prefix}{full_cmd}"] = subdesc
                        else:
                            module_cmds[f"{cmd_prefix}{cmd_name}"] = desc

            # If this module has any commands, add them to the output
            if module_cmds and module_name:
                if module_name not in commands:
                    commands[module_name] = {}
                commands[module_name].update(module_cmds)

    return commands


class Commands:
    # delete these after they are shown to the user once
    GHOST = ("help", "new", "clear", "context", "prompt", "tools", "chats", "chat")
    PUBLIC_COMMANDS = ("new", "clear", "status", "stop")
    
    # command definitions - maps command name to help text
    # use string for single command, dict for subcommands, "__SPACER__" for spacers
    CMD_DEFS = {
        # chat management
        "new": "starts a new session",
        "clear": "clears chat history",
        "chats": {
            "<page number>": "show previous chats, paginated",
        },
        "chat": {
            "": "show details about current chat",
            "<number>": "loads a chat by its number in the chats list",
            "rename <name>": "renames current chat",
            "category <category>": "puts chat in that category",
        },
        "search": "searches within your previous chats",
        "compress": "compresses your chat history",
        "export": "exports the current chat history to a file",
        "__SPACER__1": "",
        # info & content
        "prompt": {
            "": "shows system prompt",
            "<module name>": "shows the system prompt for that module",
        },
        "prompts": "shows which prompts are active",
        "context": "shows full context being sent to AI",
        "history": "shows full chat history",
        "status": "shows status info",
        "__SPACER__2": "",
        # API connection
        "connect": "attempts to connect to the API",
        "reconnect": "reconnects to the API",
        "disconnect": "disconnects from the API",
        "__SPACER__3": "",
        # module/channel management
        "modules": "lists modules",
        "module": "enables/disables a module by name",
        "channel": "toggles a channel",
        "tools": {
            "": "lists tools available to the AI",
            "search <query>": "searches the tool catalog",
            "load <name> [name2 ...]": "loads tools by exact name",
        },
        "__SPACER__4": "",
        # system
        "config": "explore, view, and set config settings",
        "restart": "restarts the server",
        "stop": "stops the AI in it's tracks",
        "__SPACER__5": "",
        # utilities
        "ping": "test command that echoes Pong!",
        "help": "shows this help",
    }
    
    # ordered list of core commands for help display
    COMMAND_ORDER = list(CMD_DEFS.keys())

    def __init__(self, channel):
        self.channel = channel

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
            cmd_full = shlex.split(message_content[len(cmd_prefix):])
            args = cmd_full[1:]

            cmd = cmd_full[0] if len(cmd_full)>0 else ""

            return (cmd_prefix, cmd, args)
        except ValueError as e:
            return None, None, []

    async def process_input(self, content: str, authorized=False):
        """wrapper around the real _process_input, handles insertion of context"""
        cmd_prefix, cmd, args = await self._extract_cmd(content)

        if cmd_prefix is None:
            return False

        # insert /command into context so that it gets properly tracked and displayed
        use_temporary = self._check_if_temporary(cmd)

        args_display = ""
        if args:
            args_display += " "
            args_display += " ".join(args)
        await self.channel.context.chat.messages.add({"role": "user", "content": f"{cmd_prefix}{cmd}{args_display}"}, cmd=True, ghost=use_temporary)

        if len(cmd) <= 0:
            raise core.exceptions.UnauthorizedException("Command was somehow zero length. Aborting for security reasons.")

        if not authorized and cmd not in self.PUBLIC_COMMANDS:
            raise core.exceptions.UnauthorizedException("You are not authorized to run admin commands.")

        # treat message as normal if it's not a command
        if cmd is None or not content.startswith(cmd_prefix):
            return False

        result = await self._process_input(content)

        # insert command result into context, flagging as temporary if needed
        await self.channel.context.chat.messages.add({"role": "assistant", "content": f"{result}"}, cmd=True, ghost=use_temporary)

        return result

    async def _process_input(self, content: str):
        """processes user input and delegates to self or module commands"""

        cmd_prefix, cmd, args = await self._extract_cmd(content)
        cmd_lookup = cmd.lower().strip()

        # first check if self (Commands) has this command
        if hasattr(self, f"cmd_{cmd_lookup}"):
            method = getattr(self, f"cmd_{cmd_lookup}")
            try:
                return await method(args)
            except Exception as e:
                self.channel.log_error(f"error executing {cmd_lookup}", e)
                return f"error: {e}"

        # fall through to module commands
        if self.channel.manager.modules:
            # See if this command exists in the command registry
            if cmd_lookup in core.module._command_registry:
                for registered_cls, method in core.module._command_registry[cmd_lookup]:
                    # Find the instance of this class in the loaded modules
                    for module_inst in self.channel.manager.modules.values():
                        if isinstance(module_inst, registered_cls):
                            # Bind the method to the instance and call it
                            bound_method = method.__get__(module_inst, registered_cls)
                            try:
                                return await bound_method(args)
                            except Exception as e:
                                self.channel.log_error("error while executing command", e)

        return "no such command! check /help"

    # ---- core commands ----

    async def cmd_help(self, args: list):
        """show help"""
        cmd_prefix = core.config.get("core").get("cmd_prefix", "/")

        output = []
        cmd_help = core.commands.get_commands(self.channel.manager.modules)
        if cmd_help:
            if args:
                module_name = args[0]
                if module_name not in cmd_help.keys():
                    return f"that's not a valid topic! check {cmd_prefix}help"
                
                for command, desc in cmd_help[module_name].items():
                    if desc == "":
                        # spacer - just add a blank line
                        output.append("")
                    else:
                        output.append(f"{command:<30} {desc}")
                return "\n".join(output)
            else:
                topics = "\n".join([f"- {topic}" for topic in cmd_help.keys()])
                return f"use {cmd_prefix}help with one of the following topics:\n{topics}\n\nexample: {cmd_prefix}help core"
        return "\n".join(output)
    
    async def cmd_ping(self, args: list):
        return "pong!"
    
    async def cmd_new(self, args: list):
        result = await self.channel.context.chat.new()
        if result:
            return "New session started."
        return "Failed to start new session"
    
    async def cmd_clear(self, args: list):
        result = await self.channel.context.chat.clear()
        if result:
            return "Chat history wiped."
        return "Failed to wipe chat history"
    
    async def cmd_chats(self, args: list):
        chats = self.channel.context.chat.get_all()
        if not chats:
            return "No saved chats found."
        
        # Parse page number from first argument
        page_size = 10
        page_number = 1
        
        if args:
            try:
                page_number = int(args[0])
                if page_number < 1:
                    page_number = 1
            except ValueError:
                pass
        
        # Sort chats by updated date (most recent first)
        sorted_chats = sorted(chats, key=lambda x: x.get('updated', ''), reverse=True)
        
        total_chats = len(sorted_chats)
        total_pages = (total_chats + page_size - 1) // page_size if total_chats > 0 else 1
        
        # Calculate page bounds
        start_idx = (page_number - 1) * page_size
        end_idx = min(start_idx + page_size, total_chats)
        
        if start_idx >= total_chats:
            page_number = max(1, total_pages)
            start_idx = (page_number - 1) * page_size
            end_idx = min(start_idx + page_size, total_chats)
        
        # Get chats for this page
        page_chats = sorted_chats[start_idx:end_idx]
        
        result = f"saved chats for {self.channel.name} (page {page_number}/{total_pages}, showing {start_idx + 1}-{end_idx} of {total_chats}):\n"
        for idx, conv in enumerate(page_chats):
            local_idx = start_idx + idx + 1  # global position
            result += f"- [{local_idx}] {conv.get('title')[:50]}\n"
        
        return result

    async def cmd_search(self, args: list):
        """Searches within your chat history"""
        query = " ".join(args)
        found = await self.channel.context.chat.search(query, 20)
        if not found:
            return "no results found"

        output = "" if not found else f"Found these chats containing '{query}':\n\n"
        for chat in found:
            date_str = datetime.datetime.fromisoformat(chat.get('updated')).strftime("%x %X")
            output += f"[{date_str}] [{chat.get('id')}] {chat.get('title')}\n"

        return output
    
    async def cmd_chat(self, args: list):
        """load or manage a chat"""
        if not args:
            chat = self.channel.context.chat
            chat_tags_str = "None"
            if chat.get('tags'):
                chat_tags_str = ", ".join(chat.get('tags'))
            chat_data = chat.get("metadata") or {}
            if chat_data:
                chat_data_str = "\n" + "\n".join([f"  {key}: {value}" for key, value in chat_data.items()])
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
                # if the argument is a number, treat it as position in the sorted list (1 = most recent)
                arg = args[0]
                try:
                    position = int(arg)
                    all_chats = self.channel.context.chat.get_all()
                    sorted_chats = sorted(all_chats, key=lambda x: x.get('updated', ''), reverse=True)
                    if position < 1 or position > len(sorted_chats):
                        return "chat with that position doesn't exist"
                    target_id = sorted_chats[position - 1]["id"]
                    result = await self.channel.context.chat.load(target_id)
                    if not result:
                        return "failed to load chat"
                    return "chat loaded"
                except ValueError:
                    result = await self.channel.context.chat.load(arg)
                    if not result:
                        return "failed to load chat"
                    return "chat loaded"
    
    async def cmd_compress(self, args: list):
        await self.channel.push("Compressing your chat history..")
        context = await self.channel.context.get()

        # use API.send() to skip all the usual convenience logic
        response = await self.channel.manager.API.send(context+[{"role": "user", "content": "Please summarize our conversation so far up to this point. The purpose is to compress current context into a summary that will be used to continue the chat."}], use_tools=False, use_thinking=False)

        if not response:
            return None

        # add special cutoff message that gets handled by the context manager
        await self.channel.context.chat.messages.add(self.channel.context.SUMMARIZATION_CUTOFF)

        # add AI's summarization
        await self.channel.context.chat.messages.add({"role": "assistant", "content": response.get("content")})

        return "chat compressed"

    async def cmd_connect(self, args: list):
        if self.channel.manager.API.connected:
            return "Already connected."
        
        result = await self.channel.manager.API.connect()
        if isinstance(result, core.api.APIError):
            return f"Error while connecting: {result}"
        return "Connected!"
    
    async def cmd_reconnect(self, args: list):
        result = await self.channel.manager.API.reconnect()
        if isinstance(result, core.api.APIError):
            return f"Error while reconnecting: {result}"
        return "Reconnected"
    
    async def cmd_disconnect(self, args: list):
        await self.channel.manager.API.disconnect()
        return "Disconnected from API"
    
    async def cmd_status(self, args: list):
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
    
    async def cmd_modules(self, args: list):
        modules_str = "\n".join(core.config.get("modules").get("enabled"))
        modules_disabled_str = "\n".join(core.config.get("modules").get("disabled"))
        modules_loaded_str = "\n".join(self.channel.manager.modules.keys())
        
        return f"== loaded ==\n{modules_loaded_str}\n\n== disabled ==\n{modules_disabled_str}\n"
    
    async def cmd_module(self, args: list):
        if not args:
            return "please provide a name of the module to toggle"
        
        module_name = args[0]
        all_modules = (core.config.get("modules", "enabled", default=[]) + 
                      core.config.get("modules", "disabled", default=[]) + 
                      core.config.get("user_modules", "enabled", default=[]) + 
                      core.config.get("user_modules", "disabled", default=[]))
        
        if module_name not in all_modules:
            return "module with that name doesn't exist"
        
        await self.channel.manager.toggle_module(module_name)
        return "module toggled"
    
    async def cmd_channel(self, args: list):
        if not args:
            return "please provide a name of the channel to toggle"
        
        channel_name = args[0]
        all_channels = core.channel.get_available_channels()
        
        if channel_name not in all_channels:
            return "channel with that name doesn't exist"
        
        await self.channel.manager.toggle_channel(channel_name)
        return "channel toggled"
    
    async def cmd_tools(self, args: list):
        if not core.config.get("model").get("use_tools", False):
            return "Tools are turned off globally."

        dynamic_loading = core.config.get("model", "dynamic_tool_loading", default=True)
        
        if args:
            subcmd = args[0].lower()

            # /tools load <module_name>
            if subcmd == "load":
                if not dynamic_loading:
                    return "Dynamic tool loading is disabled. All tools are already loaded at startup."
                module_names = args[1:]
                if not module_names:
                    return "Usage: /tools load <module_name> [module_name2 ...]"
                lines = [f"▣ Load result for {len(module_names)} module(s):"]
                for module_name in module_names:
                    result = await self.channel.tool_loader.tools_load(module_name)
                    if result.get("status") == "success":
                        lines.append(f"  ✔ {module_name} tools loaded")
                    else:
                        lines.append(f"   ✖ Failed to load {module_name} tools!")
                return "\n".join(lines)

            else:
                return f"Unknown subcommand: {subcmd}. Use /tools load, or /tools (no args) for help."

        # No subcommand — show active + catalog
        tool_map = {}
        for tool in self.channel.manager.tools:
            tool_name = tool.get("function").get("name")
            module_name = "core" if tool_name in ("tools_load",) else tool_name.split("_")[0]

            if module_name not in tool_map:
                tool_map[module_name] = []
            tool_map[module_name].append(tool_name)

        lines = []
        lines.append("== Active Tools ==")
        if tool_map:
            for mod, tools in sorted(tool_map.items()):
                lines.append(f"  ▸ {mod}:")
                for t in sorted(tools):
                    lines.append(f"    • {t}")
        else:
            lines.append("  (none)")

        # Show catalog only if dynamic loading is enabled
        if dynamic_loading:
            catalog_by_module = {}
            for name, entry in self.channel.tool_loader.catalog.items():
                if name in self.channel.tool_loader.active_names:
                    # already loaded (including preloaded default tools)
                    continue
                mod = entry["module"]
                if mod not in catalog_by_module:
                    catalog_by_module[mod] = []
                catalog_by_module[mod].append(name)

            lines.append("\n== Available Tools (Not Loaded) ==")
            if catalog_by_module:
                for mod, names in sorted(catalog_by_module.items()):
                    lines.append(f"  ▸ {mod}:")
                    for n in sorted(names):
                        lines.append(f"    • {n}")
            else:
                lines.append("  (none)")
        else:
            lines.append("\nℹ Dynamic tool loading is disabled. All tools are pre-loaded at startup.")

        return "\n".join(lines)
    
    async def cmd_config(self, args: list):
        """explore, view, and set config settings"""
        def _convert_type(value: str):
            if value.lower() in ["true", "on"]:
                return True
            if value.lower() in ["false", "off"]:
                return False
            try:
                if value.lstrip('-').isdigit():
                    return int(value)
            except ValueError:
                pass
            try:
                return float(value)
            except ValueError:
                pass
            return value
        
        async def _set_config_value(path: list, value: str, manager=None):
            if not path:
                return "error: Path cannot be empty"
            
            typed_value = _convert_type(value.strip())
            
            try:
                target = core.config.config
                if target is None:
                    return "error: Configuration is not loaded. Please restart or wait for system initialization."
                
                current = target
                for i, key in enumerate(path[:-1]):
                    if not isinstance(current, dict):
                        return f"Error: Path {path} is invalid. '{key}' is not a dictionary."
                    current = current[key]
                
                if path[-1] in current and isinstance(current[path[-1]], dict):
                    return "That's a settings group! Check which settings are in it instead of trying to set its value"
                
                if not isinstance(current, dict):
                    return f"Error: Path {path} is invalid. The parent of '{path[-1]}' is not a dictionary."
                
                current[path[-1]] = typed_value
                core.config.config.save()
                
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
        
        async def _get_config_value(path: list):
            try:
                if not path:
                    return "Available settings: " + ", ".join(core.config.config.keys())
                root_item = core.config.get(path[0])
                if root_item is None:
                    return f"{path[0]} is not a valid settings category"
                
                sub_item = root_item
                last_path_key = path[0]
                for path_key in path[1:]:
                    sub_item = sub_item.get(path_key)
                    if sub_item is None:
                        return f"{path_key} is not a valid setting"
                    last_path_key = path_key
                
                if isinstance(sub_item, dict):
                    if len(path) == 3 and path[1] == "settings":
                        section = path[0]
                        name = path[2]
                        
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
                    
                    sub_keys = ", ".join(sub_item.keys())
                    sub_item = f"Available settings in {last_path_key}: {sub_keys}"
                
                return sub_item
            except Exception as e:
                return f"Error retrieving config: {e}"
        
        if not args:
            return str(await _get_config_value([]))
        
        is_set = False
        path_to_use = args
        value_to_use = None
        
        if len(args) >= 1:
            if args[0].strip() in ("modules", "user_modules", "channels"):
                args.insert(1, "settings")
        
        current = core.config.config
        for i, arg in enumerate(args):
            if arg in current:
                if isinstance(current[arg], dict):
                    current = current[arg]
                else:
                    if i < len(args) - 1:
                        is_set = True
                        path_to_use = args[:i+1]
                        value_to_use = " ".join(args[i+1:])
                        break
                    else:
                        break
            else:
                return f"setting '{arg}' does not exist at that path."
        
        if is_set:
            return await _set_config_value(path_to_use, value_to_use, self.channel.manager)
        else:
            return str(await _get_config_value(path_to_use))
    
    async def cmd_history(self, args: list):
        if not core.config.get("api").get("context_window", True):
            return "CONTEXT DISABLED"
        
        show_system_prompt = True if len(args) and args[0] == "full" else False
        context = await self.channel.context.get(system_prompt=show_system_prompt)
        if not context:
            return "BLANK"
        
        context_display = []
        for message in context:
            if message.get("role") in ("tool", "developer"):
                continue
            
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
    
    async def cmd_context(self, args: list):
        context = await self.channel.context.get(system_prompt=True)
        return json.dumps(context, indent=2)
    
    async def cmd_prompt(self, args: list):
        """show system prompt"""
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
    
    async def cmd_prompts(self, args: list):
        enabled = []
        disabled = []
        for module_name, module in self.channel.manager.modules.items():
            has_sysprompt = True if await module.on_system_prompt() else False
            
            if has_sysprompt:
                enabled.append(module_name)
            else:
                disabled.append(module_name)
        
        enabled_str = "\n".join(enabled)
        return f"== modules with active prompts ==\n{enabled_str}"
    
    async def cmd_export(self, args: list):
        export_str = await self.channel.context.chat.export()
        
        export_dir = core.get_data_path(os.path.join("chat_exports", self.channel.name))
        file_name = datetime.datetime.now().strftime("%Y%m%d") + "_" + self.channel.context.chat.get('title')
        
        file_name = file_name.strip('/').replace(" ", "_").replace("..", "")
        file_name = file_name[:50]
        
        file_path = core.get_data_path(os.path.join("chat_exports", self.channel.name, f"{file_name}.txt"))
        os.makedirs(export_dir, exist_ok=True)
        
        with open(file_path, 'w', encoding="utf-8") as f:
            f.write(export_str)
        
        return f"chat exported to {file_path}"
    
    async def cmd_restart(self, args: list):
        await self.channel.manager.restart()
        return "restarting server"
    
    async def cmd_stop(self, args: list):
        await self.channel.manager.API.cancel()
        return "stopped!"
