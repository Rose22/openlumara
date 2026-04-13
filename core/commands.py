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

class Commands:
    # delete these after they are shown to the user once
    TEMPORARY = ("context", "prompt", "tools", "restart", "stop")

    def __init__(self, channel):
        self.channel = channel

    async def _get_help(self):
        output = []

        help_text = """
== built in commands ==
/modules                list modules
/module                 enable/disable a module by name
/tools                  list tools available to the AI
/status                 show status info
/restart                restarts the server
/stop                   stops the AI in it's tracks
/ping                   test command that echoes "Pong!"
/help                   this help
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

    async def _extract_cmd(self, message: dict):
        message_content_orig = message.get("content")
        message_content = message.get("content").strip().lower()
        cmd_prefix = core.config.get("cmd_prefix", "/")
        cmd_prefix_index = message_content.find(cmd_prefix)+len(cmd_prefix)

        cmd = message_content[cmd_prefix_index:].split()
        args = cmd[1:]

        return (cmd_prefix, cmd, args)

    async def process_input(self, message: dict):
        """wrapper around the real _process_input, handles insertion of context"""
        cmd_prefix, cmd, args = await self._extract_cmd(message)

        # treat message as normal if it's not a command
        if cmd is None or not message.get("content").startswith(cmd_prefix):
            return False

        use_temporary = self._check_if_temporary(cmd[0])

        # insert /command into context so that it gets properly tracked and displayed
        args_display = ""
        if args:
            args_display += " "
            args_display += "".join(args)
        await self.channel.context.chat.add({"role": "user", "content": f"{cmd_prefix}{cmd[0]}{args_display}"}, temporary=use_temporary)

        result = await self._process_input(message)

        # insert command result into context, flagging as temporary if needed
        await self.channel.context.chat.add({"role": "assistant", "content": f"[Command Output]:\n{result}"}, temporary=use_temporary)

        return result

    async def _process_input(self, message: dict):
        """processes user input and detects special commands that control opticlaw"""

        cmd_prefix, cmd, args = await self._extract_cmd(message)

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
            case "restart":
                #await core.restart(self.channel)
                await self.channel.manager.restart()
                return "restarting.."
            case "stop":
                # just use restart for now until i figure out how to kill the asyncio tasks
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
