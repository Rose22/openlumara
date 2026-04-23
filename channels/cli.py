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
import re
import json
import json_repair

class ToolCallRenderer:
    def __init__(self):
        self.current_tool = None
        self.printed_values = {}

    def render(self, name: str, args_str: str):
        # If this is a new tool, print the header.
        if self.current_tool != name:
            prompt_toolkit.shortcuts.print_formatted_text(
                prompt_toolkit.formatted_text.HTML(f"\n<b>Calling tool: {name}()</b>")
            )
            self.current_tool = name
            self.printed_values = {}

        try:
            data = json_repair.loads(args_str)
            if not isinstance(data, dict):
                return

            for key, value in data.items():
                should_erase_line = False
                val_str = str(value)
                previously_printed = self.printed_values.get(key, "")

                if val_str.startswith(previously_printed):
                    to_print = val_str[len(previously_printed):]
                else:
                    to_print = val_str
                    should_erase_line = True

                if key not in self.printed_values:
                    prompt_toolkit.shortcuts.print_formatted_text(
                        prompt_toolkit.formatted_text.HTML(f"\n<ansicyan>{key}:</ansicyan>\n"),
                        end="",
                        flush=True
                    )

                if to_print:
                    to_print = to_print.replace("\\n", "\n")
                    if should_erase_line:
                        print("\r", end="", flush=True)

                    print(f"{to_print}", end="", flush=True)

                self.printed_values[key] = val_str
        except Exception:
            pass

    def reset(self):
        """Finalize the tool call block with a newline."""
        if self.current_tool is not None:
            self.current_tool = None
            self.printed_values = {}

class Cli(core.channel.Channel):
    running = True

    def _setup_style(self):
        self.style = prompt_toolkit.styles.Style.from_dict({
            "prompt": "ansicyan bold",
            "reasoning-label": "ansiyellow bold",
            "conclusion-label": "ansimagenta bold",
            "toolcall-response-label": "ansiblue bold",
            "error": "ansired bold",
            "status": "ansiblue",
            "separator": "ansigray",
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

    def _print_header(self, label: str, style_class: str = None):
        width = 40
        separator = "─" * width
        self._print_formatted(f"{separator}", "separator")
        self._print_formatted(f"  {label}", style_class)
        self._print_formatted(f"{separator}", "separator")

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
                msg = await prompt_session.prompt_async(
                    self._get_prompt(),
                    refresh_interval=0.5,
                    set_exception_handler=False
                )

                if not msg.strip():
                    continue

                await self._process_message(msg)

        return True

    async def _process_message(self, msg):
        message_state = None
        # Create a fresh renderer for this message session
        tool_renderer = ToolCallRenderer()
        currently_reasoning = False

        async for token in self.send_stream({"role": "user", "content": msg}):
            token_type = token.get("type")
            content = token.get("content", "")

            # print headers
            if token_type == "reasoning" and not currently_reasoning:
                self._print_header("Reasoning", "reasoning-label")
                currently_reasoning = True
            elif token_type == "tool":
                self._print_formatted("\n(processing results..)", "toolcall-response-label")
            elif token_type == "content" and currently_reasoning:
                self._print_header("Conclusion", "conclusion-label")

            if token_type in ["content", "tool_calls", "tool"] and currently_reasoning:
                # we can have multiple reasoning blocks
                currently_reasoning = False

            # if token_type == "tool":
            #     # print toolcall response
            #     result = json.loads(content)
            #     subcontent = result.get("content")
            #     print(str(subcontent).strip(), flush=True)

            elif token_type == "tool_call_delta":
                # Extract the accumulated tool call from the delta
                tc_list = token.get("tool_calls", [])
                if tc_list:
                    tc = tc_list[0]
                    # Render the partial/full tool call fancy style
                    tool_renderer.render(tc.function.name, tc.function.arguments)

            elif token_type == "tool_calls":
                # The final full tool call list is emitted at the end of the stream
                tool_renderer.reset()
                print("\n", end="", flush=True)

            # print the actual tokens
            if token_type in ["content", "reasoning"]:
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
