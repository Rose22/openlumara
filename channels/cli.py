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

        # Extract key-value pairs
        # Match "key": "value" or "key": value
        # This regex captures the key, and the value (which might be partial if it's a string)
        pattern = r'"([^"]+)"\s*:\s*(?:"((?:[^"\\]|\\.)*)"?|([^,}\s"]+)?)'
        matches = list(re.finditer(pattern, args_str))

        for match in matches:
            key = match.group(1)
            val = match.group(2) if match.group(2) is not None else match.group(3)
            if val is None:
                val = ""

            previously_printed = self.printed_values.get(key, "")

            if val.startswith(previously_printed):
                to_print = val[len(previously_printed):]
            else:
                # Fallback if the value somehow changed (shouldn't happen in well-formed streams)
                to_print = val

            if key not in self.printed_values:
                # If the parser detects a new key, print its label
                prompt_toolkit.shortcuts.print_formatted_text(
                    prompt_toolkit.formatted_text.HTML(f"\n<ansicyan>{key}:</ansicyan>\n"),
                    end="",
                    flush=True
                )

            if to_print:
                # convert newlines to real newlines
                to_print = to_print.replace("\\n", "\n")

                # Print the streamed value inline
                print(to_print, end="", flush=True)

            self.printed_values[key] = val

    def reset(self):
        """Finalize the tool call block with a newline."""
        if self.current_tool is not None:
            # Just print a newline to finish the inline streaming
            print()
            self.current_tool = None
            self.printed_values = {}

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
        # Create a fresh renderer for this message session
        tool_renderer = ToolCallRenderer()

        async for token in self.send_stream({"role": "user", "content": msg}):
            token_type = token.get("type")
            content = token.get("content", "")

            if token_type == "reasoning" and not message_state:
                self._print_formatted("Reasoning:", "reasoning-label")
                message_state = "reasoning"

            if token_type == "content" and message_state == "reasoning":
                self._print_formatted("\nConclusion:", "conclusion-label")
                message_state = "final output"

            if token_type in ["content", "reasoning"]:
                print(content, end="", flush=True)

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
