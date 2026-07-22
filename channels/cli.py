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
import shlex

class Cli(core.channel.Channel):
    """Talk to your AI from the terminal! Auto-disables itself when ran as a background server."""

    dependencies = ["prompt_toolkit", "partial-json-parser"]

    # TODO: use partial-json-parser for the streaming toolcalls :D yayyy!!

    running = True

    settings = {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        }
        # "stream_tool_calls": {
        #     "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
        #     "default": False
        # }
    }

    def _setup_style(self):
        self.style = prompt_toolkit.styles.Style.from_dict({
            "prompt": "ansicyan bold"
            # "reasoning-label": "ansiyellow bold",
            # "conclusion-label": "ansimagenta bold",
            # "toolcall-response-label": "ansiblue bold",
            # "error": "ansired bold",
            # "status": "ansiblue",
            # "separator": "ansigray",
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

    async def _process_message(self, msg):
        message_state = None
        # Create a fresh renderer for this message session
        currently_reasoning = False

        # special commands like /quit
        message_after = None

        words = shlex.split(msg)
        cmd_prefix = core.config.get("core", "cmd_prefix")
        cmd = words[0][len(cmd_prefix):]

        if cmd in ("quit", "exit"):
                print("Exiting..")
                await self.manager.shutdown()
                return
        elif cmd == "help":
            # append the extra commands to the /help
            message_after = """
---
/quit           quits the program
/exit           quits the program
""".strip()

        # display sending indicator
        print("sending..", end="", flush=True)

        first_token_received = False
        processing_prompt = False
        async for token in self.format_stream_for_text(
            self.send_stream(msg, commands_authorized=True),
            use_markdown=False
        ):
            token_type = token.get("type")
            content = token.get("content", "")

            if token_type == "prompt_progress":
                print("\rprocessing your request..", end="", flush=True)
                processing_prompt = True

            if token_type in ["content", "reasoning"]:
                if not first_token_received:
                    # remove sending indicator using \r
                    process_padding = 25 if processing_prompt else 0 # 25 is the length of "processing your request.."

                    print("\r"+" "*process_padding, end="", flush=True)
                    print("\r", end="", flush=True)

                    processing_prompt = False
                    first_token_received = True

                print(content, end="", flush=True)

        if message_after:
            print(message_after)

        print()
        print()

    async def run(self):
        if not sys.stdin.isatty():
            return False

        self._setup_style()
        self._setup_history()

        prompt_session = prompt_toolkit.PromptSession(
            history=self.history,
            style=self.style,
            multiline=False,
            mouse_support=False,
            enable_system_prompt=True,
            enable_suspend=True,
            search_ignore_case=True
        )

        with prompt_toolkit.patch_stdout.patch_stdout():
            while self.running:
                try:
                    msg = await prompt_session.prompt_async(
                        self._get_prompt(),
                        refresh_interval=0.5,
                        set_exception_handler=False
                    )
                except KeyboardInterrupt:
                    await self.manager.shutdown()
                    break

                if not msg.strip():
                    continue

                await self._process_message(msg)

        return True

    async def on_push(self, message: dict):
        self.log("push", message.get("content").strip())
        print(flush=True)

    def on_log(self, category, message):
        if category == "toolcall":
            # SKIP
            return

        if core.quiet:
            return

        # allow hiding the category string for special formatting and stuff
        cat_str = f"[{category.upper()}] " if category else ""
        print(f"{cat_str}{message}", flush=True)

    def on_shutdown(self):
        self.running = False
        return True
