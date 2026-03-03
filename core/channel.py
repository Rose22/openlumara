import core
import os
import sys
import time
import json

class Channel:
    """Base class for channels"""

    def __init__(self, manager):
        self.name = self.__class__.__name__
        self.manager = manager
        self._help = """
/new            start a new session (clears context window)
/models         list available models
/model          switch model
/modules        list modules
/module         enable/disable a module by name
/tools          list tools
/sysprompt      show current system prompt
/context        show current context window
/stop           stops a running task
/restart        restarts the server
/stop           stops the AI in it's tracks
/help           this help
""".strip()


    async def _process_input(self, message: str):
        """processes user input and detects special commands that control opticlaw"""
        message = message.strip().lower()
        cmd_prefix = core.config.get("cmd_prefix", "/")
        if not message.startswith(cmd_prefix):
            return None

        cmd = message.split(cmd_prefix)[1].split()

        match cmd[0]:
            case "new":
                self.manager.API._turns = []
                return "New session started."
            case "help":
                return self._help
            case "models":
                return "not implemented yet"
            case "model":
                return "not implemented yet"
            case "modules":
                # TODO: also get disabled modules
                modules_str = "\n".join(core.config.get("modules"))
                modules_disabled_str = "\n".join(core.config.get("modules_disabled"))
                modules_loaded_str = "\n".join(self.manager.modules.keys())

                return f"Loaded:\n{modules_loaded_str}\n\nDisabled in config:\n{modules_disabled_str}\n"
            case "module":
                return "not implemented yet"
            case "tools":
                tool_list = []
                for tool in self.manager.tools:
                    tool_list.append(tool.get("function").get("name"))
                return "\n".join(tool_list)
            case "sysprompt":
                if not core.config.get("context_window"):
                    return "CONTEXT DISABLED"

                sysprompt = await self.manager.get_system_prompt()
                return sysprompt if sysprompt else "BLANK"
            case "context":
                if not core.config.get("context_window"):
                    return "CONTEXT DISABLED"

                context = await self.manager.API.build_context(system_prompt=False)
                if not context:
                    return "BLANK"

                context_display = []
                for turn in context:
                    context_display.append(f"== {turn.get('role')} ==\n{turn.get('content')}")

                return "\n\n".join(context_display)
            case "restart":
                await self.announce_all("restarting server..")
                time.sleep(0.1)
                os.execv(sys.argv[0], sys.argv)
            case "stop":
                # just use restart for now until i figure out how to kill the asyncio tasks
                await self.announce_all("stopping..")
                time.sleep(0.1)
                os.execv(sys.argv[0], sys.argv)
            case _:
                return self._help

    async def send(self, role: str, message: str, **kwargs):
        """sends a message to the AI from within the current channel"""
        cmd_process = await self._process_input(message)
        if cmd_process:
            return cmd_process

        return await self.manager.API.send(role, message, channel=self, stream=False, **kwargs)

    async def send_stream(self, role: str, message: str, **kwargs):
        """sends a message to the AI from within the current channel, streaming version"""
        cmd_process = await self._process_input(message)
        if cmd_process:
            for word in cmd_process:
                yield word
            return

        async for token in self.manager.API.send_stream(role, message, channel=self, **kwargs):
            yield token

    async def announce(self, message: str):
        """called externally to announce things in this channel, such as a reminder sent by the AI"""
        raise NotImplementedError

    async def announce_all(self, message: str):
        """announces a message across all channels. useful for very important notifications!"""
        for channel_name, channel in self.manager.channels.items():
            await channel.announce(message)
        return
