import core
import os
import asyncio
import prompt_toolkit
import prompt_toolkit.patch_stdout
import prompt_toolkit.history
import prompt_toolkit.styles
import prompt_toolkit.formatted_text
import prompt_toolkit.key_binding
import prompt_toolkit.shortcuts
import prompt_toolkit.application
import sys

class Cli(core.channel.Channel):
    running = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_style()
        self._setup_history()

    def _setup_style(self):
        self.style = prompt_toolkit.styles.Style.from_dict({
            "prompt": "ansicyan bold",
            "reasoning-label": "ansiyellow bold",
            "conclusion-label": "ansimagenta bold",
            "error": "ansired bold",
            "status": "ansiblue",
        })

    def _setup_history(self):
        history_file = os.path.join(core.get_data_path(), "cli_history")
        self.history = prompt_toolkit.history.FileHistory(str(history_file))

    def _get_prompt(self):
        return prompt_toolkit.formatted_text.HTML(
            "<prompt>user</prompt>> "
        )

    def _print_formatted(self, text, style_class=None):
        if style_class:
            formatted = prompt_toolkit.formatted_text.HTML(
                f"<{style_class}>{text}</{style_class}>"
            )
            prompt_toolkit.shortcuts.print_formatted_text(formatted, style=self.style)
        else:
            print(text, end="", flush=True)

    async def run(self):
        if not sys.stdin.isatty():
            return False

        prompt_session = prompt_toolkit.PromptSession(
            history=self.history,
            style=self.style,
            multiline=False,
            mouse_support=False,
            enable_system_prompt=True,
            enable_suspend=True,
            search_ignore_case=True,
        )

        with prompt_toolkit.patch_stdout.patch_stdout():
            while self.running:
                msg = await prompt_session.prompt_async(
                    self._get_prompt(),
                    refresh_interval=0.5,
                )

                if not msg.strip():
                    continue

                await self._process_message(msg)

        return True

    async def _process_message(self, msg):
        message_state = None
        async for token in self.send_stream({"role": "user", "content": msg}):
            token_type = token.get("type")
            if token_type not in ["reasoning", "content"]:
                continue

            content = token.get("content", "")

            if token_type == "reasoning" and not message_state:
                self._print_formatted("Reasoning:", "reasoning-label")
                message_state = "reasoning"

            if token_type == "content" and message_state == "reasoning":
                self._print_formatted("\nConclusion:", "conclusion-label")
                message_state = "final output"

            print(content, end="", flush=True)

        print()
        print()

    async def _announce(self, message: str, type: str = None):
        style_map = {
            "error": "error",
            "status": "status",
            "warning": "reasoning-label",
        }
        style_class = style_map.get(type)
        self._print_formatted(f"[cli] {message}\n", style_class)
        core.log("cli", message)

    def on_shutdown(self):
        self.running = False
        return True
