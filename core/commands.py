import core

def get_commands_help(modules_dict):
    """
    Builds a help string grouped by module instance.
    """
    output = []

    for module_name, instance in modules_dict.items():
        module_cmds = []

        # Scan the global registry for commands belonging to this instance's class
        for cmd_name, handlers in core.module._command_registry.items():
            for registered_cls, method in handlers:
                if isinstance(instance, registered_cls):
                    desc = method._command_description
                    # Format: /command              description
                    module_cmds.append(f"{cmd_name:<20} {desc}")
                    break # Only take the first matching handler

        # If this module has any commands, add them to the output
        if module_cmds:
            # Sort alphabetically
            module_cmds.sort()
            section = f"== {module_name} ==\n" + "\n".join(module_cmds)
            output.append(section)

    return "\n\n".join(output)

class Commands:
    # delete these after they are shown to the user once
    TEMPORARY = ("context", "sysprompt", "tools")

    def __init__(self, channel):
        self.channel = channel

    async def _get_help(self):
        output = []

        help_text = """
== built in commands ==
/new                    start a new session (clears context window)
/clear                  same as /new
/sysprompt              show current system prompt
/prompts                show which modules are injecting prompts into the system prompt
/context                show current context window
/tools                  list tools available to the AI

/status                 show status info
/modules                list modules
/module                 enable/disable a module by name

/set                    shows you all settings
/set <name>             shows you the value of a setting
/set <name> <value>     sets a setting to that value

/restart                restarts the server
/stop                   stops the AI in it's tracks
/help                   this help
        """.strip()

        output.append(help_text)

        if self.channel.manager.modules:
            # Get automated command help grouped by module
            cmd_help = core.commands.get_commands_help(self.channel.manager.modules)
            if cmd_help:
                output.append(cmd_help)

        return "\n\n".join(output)

    async def process_input(self, message: dict):
        """processes user input and detects special commands that control opticlaw"""
        message_content_orig = message.get("content")
        message_content = message.get("content").strip().lower()
        cmd_prefix = core.config.get("cmd_prefix", "/")
        cmd_prefix_index = message_content.find(cmd_prefix)+len(cmd_prefix)

        # why not lol
        if message_content_orig.startswith("STOP"):
            await self.channel.manager.API.cancel()
            return "stopped!"

        if not message_content.startswith(cmd_prefix):
            return None

        # always use temporary commands if tools are turned off. command output being seen by the AI is not useful and usually not wanted in that case

        cmd = message_content[cmd_prefix_index:].split()
        args = cmd[1:]

        match cmd[0]:
            case "new":
                result = await self.channel.context.chat.new()
                if not result:
                    return "failed to start new session"

                return "New session started."
            case "clear":
                result = await self.channel.context.chat.clear()
                if not result:
                    return "failed to clear current chat"
                return "Cleared current chat!"
            # case "undo":
            #     self.channel.manager.API._messages.pop()
            #     self.channel.manager.API._messages.pop()
            #     self._last_cmd_was_temporary = True
            #     return "Turn undone."
            case "help":
                return await self._get_help()
            case "status":
                return "\n".join(await self.channel.manager.get_status())
            case "modules":
                modules_str = "\n".join(core.config.get("modules").get("enabled"))
                modules_disabled_str = "\n".join(core.config.get("modules").get("disabled"))
                modules_loaded_str = "\n".join(self.channel.manager.modules.keys())

                return f"== loaded ==\n{modules_loaded_str}\n\n== disabled ==\n{modules_disabled_str}\n"
            case "module":
                if not args:
                    return "please provide a name of the module to toggle"

                import modules
                module_manager = modules.module.Module(self.channel.manager)
                found = False
                for module in modules.get_all(respect_config=False):
                    module_name = core.modules.get_name(module)
                    print(module_name)
                    if args[0].lower().strip() == module_name:
                        found = True

                if not found:
                    return "module with that name doesn't exist"

                await module_manager.toggle(args[0])
                await self.channel.announce("module toggled")
                await self.channel.announce("restarting to apply module change..", "error")
                await asyncio.sleep(0.2)
                await core.restart()
                return
            case "set":
                if not args:
                    display_list = []
                    for key, value in core.config.config.items():
                        if isinstance(value, list):
                            continue
                        elif isinstance(value, bool):
                            value = "on" if value else "off"
                        elif "_key" in key or "_token" in key:
                            value = "******"

                        display_list.append(f"{key}: {value}")

                    return "\n".join(display_list)

                key = args[0].lower()
                if key not in core.config.config.keys():
                    return "that setting does not exist"

                if len(args) < 2:
                    # show value
                    value = core.config.get(key)
                    if isinstance(value, bool):
                        value = "on" if value else "off"
                    return value
                else:
                    if key in ("api_url", "api_key"):
                        return "it is unsafe to modify API settings while opticlaw is running. please manually edit the config file."

                    # set value
                    setting = " ".join(args[1:])
                    if isinstance(core.config.get(key), list):
                        return "use the respective module to change this setting"
                    if isinstance(core.config.get(key), bool):
                        if setting.lower() in ("true", "on"):
                            setting = True
                        elif setting.lower() in ("false", "off"):
                            setting = False
                        else:
                            return "set this setting to either on or off"

                    if isinstance(setting, str) and setting.isdecimal():
                        setting = int(setting)

                    core.config.config[key] = setting
                    core.config.config.save()

                    return "setting changed!"
            case "prompts":
                enabled = []
                no_prompt = []
                disabled = []
                for module_name, module in self.channel.manager.modules.items():
                    has_sysprompt = True if await module.on_system_prompt() else False

                    if has_sysprompt and (module_name not in core.config.get("modules").get("disabled_prompts")):
                        enabled.append(module_name)
                    elif module_name not in core.config.get("modules").get("disabled_prompts"):
                        no_prompt.append(module_name)
                    else:
                        disabled.append(module_name)

                enabled_str = "\n".join(enabled)
                no_prompt_str = "\n".join(no_prompt)
                disabled_str = "\n".join(disabled)
                return f"== modules with active prompts ==\n{enabled_str}\n\n== modules that don't include prompts ==\n{no_prompt_str}\n\n== modules with disabled prompts ==\n{disabled_str}"

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
            case "sysprompt":
                if not core.config.get("api").get("context_window"):
                    return "CONTEXT DISABLED"

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
            case "context":
                if not core.config.get("api").get("context_window"):
                    return "CONTEXT DISABLED"

                context = await self.channel.context.get(system_prompt=True)
                if not context:
                    return "BLANK"

                if len(cmd) > 1 and cmd[1] == "raw":
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
            case "restart":
                await core.restart(self)
            case "stop":
                # just use restart for now until i figure out how to kill the asyncio tasks
                await self.channel.manager.API.cancel()
                return "stopped!"
            case _:
                # Check the new decorator registry
                if self.channel.manager.modules:
                    cmd_lookup = cmd[0].lower().strip()

                    # See if this command exists in the registry
                    if cmd_lookup in core.module._command_registry:
                        for registered_cls, method in core.module._command_registry[cmd_lookup]:
                            # Find the instance of this class in the loaded modules
                            for module_inst in self.channel.manager.modules.values():
                                if isinstance(module_inst, registered_cls):
                                    # Bind the method to the instance and call it
                                    bound_method = method.__get__(module_inst, registered_cls)
                                    return await bound_method(cmd[1:])

                return await self._get_help()
