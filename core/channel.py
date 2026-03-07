import core
import os
import sys
import time
import json
import asyncio

class Channel:
    """Base class for channels"""

    def __init__(self, manager):
        self.name = self.__class__.__name__
        self.manager = manager
        self._last_cmd_was_temporary = False

    async def _get_help(self):
        output = []

        help_text = """
== built in commands ==
/new            start a new session (clears context window)
/clear          same as /new
/sysprompt      show current system prompt
/prompts        show which modules are injecting prompts into the system prompt
/context        show current context window
/tools          list tools available to the AI

/status         show status info
/modules        list modules
/module         enable/disable a module by name

/restart        restarts the server
/stop           stops the AI in it's tracks
/help           this help
        """.strip()

        output.append(help_text)

        if self.manager.modules:
            # support custom commands supplied by modules
            for module_name, module in self.manager.modules.items():
                if hasattr(module, "on_command_help"):
                    cmd_help = await module.on_command_help()
                    if cmd_help:
                        output.append(f"== {module_name} ==\n{cmd_help}".strip())

        return "\n\n".join(output)

    async def _process_input(self, message: str):
        """processes user input and detects special commands that control opticlaw"""
        message = message.strip().lower()
        cmd_prefix = core.config.get("cmd_prefix", "/")
        cmd_prefix_index = message.find(cmd_prefix)+len(cmd_prefix)
        if not message.startswith(cmd_prefix):
            return None

        cmd = message[cmd_prefix_index:].split()
        args = cmd[1:]

        match cmd[0]:
            case "new":
                self.manager.API._messages = []
                return "New session started."
            case "clear":
                # alias for "new"
                self.manager.API._messages = []
                return "New session started."
            case "help":
                return await self._get_help()
            case "status":
                return "\n".join(await self.manager.get_status())
            case "modules":
                modules_str = "\n".join(core.config.get("modules"))
                modules_disabled_str = "\n".join(core.config.get("modules_disabled"))
                modules_loaded_str = "\n".join(self.manager.modules.keys())

                return f"== loaded ==\n{modules_loaded_str}\n\n== disabled ==\n{modules_disabled_str}\n"
            case "module":
                if not args:
                    return "please provide a name of the module to toggle"

                import modules
                module_manager = modules.module_manager.Modules(self.manager)
                found = False
                for module in modules.get_all(respect_config=False):
                    module_name = core.modules.get_name(module)
                    print(module_name)
                    if args[0].lower().strip() == module_name:
                        found = True

                if not found:
                    return "module with that name doesn't exist"

                await module_manager.toggle(args[0])
                await self.announce("module toggled")
                await self.announce("restarting to apply module change..", "error")
                await asyncio.sleep(0.2)
                await core.restart()
                return
            case "prompts":
                enabled = []
                no_prompt = []
                disabled = []
                for module_name, module in self.manager.modules.items():
                    has_sysprompt = True if await module.on_system_prompt() else False

                    if has_sysprompt and (module_name not in core.config.get("modules_disable_prompts")):
                        enabled.append(module_name)
                    elif module_name not in core.config.get("modules_disable_prompts"):
                        no_prompt.append(module_name)
                    else:
                        disabled.append(module_name)

                enabled_str = "\n".join(enabled)
                no_prompt_str = "\n".join(no_prompt)
                disabled_str = "\n".join(disabled)
                return f"== modules with active prompts ==\n{enabled_str}\n\n== modules that don't include prompts ==\n{no_prompt_str}\n\n== modules with disabled prompts ==\n{disabled_str}"

            case "tools":
                tool_map = {}
                for tool in self.manager.tools:
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

                self._last_cmd_was_temporary = True

                return "\n\n".join(tool_map_display)
            case "sysprompt":
                if not core.config.get("context_window"):
                    return "CONTEXT DISABLED"

                _sysprompt = await self.manager.get_system_prompt()
                if not _sysprompt:
                    _sysprompt = "BLANK"
                sysprompt = f"=== system prompt ===\n{_sysprompt}"
                disabled_prompts = core.config.get("modules_disable_prompts")
                if disabled_prompts:
                    sysprompt += "\n\n=== disabled prompts ===\n"
                    sysprompt += "\n".join([mod_name for mod_name in disabled_prompts])
                endprompt = await self.manager.get_end_prompt()
                if endprompt:
                    sysprompt += f"\n\n=== end prompts ===\n{endprompt}"

                self._last_cmd_was_temporary = True

                return sysprompt if sysprompt else "BLANK"
            case "context":
                if not core.config.get("context_window"):
                    return "CONTEXT DISABLED"

                context = await self.manager.API.build_context(system_prompt=True)
                if not context:
                    return "BLANK"

                self._last_cmd_was_temporary = True

                context_display = []

                for message in context:
                    content = message.get("content")
                    if not content:
                        if message.get("tool_calls"):
                            content = str(message.get("tool_calls"))

                    context_display.append(f"== {message.get('role')} ==\n{content}")

                context_display.append("---")

                disabled_prompts = core.config.get("modules_disable_prompts")
                if disabled_prompts:
                    disabled_prompts_str = "\n".join([mod_name for mod_name in disabled_prompts])
                    context_display.append(f"== disabled prompts ==\n{disabled_prompts_str}")

                ctx_string = ""
                context_size = await self.manager.API.get_context_size()
                for key, value in context_size.items():
                    ctx_string += f"{key}: {value}\n"
                context_display.append(f"== context size ==\n{ctx_string}")

                return "\n\n".join(context_display)
            case "restart":
                await core.restart(self)
            case "stop":
                # just use restart for now until i figure out how to kill the asyncio tasks
                await self.manager.API.cancel()
                return "stopped!"
            case _:
                if self.manager.modules:
                    # support custom commands supplied by modules
                    for module_name, module in self.manager.modules.items():
                        if hasattr(module, "on_command"):
                            if cmd[0].lower().strip() == module_name:
                                return await module.on_command(cmd[1:])

                return await self._get_help()

    async def send(self, role: str, message: str, **kwargs):
        """sends a message to the AI from within the current channel"""
        if self._last_cmd_was_temporary:
            # Remove the last two messages: the command and the command_response
            # We pop twice to ensure both the trigger and the result are gone.
            if len(self.manager.API._messages) >= 2:
                self.manager.API._messages.pop()
                self.manager.API._messages.pop()
                self._last_cmd_was_temporary = False

        cmd = await self._process_input(message)
        if cmd:
            # insert /command into messages so that it gets properly tracked and displayed
            await self.manager.API.insert_message(f"command", message)

            # insert and return the command response without sending it to the AI
            await self.manager.API.insert_message(f"command_response", cmd)
            return cmd
        else:
            # if not a command, send the message to the AI and return it's response (context insertion happens in the API.send() method)
            return await self.manager.API.send(role, message, channel=self, stream=False, **kwargs)

    async def send_stream(self, role: str, message: str, **kwargs):
        """sends a message to the AI from within the current channel, streaming version"""
        if self._last_cmd_was_temporary:
            if len(self.manager.API._messages) >= 2:
                self.manager.API._messages.pop()
                self.manager.API._messages.pop()
                self._last_cmd_was_temporary = False

        cmd = await self._process_input(message)
        if cmd:
            # insert /command into messages so that it gets properly tracked and displayed
            await self.manager.API.insert_message(f"command", message)

            # insert and return the command response without sending it to the AI
            cmd_response = []
            for token in cmd:
                cmd_response.append(token)
                yield token
            await self.manager.API.insert_message(f"command_response", "".join(cmd_response))
            return
        else:
            async for token in self.manager.API.send_stream(role, message, channel=self, **kwargs):
                yield token

    async def announce(self, message: str, type=None, insert_message=True):
        """called externally to announce things in this channel, such as a reminder sent by the AI"""
        if not type:
            type = "info"

        # insert announced message into context
        if insert_message:
            await self.manager.API.insert_message(f"announce_{type}", message)

        # Subclass hook
        await self._announce(message, type=type)
    async def _announce(self, message: str, type=None):
        """override this one in subclasses"""
        raise NotImplementedError

    async def announce_all(self, message: str, type=None):
        """announces a message across all channels. useful for very important notifications!"""
        if not type:
            type = "info"

        count = 0
        for channel_name, channel in self.manager.channels.items():
            insert = True if count < 1 else False
            await channel.announce(message, type, insert_message=insert)
            count += 1
        return

    async def ask(self, message: str):
        """sends a message in the channel and then intercepts communication for one message so that user can be asked for input without that input being sent to the LLM. useful for menus."""
        pass
