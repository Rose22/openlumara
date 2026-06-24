import core
import os
import asyncio
import sys
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

class CliMarkdown(core.channel.Channel):
    """Talk to your AI from the terminal! Experimental version with markdown support. Auto-disables itself when ran as a background server."""

    dependencies = ["rich", "prompt_toolkit"]

    running = True
    ready = False

    settings = {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False
        }
    }

    console = None
    running = True
    queued_logs = []

    async def _process_message(self, msg):
        buffer = []
        first_token = True

        strings = {
            "thinking_header": "**Thinking**  ",
            "thinking_str": "*thinking..*  ",
            "conclusion_header": "**Conclusion**  ",
            "processing_tool": "(processing results..)",
            "newline": "  \n",
            "thinking_newline": "\n"
        }

        self.console.print("sending..", end="")

        # Live runs a background thread. We must avoid blocking or printing directly inside it.
        with Live(
            console=self.console,
            refresh_per_second=8,
            transient=False,
            vertical_overflow="visible"
        ) as live:
            async for token in self.format_stream_for_text(
                self.send_stream({"role": "user", "content": msg}, commands_authorized=True),
                strings=strings
            ):
                if first_token:
                    self.console.print("\r", end="")
                    first_token = False

                content = token.get("content", "")
                buffer.append(content)
                live.update(Markdown("".join(buffer)), refresh=True)

        # Move cursor down after streaming completes
        self.console.print()

    async def on_ready(self):
        self.console = Console()

        # Prompt Toolkit setup
        self.history_path = os.path.join(core.get_data_path(), "cli_history.txt")
        self.history = FileHistory(self.history_path)

        # Custom key bindings
        self.kb = KeyBindings()

        @self.kb.add('escape', 'r')
        def _(event):
            """Toggle reverse history search"""
            vent.app.current_buffer.search_direction = 'reverse'
            event.app.current_buffer.begin_search()

        # Style configuration
        self.style = Style.from_dict({
            'prompt': 'cyan bold',
            'default': 'ansiblack',
        })

        # Create PromptSession
        self.session = PromptSession(
            history=self.history,
            key_bindings=self.kb,
            style=self.style,
            multiline=False,
            complete_while_typing=True,
            enable_history_search=True,
            mouse_support=False,
        )

        self.ready = True

    async def run(self):
        if not sys.stdin.isatty():
            return False

        while not self.ready:
            await asyncio.sleep(0.1)

        while self.running:
            try:
                # prompt_toolkit handles history, multi-line, and search natively
                msg = await self.session.prompt_async("user> ")

                if not msg or not msg.strip():
                    continue

                if msg.strip().lower() in ("/quit", "/exit"):
                    await self.manager.shutdown()
                    break

                cmd_prefix = core.config.get("core", "cmd_prefix")
                if msg.strip().lower().startswith(cmd_prefix):
                    cmd_response = await self.send({"role": "user", "content": msg}, commands_authorized=True)
                    cmd_response_str = cmd_response.get("content")
                    self.console.print(Markdown(f"```\n{cmd_response_str}\n```"))
                    continue

                await self._process_message(msg)

            except KeyboardInterrupt:
                await self.manager.shutdown()
                break
            except Exception as e:
                print(e)

        return True

    async def on_request_stalled(self):
        self.console.print("\r[blue dim]...waiting for response...[/blue dim]")

    async def on_push(self, message: dict):
        self.console.print(f"[bold]PUSH[/bold] {message.get('content').strip()}")

    def on_log(self, category, message):
        if category == "toolcall":
            return

        if self.console:
            if self.queued_logs:
                for cat, msg in self.queued_logs:
                    self.console.print(f"[bold]<{cat.upper()}>[/bold] {msg}")
                self.queued_logs = None

            self.console.print(f"[bold]<{category.upper()}>[/bold] {message}")
        else:
            self.queued_logs.append((category, message))

    def on_shutdown(self):
        self.running = False
        # prompt_toolkit FileHistory auto-saves on session close, but we can force it if needed
        try:
            self.history.save_history_file()
        except Exception:
            pass
        return True
