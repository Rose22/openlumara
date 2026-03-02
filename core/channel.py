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
                return """
/new            start a new session (clears context window)
/models         list available models
/model          switch model
/tools          list tools
/enable         enable a tool
/disable        disable a tool
/stop           stops a running task
/restart        restarts the server
/help           this help
""".strip()
            case "models":
                return "not implemented yet"
            case "model":
                return "not implemented yet"
            case "tools":
                tool_list = []
                for tool in self.manager.tools:
                    tool_list.append(tool.get("function").get("name"))
                return "\n".join(tool_list)
            case "enable":
                return "not implemented yet"
            case "disable":
                return "not implemented yet"
            case "debug":
                await self.announce_all("piiiinggg!")
                return "sent a debug announcement to all channels!"
            case "restart":
                await self.announce_all("restarting..")
                time.sleep(0.5)
                os.execv(sys.argv[0], sys.argv)
            case "stop":
                return "Not implemented yet"

    async def send(self, role: str, message: str, **kwargs):
        """sends a message to the AI from within the current channel"""
        cmd_process = await self._process_input(message)
        if cmd_process:
            return cmd_process

        response = self.manager.API.send(role, message, stream=False, **kwargs)
        return await self.manager.API.recv(response, self, **kwargs)

    async def send_stream(self, role: str, message: str, **kwargs):
        """sends a message to the AI from within the current channel, streaming version"""
        cmd_process = await self._process_input(message)
        if cmd_process:
            for word in cmd_process:
                yield word
            return

        response = self.manager.API.send(role, message, stream=True, **kwargs)
        async for token in self.manager.API.recv_stream(response, self, **kwargs):
            yield token

    async def announce(self, message: str):
        """called externally to announce things in this channel, such as a reminder sent by the AI"""
        raise NotImplementedError

    async def announce_all(self, message: str):
        """announces a message across all channels. useful for very important notifications!"""
        for channel_name, channel in self.manager.channels.items():
            await channel.announce(message)
        return
