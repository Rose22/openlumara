import os
import regex as re
import sys
import json
import time

# readline does not exist on windows
if sys.platform != "win32":
    import readline

import asyncio
import random
import concurrent.futures

# prompt toolkit for better input, async prompting, command history, and so on
import pygments.lexers

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
import rich.box
import rich.panel
import rich.padding
import rich.progress
import rich.markdown
import rich.live
import rich.syntax
import rich.traceback

# openlumara core
import core

def plaintext(text):
    """helper that makes the Rich library not auto-color text"""

    return rich.text.Text(text)


# step-based live view, powered by core/turns.py step events.
STATUS_ICONS = {
    "thinking": ("◐", "dim"),
    "running": ("⚙", "dim"),
    "done": ("✓", "green"),
    "failed": ("✗", "red"),
    "thoughts": ("·", "dim"),
}

# braille frames of rich's "dots" spinner
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# tools whose code arguments deserve highlighting, and which of their
# arguments are code (create streams one new blob, edit a before/after pair)
CODE_ARGS_BY_TOOL = {
    "coder_file_create": ("content",),
    "coder_file_edit": ("original_code", "replacement_code"),
}

# file extension -> lexer name, mirroring the coder webui's READ_LANG_BY_EXT
# map (modules/coder/webui/assets/js/custom_tool_views/shared.js)
LEXER_BY_EXT = {
    "py": "python", "js": "javascript", "mjs": "javascript", "ts": "typescript",
    "json": "json", "html": "html", "xml": "xml", "css": "css", "scss": "scss",
    "yml": "yaml", "yaml": "yaml", "md": "markdown", "rs": "rust", "go": "go",
    "c": "c", "h": "c", "cpp": "cpp", "hpp": "cpp", "sh": "bash", "bash": "bash",
    "toml": "ini", "ini": "ini", "sql": "sql", "java": "java", "rb": "ruby",
    "php": "php", "txt": "text",
}

def tail_text(text, max_lines):
    """last max_lines lines of text, with a .. marker when lines were dropped.
    max_lines of 0 means show everything."""
    if not text:
        return ""
    
    lines = text.rstrip().splitlines()
    if max_lines and len(lines) > max_lines:
        return ".." + "\n" + "\n".join(lines[-max_lines:])
    
    return "\n".join(lines)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u2026])\s+")

def thought_snippet(text, limit=80):
    """one-line summary of a step's reasoning"""
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return ""

    parts = SENTENCE_SPLIT.split(t)
    s = parts[-1].strip()
    if len(s) <= limit:
        return s

    win = s[:limit]
    # greedy: matches up through the LAST sentence end inside the window
    term = re.match(r"^[\s\S]*[.!?\u2026](?=\s|$)", win)
    if term and len(term.group(0)) >= 12:
        return term.group(0).strip()

    sp = win.rfind(" ")
    head = win[:sp] if sp > 20 else win[:limit - 1]
    return head.rstrip() + "\u2026"

class StepTreeView:
    # live previews stay short so the live area never balloons past the screen
    LIVE_REASONING_LINES = 5
    LIVE_CONTENT_LINES = 5
    LIVE_FINAL_LINES = 12
    LIVE_ARG_LINES = 6

    def __init__(self, channel):
        self.channel = channel
        self.steps = {}
        self.order = []
        self.final_messages = []
        self.progress = None
        self.progress_task = None
        self.show_progress = False
        # the live area repaints far faster than tokens arrive, so only
        # re-parse a region when its text actually changed
        self.md_cache = {}
        # same trick for highlighted code, keyed per tool call
        self.syntax_cache = {}
        # fitted-live-render memo
        self.dirty = 0
        self.render_cache = None

    def _md(self, key, source):
        cached = self.md_cache.get(key)
        if cached is not None and cached[0] == source:
            return cached[1]
        
        rendered = rich.markdown.Markdown(source)
        self.md_cache[key] = (source, rendered)
        return rendered

    def _get_progress(self):
        if self.progress is None:
            self.progress = rich.progress.Progress(expand=False, auto_refresh=False)
            self.progress_task = None
            
        return self.progress

    def set_progress(self, desc, percent):
        progress = self._get_progress()
        accent = self.channel._get_accent_color()
        desc = f"[{accent}]{desc}[/]"

        # total=1 with a fraction, exactly like the classic handler
        if self.progress_task is None:
            if percent is None:
                self.progress_task = progress.add_task(desc, total=None)
            else:
                self.progress_task = progress.add_task(desc, completed=percent / 100, total=1)
        elif percent is None:
            progress.update(self.progress_task, description=desc, completed=None, total=None)
        else:
            progress.update(self.progress_task, description=desc, completed=percent / 100, total=1)
            
        self.show_progress = True
        self.dirty += 1

    def update_step(self, step):
        num = step.get("step") or 0
        if num not in self.steps:
            self.order.append(num)
        self.steps[num] = step
        
        # real content arrived: any progress bar is obsolete now
        self.show_progress = False
        self.dirty += 1

    def set_final(self, messages):
        self.final_messages = messages or []
        self.dirty += 1

    def _tool_line(self, tool):
        meta = tool.get("_metadata") or {}
        name = meta.get("display_name") or (tool.get("function") or {}).get("name") or "unknown"
        done = meta.get("response") is not None
        failed = meta.get("failed")

        line = rich.text.Text("  🔧 ")
        line.append(name, style="bold red" if failed else "bold")

        summary = meta.get("summary") or ""
        if summary and (done or self.channel.config.get("stream_tool_calls")):
            line.append(summary, style="dim")

        result = meta.get("result_summary") or ""
        if result:
            line.append("  → " + result, style="red" if failed else "dim green")
        elif not done:
            line.append(" ..", style=self.channel._get_accent_color())

        return line

    def _syntax(self, tool_id, path, code):
        """syntax highlighting"""
        cached = self.syntax_cache.get(tool_id)
        if cached is not None and cached[0] == code:
            return cached[1]

        name = ""
        if path and "." in path:
            name = LEXER_BY_EXT.get(path.rsplit(".", 1)[-1].lower(), "")

        # validate the name resolves in this pygments version (typescript
        # etc. may be missing on older installs) before handing it to rich
        if name:
            try:
                pygments.lexers.get_lexer_by_name(name)
            except Exception:
                name = ""
        if not name:
            try:
                name = pygments.lexers.guess_lexer_for_filename(path or "x.py").name
            except Exception:
                name = "text"

        # background_color=default: the border does the framing, so the
        # theme's solid block background is off
        rendered = rich.syntax.Syntax(code, name, word_wrap=False, background_color="default")
        self.syntax_cache[tool_id] = (code, rendered)
        return rendered

    def _arg_lines(self, tool):
        """parses streaming toolcalls"""
        meta = tool.get("_metadata") or {}
        args = meta.get("args_parsed") or {}

        tool_name = meta.get("display_name") or (tool.get("function") or {}).get("name")
        code_args = CODE_ARGS_BY_TOOL.get(tool_name) or ()

        lines = []
        for key, value in args.items():
            if key == "_raw":
                continue
            if isinstance(value, (dict, list)):
                text = json.dumps(value, indent=2)
            elif value is None:
                text = "null"
            elif isinstance(value, bool):
                text = "true" if value else "false"
            else:
                text = str(value)

            shown = tail_text(text, self.LIVE_ARG_LINES)

            # code args get their own highlighted block under the label,
            # framed in a rounded border in the accent color
            if key in code_args:
                lines.append(rich.text.Text(f"      {key}:", style="dim"))
                # cache per call AND arg: an edit streams two blocks with
                # the same tool call id
                syntax = self._syntax(f"{tool.get('id') or tool_name}:{key}", args.get("path") or "", shown)
                accent = self.channel._get_accent_color()
                panel = rich.panel.Panel(syntax, box=rich.box.ROUNDED, border_style=accent, padding=(0, 1))
                lines.append(rich.padding.Padding(panel, (0, 0, 0, 4)))
                continue

            first = True
            for ln in shown.splitlines():
                arg = rich.text.Text()
                if first:
                    arg.append(f"      {key}: ", style="dim")
                    first = False
                else:
                    arg.append("            ")
                arg.append(ln)
                lines.append(arg)
        return lines

    def _modules_text(self, step):
        # module chips: "Coder: file edit x2, Shell: run"
        groups = []
        for group in step.get("modules") or []:
            actions = []
            for action in group.get("actions") or []:
                name = (action.get("name") or "").replace("_", " ")
                if not name:
                    continue
                    
                count = action.get("count") or 1
                if count > 1:
                    name += f" x{count}"
                    
                actions.append(name)
                
            if actions:
                groups.append(f"{group.get('module')}: {', '.join(actions)}")
                
        return ", ".join(groups)

    def _header_segments(self, step):
        reasoning = (step.get("reasoning_content") or "").strip()
        mods = self._modules_text(step)

        segments = []
        if reasoning:
            if step.get("reasoning_live"):
                segments.append(("Thinking..", "italic"))
            else:
                segments.append((thought_snippet(reasoning), ""))
            return segments, mods

        if not mods:
            if step.get("reasoning_live"):
                segments.append(("Thinking..", "italic"))
            else:
                segments.append(("writing", "dim"))

        tool_calls = step.get("tool_calls") or []
        if len(tool_calls) == 1:
            meta = tool_calls[0].get("_metadata") or {}
            summary = meta.get("summary") or ""
            
            if summary:
                segments.append((" " + summary, "dim"))
            result = meta.get("result_summary") or ""
            
            if result:
                segments.append(("  \u2192 " + result, "dim green"))
        return segments, mods

    def _step_lines(self, step, live):
        accent = self.channel._get_accent_color()
        show_reasoning = self.channel.config.get("show_reasoning")
        is_tail = bool(step.get("is_tail"))

        status = step.get("status") or "thinking"
        if status == "thinking":
            # animated spinner while the model reasons
            icon = SPINNER_FRAMES[int(time.monotonic() * 8) % len(SPINNER_FRAMES)]
            icon_style = accent
        else:
            icon, icon_style = STATUS_ICONS.get(status, ("·", "dim"))

        segments, mods = self._header_segments(step)

        header = rich.text.Text()
        header.append(f" {icon} ", style=icon_style)
        for i, (text, style) in enumerate(segments):
            if i == 0 and is_tail:
                style = (style + " " if style else "") + accent
            header.append(text, style=style)

        # module chips pinned to the right edge of the terminal; the left
        # part is ellipsis-truncated (and padded) to make room for them
        if mods:
            right_len = len(mods) + 1
            avail = self.channel.console.width - right_len
            header.truncate(max(avail, 8), overflow="ellipsis", pad=True)
            header.append(" " + mods, style="dim")

        lines = [header]

        reasoning = step.get("reasoning_content") or ""
        content = step.get("content") or ""
        tool_lines = [self._tool_line(t) for t in step.get("tool_calls") or []]

        if live:
            # only the open (tail) step stays expanded
            if is_tail:
                if show_reasoning and reasoning.strip():
                    for ln in tail_text(reasoning, self.LIVE_REASONING_LINES).splitlines():
                        lines.append(rich.text.Text("     " + ln, style="dim italic"))
                if content.strip():
                    md = self._md(("step", step.get("step")), tail_text(content, self.LIVE_CONTENT_LINES))
                    lines.append(rich.padding.Padding(md, (0, 0, 0, 4)))

                for tool, tool_line in zip(step.get("tool_calls") or [], tool_lines):
                    lines.append(tool_line)
                    # stream the args of calls still being written
                    streaming = (tool.get("_metadata") or {}).get("response") is None
                    if streaming and self.channel.config.get("stream_tool_calls"):
                        lines.extend(self._arg_lines(tool))
            return lines

        if show_reasoning and reasoning.strip():
            for ln in reasoning.rstrip().splitlines():
                lines.append(rich.text.Text("     " + ln, style="dim italic"))
        if content.strip():
            md = self._md(("step", step.get("step")), content.rstrip())
            lines.append(rich.padding.Padding(md, (0, 0, 0, 4)))
        if step.get("status") == "failed":
            lines.extend(tool_lines)
        return lines

    def render(self, live=True):
        cache_key = None
        if live:
            cache_key = (self.dirty, int(time.monotonic() * 8), self.channel.console.height)
            if self.render_cache is not None and self.render_cache[0] == cache_key:
                return self.render_cache[1]

        lines = []

        for num in self.order:
            lines.extend(self._step_lines(self.steps[num], live))

        # progress bar under the step list
        if self.show_progress and self.progress is not None:
            lines.append(self.progress)

        if live:
            for i, message in enumerate(self.final_messages):
                content = message.get("content") or ""
                if not content.strip():
                    continue
                if message.get("is_cmd"):
                    for ln in tail_text(content, self.LIVE_FINAL_LINES).splitlines():
                        lines.append(rich.text.Text(ln))
                else:
                    lines.append(self._md(("final", i), tail_text(content, self.LIVE_FINAL_LINES)))

        if not lines:
            return rich.text.Text("")
        
        if live:
            lines = self._fit_viewport(lines)
            group = rich.console.Group(*lines)
            self.render_cache = (cache_key, group)
            return group
        
        return rich.console.Group(*lines)

    def final_answer_messages(self):
        return [m for m in self.final_messages if (m.get("content") or "").strip()]

    def _height(self, renderables):
        total = 0
        for renderable in renderables:
            total += len(self.channel.console.render_lines(renderable))
        return total

    def _fit_viewport(self, lines):
        heights = [self._height([ln]) for ln in lines]
        budget = self.channel.console.height - 1

        total = sum(heights)
        dropped = 0
        if total > budget:
            # the ".. N lines above" marker itself costs a line
            while total + 1 > budget and len(lines) > 1:
                total -= heights.pop(0)
                lines.pop(0)
                dropped += 1
            lines.insert(0, rich.text.Text(f"  .. {dropped} lines above", style="dim"))
        return lines

class Cli(core.channel.Channel):
    """A CLI channel for openlumara"""

    running = True

    settings = {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": True
        },
        "show_steps": {
            "description": "Show the AI's process as a live-updating list of steps instead of a flat text stream",
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

    async def on_system_prompt(self):
        return "This channel does not support markdown."

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

    async def on_stream(self, stream):
        if self.config.get("show_steps"):
            return await self._on_stream_steps(stream)
        return await self._on_stream_classic(stream)

    # step-based streaming via core/turns.py, rendered live with rich.live.
    async def _on_stream_steps(self, stream):
        accent_color = self._get_accent_color()
        view = StepTreeView(self)

        live = None
        def repaint():
            nonlocal live
            if live is None:
                live = rich.live.Live(
                    view.render(live=True),
                    console=self.console,
                    refresh_per_second=60,
                    transient=True,
                    vertical_overflow="ellipsis",
                )
                live.start()
            else:
                live.update(view.render(live=True))

        cancelled = False
        error_text = None

        try:
            async for event in self.turncollector.group_stream(stream):
                event_type = event.get("type")

                if event_type == "step":
                    view.update_step(event.get("content"))
                    repaint()
                elif event_type == "final":
                    view.set_final(event.get("content") or [])
                    repaint()
                else:
                    token = event.get("content") or {}
                    token_type = token.get("type")

                    if token_type == "prompt_progress":
                        progress = token.get("content") or {}
                        view.set_progress("Processing..", progress.get("percent"))
                        repaint()
                    elif token_type == "model_load_progress":
                        content = token.get("content") or {}
                        model_name = (content.get("model") or "").split("/")[-1]
                        labels = {"queued": "Queued", "downloading": "Downloading"}
                        label = labels.get(content.get("status"), "Loading")
                        desc = f"{label} {model_name}" if model_name else f"{label} model"
                        view.set_progress(desc, content.get("percent"))
                        repaint()
                    elif token_type == "error":
                        error_text = token.get("content")
                        break
                    # user_message / token_usage / timings: nothing to render
        except asyncio.CancelledError:
            cancelled = True
        except KeyboardInterrupt:
            cancelled = True
        finally:
            if live is not None:
                live.stop()
            self._token_usage = await self.context.get_total_tokens()

        # permanent reprint: the settled step tree first,
        # then the answer itself
        if view.order:
            self.console.print(view.render(live=False))
            self.console.print()

        if error_text is not None:
            self.console.print(f"[red][bold]ERROR:[/bold] {error_text}[/red]")
            return
        if cancelled:
            self.console.print(f"[{accent_color}]cancelled.[/]")
            return

        printed_any = False
        for message in view.final_answer_messages():
            content = message.get("content") or ""
            if message.get("is_cmd"):
                self.console.print(plaintext(content))
            else:
                self.console.print(rich.markdown.Markdown(content))
            printed_any = True

        if printed_any:
            self.console.print()

    async def _on_stream_classic(self, stream):
        accent_color = self._get_accent_color()

        processing_prompt = False
        first_processing_prompt = True
        progress = rich.progress.Progress(expand=False, transient=False)
        progress_task = None

        # tracks whether we're tracking llamacpp router model loading progress,
        # or prompt processing progress
        bar_mode = None

        def show_bar(mode, description):
            nonlocal processing_prompt, progress_task, first_processing_prompt, bar_mode

            if not processing_prompt:
                if not first_processing_prompt:
                    # create a newline so that the progress bar doesnt replace the content
                    self.console.print()
                first_processing_prompt = False

                progress.start()
                progress_task = progress.add_task(f"[{accent_color}]{description}", total=1)
                processing_prompt = True
            elif bar_mode != mode:
                progress.update(progress_task, description=f"[{accent_color}]{description}")

            bar_mode = mode

        def hide_bar():
            nonlocal processing_prompt, progress_task, bar_mode

            if processing_prompt:
                # remove the progress bar upon receival of the first non-progress token
                progress.remove_task(progress_task)
                progress.stop()
                processing_prompt = False
                bar_mode = None

        # sending_prompt = True
        # sending = rich.status.Status("Sending", console=self.console)
        # sending.start()

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

        final_reasoning = []
        final_content = []

        try:
            async for token in self.format_stream_for_text(
                stream,
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

                # if sending_prompt:
                #     sending.stop()
                #     sending_prompt = False

                if token_type == "prompt_progress":
                    show_bar("prompt", "Processing..")

                    cache = token_content.get("cache") or 0
                    processed = (token_content.get("processed") or 0) - cache
                    total = (token_content.get("total") or 0) - cache

                    progress.update(progress_task, completed=(processed / total) if total > 0 else 0, refresh=True)
                elif token_type == "model_load_progress":
                    model_name = (token_content.get("model") or "").split("/")[-1]

                    labels = {
                        "queued": "Queued",
                        "downloading": "Downloading",
                    }
                    label = labels.get(token_content.get("status"), "Loading")

                    desc = f"{label} {model_name}" if model_name else f"{label} model"

                    # stage = token_content.get("stage") or ""
                    # if stage:
                    #     desc += f" · {stage.replace('_', ' ')}"

                    show_bar("model_load", desc)

                    percent = token_content.get("percent")
                    progress.update(progress_task, completed=(percent / 100) if percent is not None else 0, refresh=True)
                elif processing_prompt:
                    hide_bar()

                if token_type == "reasoning":
                    final_reasoning.append(token_content)
                elif token_type == "content":
                    final_content.append(token_content)

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
            return
        except KeyboardInterrupt:
            self.console.print(f"\n[{accent_color}]cancelled.[/]")
            return
        finally:
            progress.stop()
            # sending.stop()

            if not show_reasoning:
                reasoning_indicator.stop()

            self._token_usage = await self.context.get_total_tokens()

        self.console.print()

        msg = {"role": "assistant"}
        if final_reasoning:
            msg["reasoning_content"] = "".join(final_reasoning)
        if final_content:
            msg["content"] = "".join(final_content)

        return msg

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

        while self.running:
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

            await self.push_stream(
                self.send_stream(user_input, commands_authorized=True)
            )

    async def on_shutdown(self):
        # stop the input loop so that run() exits cleanly
        self.running = False

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
