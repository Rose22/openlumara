import os
import sys
try:
    import readline  # posix-only; gives input() line editing/history where available
except ImportError:
    pass
import asyncio
import random
import concurrent.futures

# prompt toolkit for better input, async prompting, command history, and so on
import prompt_toolkit
import prompt_toolkit.patch_stdout
import prompt_toolkit.history
import prompt_toolkit.formatted_text
import prompt_toolkit.styles
import prompt_toolkit.auto_suggest

# rich for pretty output and progress indicators
import rich
import rich.console
import rich.text
import rich.status
import rich.progress
import rich.markdown
import rich.traceback

# openlumara core
import core

def plaintext(text):
    """helper that makes the Rich library not auto-color text"""

    return rich.text.Text(text)

class Cli(core.channel.Channel):
    """A basic CLI channel for openlumara"""

    settings = {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": True
        },
        "accent_color": {
            "description": "Accent color (as hex code) to use for various UI elements",
            "default": "#E0B0FF"
        },
        "prompt": {
            "description": "The prompt text you would like to appear when the CLI asks you for input",
            "default": "user>"
        },
        "show_status_bar": {
            "description": "Whether to show a bar at the bottom of the CLI, with stuff like current token use, current model, etc",
            "default": True
        },
        "show_chat_title": {
            "description": "Whether to show the chat title in the bottom bar",
            "default": True,
            "depends": "show_status_bar"
        },
        "show_model_name": {
            "description": "Whether to show the model name in the bottom bar",
            "default": True,
            "depends": "show_status_bar"
        },
        "show_token_usage": {
            "description": "Whether to show the current token usage in the bottom bar",
            "default": True,
            "depends": "show_status_bar"
        },
        "show_api_url": {
            "description": "Whether to show the configured API URL in the bottom bar",
            "default": False,
            "depends": "show_status_bar"
        },
    }

    blurbs = [
        "making AI agents easy for everyday people since 2026",
        "the AI framework that puts local AI first",
        "because AI agents should be for more than just coding",
        "what are we doing today?",
        "Rose22 says: i liek stawrbery",
        "Rose22 says: remember to drink water!",
        "the \"open\" stands for open source",
        "where local AI is the #1 priority",
        "your sanctuary in a sea of vibecoded noise",
        "cats have claws too, not just lobsters. meow! :3",
        "fast, lightweight, and modular",
        "the AI agent that literally can't wreck your computer",
        "remember to hydrate!",
        "em dashes are annoying — don't be an em dash.",
        "press A to jump",
        "press B to crouch",
        "press START to play",
        "insert theme song here",
        "initializing artificial intelligence",
        "now you're thinking with portals",
        "pairs well with Qwen or Gemma!",
        "because the average person doesn't have datacenter amounts of VRAM",
        "fully local, fully private",
        "your data stays where it belongs - on your hardware",
        "fully open source, fully local, fully private"
    ]

    dependencies = ["prompt_toolkit", "rich"]

    async def on_ready(self):
        if not sys.stdout.isatty():
            return

        accent_color = self.config.get("accent_color") or "white"

        self.console = rich.console.Console()
        self.console.print(plaintext("-"*40))

        self.console.print(f"[{accent_color}]Welcome to OpenLumara[/]")
        self.console.print(f"[italic]{random.choice(self.blurbs)}[/]")
        self.console.print()

        if core.firstrun:
            self.console.print("-"*40)
            self.console.print("[bold]First start detected![/bold]")
            self.console.print("Welcome to OpenLumara! Here is a quick guide on how to get started:")
            if "webui" in self.manager.channels:
                webui_chan = self.manager.channels["webui"]
                self.console.print(f"1. Open the WebUI at the link indicated below")
                self.console.print("2. Click the gear icon inside the webUI (in the header above the chat) to open the Settings Panel")
                self.console.print("3. Navigate to the API tab, then get your API url from your preferred local AI server (such as llamacpp, lemonade, koboldcpp) or your cloud API")
                self.console.print("4. Verify the connection is good, then navigate to the Models tab and select your model")
                self.console.print("5. You're done. Enjoy!")
            self.console.print("-"*40)

        cmd_prefix = core.config.get("core", "cmd_prefix")

        self.console.print(f"Type {cmd_prefix}new to start a new session, {cmd_prefix}help for help, {cmd_prefix}chats to see your chats")
        self.console.print(f"Type {cmd_prefix}quit or {cmd_prefix}exit to quit")
        self.console.print(plaintext("-"*40))

        # install rich's traceback handler
        rich.traceback.install(show_locals=True)

        self._token_usage = await self.context.get_total_tokens()

    async def _get_input(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, "user> ")

    def _get_accent_color(self):
        return self.config.get("accent_color") or "white"

    def _setup_history(self):
        history_file = os.path.join(core.get_data_path(), "cli_history")
        self.history = prompt_toolkit.history.FileHistory(str(history_file))

    def _token_bar(self, pct, width=10):
        pct = max(0, min(1, pct))  # clamp 0-1
        filled = int(pct * width)
        empty = width - filled

        accent_color = self._get_accent_color()
        return f"<style bg=\"{accent_color}\">" + ("▓" * filled) + "</style>" + ("░" * empty)

    def bottom_bar(self):
        if not self.config.get("show_status_bar"):
            return None

        chat_title = self.context.chat.get('title') or "New chat"
        model = self.manager.API.get_model() or "model not set"
        max_tokens = core.config.get('api', 'max_context')
        api_url = core.config.get('api', 'url')

        tokens_percent = self._token_usage / max_tokens
        token_bar = self._token_bar(tokens_percent, width=20)

        title_str = chat_title[:25] + (".." if len(chat_title)>25 else "") if self.config.get("show_chat_title") else ""
        model_str = f"▣ {model}" if self.config.get("show_model_name") else ""
        token_bar_str = f"◉ Tokens: {token_bar} {self._token_usage}/{max_tokens}" if self.config.get("show_token_usage") else ""
        api_url_str = f"⇄ {api_url}" if self.config.get("show_api_url") else ""

        total_bar = [s for s in (title_str, model_str, token_bar_str, api_url_str) if s]
        total_bar_str = " | ".join(total_bar)
        return prompt_toolkit.formatted_text.HTML(total_bar_str)

    async def run(self):
        # auto disable when not run from a terminal
        if not sys.stdout.isatty():
            return False

        self._setup_history()

        prompt_session = prompt_toolkit.PromptSession(
            history=self.history,
            multiline=False,
            mouse_support=False,
            enable_system_prompt=True,
            enable_suspend=True,
            search_ignore_case=True,
            auto_suggest=prompt_toolkit.auto_suggest.AutoSuggestFromHistory(),
            style=prompt_toolkit.styles.Style.from_dict({
                "bottom-toolbar": "#0A0A0A bg:#777777"
            })
        )

        while True:
            try:
                optional_args = {}
                if self.config.get("show_status_bar"):
                    optional_args["bottom_toolbar"] = self.bottom_bar

                accent_color = self._get_accent_color()
                prompt_text = self.config.get("prompt")
                with prompt_toolkit.patch_stdout.patch_stdout(raw=True):
                    user_input = await prompt_session.prompt_async(
                        prompt_toolkit.formatted_text.HTML(f"<style fg=\"{accent_color}\">{prompt_text}</style> "),
                        set_exception_handler=False,
                        **optional_args
                    )
            except (KeyboardInterrupt, EOFError):
                self.console.print()
                await self.manager.shutdown()
                break

            if not user_input:
                continue

            _, cmd, _ = await self.commands._extract_cmd(user_input)
            if cmd in ("quit", "exit"):
                await self.manager.shutdown()
                break

            processing_prompt = False
            first_processing_prompt = True
            progress = rich.progress.Progress(expand=False, transient=False)
            progress_task = None

            sending_prompt = True
            sending = rich.status.Status("Sending", console=self.console)
            sending.start()

            show_reasoning = self.config.get("show_reasoning")

            strings = {
                "thinking_header": "Thinking:",
                "thinking_newline": "\n-> ",
                "conclusion_header": "",
                "separator": "-"*8 if show_reasoning else "",
                "tool_call_header": "🔧 calling tool {tool_name}"
            }

            if not show_reasoning:
                reasoning_indicator = rich.status.Status("Thinking..", console=self.console)
            reasoning_indicator_started = False

            try:
                async for token in self.format_stream_for_text(
                    self.send_stream(user_input, commands_authorized=True),
                    use_markdown=False,
                    strings=strings,
                    show_indicators=False
                ):
                    token_type = token.get("type")
                    token_content = token.get("content")

                    if token_type == "error":
                        self.console.print(f"[red][bold]ERROR:[/bold] {token_content}[/red]")
                        continue
                    elif token_type in ("user_message", "token_usage"):
                        continue

                    if sending_prompt:
                        sending.stop()
                        sending_prompt = False

                    if token_type == "prompt_progress":
                        if not processing_prompt:
                            if first_processing_prompt:
                                first_processing_prompt = False
                            else:
                                # create a newline so that the progress bar doesnt replace the content
                                self.console.print()

                            # display a progress bar
                            progress.start()
                            progress_task = progress.add_task(f"[{accent_color}]Processing..", total=1)
                            processing_prompt = True

                        progress.update(progress_task, completed=(token_content.get("processed") / token_content.get("total")), refresh=True)
                    elif processing_prompt:
                        # remove the progress bar upon receival of the first non-progress token
                        progress.remove_task(progress_task)
                        progress.stop()
                        processing_prompt = False

                    if token_type == "reasoning" and not show_reasoning:
                        if not reasoning_indicator_started:
                            reasoning_indicator.start()
                            reasoning_indicator_started = True
                    elif token_type == "formatted":
                        if reasoning_indicator_started:
                            reasoning_indicator.stop()
                            reasoning_indicator_started = False

                        self.console.print(token_content, end="")
            except asyncio.CancelledError:
                self.console.print(f"\n[{accent_color}]cancelled.[/]")
            except KeyboardInterrupt:
                self.console.print(f"\n[{accent_color}]cancelled.[/]")
            finally:
                progress.stop()
                sending.stop()

                if not show_reasoning:
                    reasoning_indicator.stop()

                self._token_usage = await self.context.get_total_tokens()

            self.console.print()

    async def on_push(self, message: dict):
        accent_color = self._get_accent_color()
        self.console.print("-"*40)
        self.console.print(f"[{accent_color} bold]{message.get('content')}")
        self.console.print("-"*40)

        self._token_usage = await self.context.get_total_tokens()

    def on_log(self, category: str, message: str):
        if category == "toolcall":
            # SKIP
            return

        if not hasattr(self, 'console'):
            return

        cat_str = rf"\[{category.upper()}] " if category else ""

        accent_color = self._get_accent_color()
        self.console.print(f"[bold {accent_color}]{cat_str}[/]{message}")
