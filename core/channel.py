# core
import core
import core.commands

# system
import os
import sys
import time
import json
import asyncio

# parsing stuff
import json_repair
import partial_json_parser
import regex
import base64
import filetype
import io

# an error occurred please try again later
import traceback

def get_available_channels():
    structure = core.config.get_module_structure()
    channels = []
    for name, data in structure.items():
        if data.get("metadata", {}).get("type") in ("channel", "user_channel"):
            channels.append(name)

    return channels

class Channel:
    """Base class for channels"""

    settings = {
        # base settings here lol
    }

    # just like with modules, channels can define python dependencies
    # for the framework to automatically install/uninstall
    dependencies = []

    def __init__(self, manager, is_user_channel=False):
        self.manager = manager
        self.name = core.modules.get_name(self) # shorthand alias
        self.commands = core.commands.Commands(self)
        self._last_cmd_was_temporary = False
        self.context = core.context.Context(self) # each channel has its own context window
        self.console_buffer = [] # used to log system messages

        self.tc_manager = core.toolcalls.ToolcallManager(self)
        self.turncollector = core.turns.TurnCollector()

        # used to track whether to preserve reasoning
        # for only the current "agentic turn"
        # (so that reasoning from older toolcalls can be discarded)
        self.agentic_loop_start: int = -1

        # load channel config
        self.config = core.config.ConfigManager(core.config.config, ["channels" if not is_user_channel else "user_channels", "settings", self.name])

        self._shutting_down = False

        # start the "push queue" which handles messages that are pushed to channels without
        # the user first sending a message. this is what powers announcements and the like
        self.push_queue = asyncio.Queue()
        self._queue_task = None

        # Persistent state for the tool renderer
        self._tool_state = {
            "name": None,
            "raw_args": "",
            "keys_state": {}
        }

    # ------------------
    # Events
    # ------------------
    async def run(self):
        # stub, meant for derivative channels to override
        pass

    async def on_ready(self):
        """
        called when the entire framework has fully initialized
        (when the message "[CORE] Startup complete" shows up)
        """
        pass

    async def _shutdown(self):
        """internal shutdown function. gets called by the manager before on_shutdown()"""

        self._shutting_down = True
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass

    async def on_shutdown(self):
        """overridable method that runs on the channel's shutdown"""
        pass

    async def _push_consumer(self):
        """Consumes messages from the queue and triggers on_push sequentially"""
        while not getattr(self, "_shutting_down", False):
            try:
                message = await self.push_queue.get()
                await self.on_push(self.format_message(message))
                self.push_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Always log full traceback for easier debugging
                self.log(self.name, traceback.format_exc())
                self.log(self.name, f"error in message consumer: {str(e)}")
                await asyncio.sleep(0.5)

    def log(self, category: str, message: str):
        """
        used across the framework to log messages
        basically a drop-in replacement for print()
        will propagate the messages to the console log buffer of all channels
        """
        try:
            self.manager.log(category, message)
        except Exception as e:
            print(f"[FATAL ERROR] failed to send log to channels ({e}): [{category.upper()}] {message}")

    def log_error(self, msg: str, e: Exception):
        """console log but with extra spice for errors"""
        if core.debug:
            self.log("error", f"{msg}: {core.detail_error(e)}")
            self.log("error traceback", traceback.format_exception(e))
        else:
            self.log("error", f"{msg}: {e}")

    def on_log(self, category: str, message: str):
        """
        overridable method that you can use to display logs
        that were broadcasted by self.log()
        for a simple cli channel, we just print()
        """
        pass

    async def _start_push_queue(self):
        if not hasattr(self, "on_push"):
            return
        self._queue_task = asyncio.create_task(self._push_consumer())

    async def on_push(self, message: dict):
        """
        overridable method that should immediately display a message in your channel.
        used by modules all over the framework, such as the scheduler, calendar, and so on,

        to send content to the user without having to prompt the AI
        """
        pass

    async def on_install(self):
        """Overridable method that triggers when the auto-installer installs the dependencies for a channel"""
        pass
    async def on_uninstall(self):
        """Overridable method that triggers when the auto-installer uninstalls the dependencies for a channel"""
        pass

    async def push(self, message):
        """
        push a message to the push queue, which will instantly display it in all channels
        """

        if not hasattr(self, "push_queue"):
            return False

        # message can be either a str or a dict.
        # if dict, just use it as-is
        # otherwise, turn it into an openAI message dict
        if isinstance(message, dict):
            await self.context.chat.add(message)
            await self.push_queue.put(message)
        else:
            await self.context.chat.add({"role": "assistant", "content": str(message)})
            await self.push_queue.put({"role": "assistant", "content": str(message)})

    # --------------------
    # Helper methods
    # --------------------
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # merge the base class's settings with the subclass settings.
        # this way, we can define settings ALL channels should have
        for b in cls.__mro__[1:]:
            if hasattr(b, "settings"):
                cls.settings = b.settings | cls.settings
                break

    async def _set_as_active_channel(self):
        if self.manager.channel is self:
            return
        self.manager.channel = self
        self.manager.savedata["last_channel"] = self.name
        self.manager.savedata.save()

        # give all modules a way to access this channel
        for module_name, module in self.manager.modules.items():
            module.channel = self

    def _extract_content(self, message_dict):
        """helper method that makes sure we always get the text content as a string from the messages array, even if it's multimodal"""
        content = message_dict.get("content")

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # it's multimodal
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text")

        # fallback
        return ""

    # ---------------------
    # Content Processors
    # ---------------------
    async def _process_multimodal(self, message: str = None, files: list = None) -> list:
        """
        Converts a list of file handler objects into an openAI API multimodal message object,
        allowing the AI to process images, audio, etc.

        For sending through send() and send_stream()

        Structure is:
        {
            "my_file.png": (file handler object),
            "my_audio.mp3": (file handler object),
            and so on
        }
        """
        content_blocks = []

        if not message and not files:
            # wtf why would you do that
            return None

        # if no files were provided, just return the content unmodified
        if not files:
            return message

        # otherwise add the text message as a text block
        if message:
            content_blocks.append({"type": "text", "text": message})

        format_map = {
            "audio/wav": "wav", "audio/mp3": "mp3", "audio/mpeg": "mp3",
            "audio/ogg": "ogg", "audio/flac": "flac",
            "audio/webm": "webm", "audio/mp4": "mp4", "audio/aac": "mp4",
        }

        for filename, file_data in files.items():
            if not file_data:
                continue

            kind = filetype.guess(file_data)
            mime_type = kind.mime if kind else "application/octet-stream"

            if mime_type.startswith("image/"):
                b64 = base64.b64encode(file_data).decode("utf-8")
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"}
                })

            elif mime_type.startswith("audio/"):
                b64 = base64.b64encode(file_data).decode("utf-8")
                content_blocks.append({
                    "type": "input_audio",
                    "input_audio": {
                        "data": b64,
                        "format": format_map.get(mime_type, "wav")
                    }
                })

            elif mime_type == "application/pdf":
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(io.BytesIO(file_data))
                    text_parts = []
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                    combined = "\n\n".join(text_parts)
                    content_blocks.append({
                        "type": "text",
                        "text": f"File: {filename}\n\n```pdf\n{combined}\n```"
                    })
                except Exception as e:
                    content_blocks.append({
                        "type": "text",
                        "text": f"[Error extracting PDF '{filename}': {e}]"
                    })

            else:
                try:
                    content_blocks.append({
                        "type": "text",
                        "text": f"File: {filename}\n\n```{file_data.decode('utf-8')}```"
                    })
                except UnicodeDecodeError:
                    content_blocks.append({
                        "type": "text",
                        "text": f"[Binary file: {filename}]"
                    })

        if content_blocks:
            return content_blocks

        return message

    def format_message(self, orig_message: dict):
        formatted = ""

        message = dict(orig_message)

        role = message.get("role")

        show_reasoning = self.config.get("show_reasoning")
        reasoning_content = None

        if role in ("user", "assistant"):
            if show_reasoning:
                reasoning_content = message.get("reasoning_content")
                if reasoning_content:
                    formatted += f"**Reasoning:**\n{reasoning_content}\n\n"

            content = message.get("content")
            if content:
                if reasoning_content and show_reasoning:
                    formatted += "**Conclusion**:\n"

                formatted += f"{content}\n\n"

        if role == "assistant":
            if message.get("tool_calls"):
                for tool_call in message.get("tool_calls"):
                    formatted += self.tc_manager.display_call(tool_call)+"\n"

                formatted += "\n\n"

        if role == "tool":
            formatted = "processing results.."

        message["content"] = formatted.strip()

        return message

    async def _render_tool_token(self, name: str, args_str: str) -> str:
        # 1. Handle tool switch
        if name != self._tool_state["name"]:
            self._tool_state["name"] = name
            self._tool_state["raw_args"] = ""
            self._tool_state["keys_state"] = {}
            return f"\n**Calling tool: {name}**"

        # 2. Parse partial JSON - handles incomplete/malformed streams
        delta = ""
        try:
            data = partial_json_parser.loads(args_str, allow_partial=partial_json_parser.Allow.ALL)
            if not isinstance(data, dict):
                data = {}
        except Exception as e:
            data = {}

        # 3. Delta comparison
        for key, value in data.items():
            val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            prev_val = self._tool_state["keys_state"].get(key)

            if prev_val is None:
                delta += f"\n**{key}**: "
                if val_str:
                    delta += val_str
                self._tool_state["keys_state"][key] = val_str
            elif val_str != prev_val:
                delta += val_str[len(prev_val):] if val_str.startswith(prev_val) else val_str
                self._tool_state["keys_state"][key] = val_str

        self._tool_state["raw_args"] = args_str
        return delta

    # -------------------------
    # The actual sending logic
    # -------------------------
    async def _send_preprocess(self, message: str, files: list = None, commands_authorized = False):
        """
        internal helper function so that send() and send_stream()
        both use many of the same code paths and i don't have to keep maintaining each one individually
        """
        await self._set_as_active_channel()
        user_message = message

        # process any commands
        is_cmd = user_message.strip().lower().startswith(
            core.config.get("core", "cmd_prefix").strip().lower()
        )

        if is_cmd:
            try:
                cmd_response = await self.commands.process_input(user_message, authorized=commands_authorized)
            except Exception as e:
                self.log(self.name, f"Error while executing command: {core.detail_error(e)}")
                await self.context.chat.add({"role": "user", "content": user_message})
                return {"type": "error", "content": str(core.detail_error(e))}

            if cmd_response:
                # process_input already adds to context
                return {"type": "cmd_response", "content": str(cmd_response), "is_cmd": True}
            else:
                return {"type": "blank"}

        # apply any on_user_message() hooks
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_user_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_user_message):
                        usr_msg_result = await module.on_user_message(user_message)
                    else:
                        usr_msg_result = module.on_user_message(user_message)
                except Exception as e:
                    self.log("module error", f"{module_name}: in on_user_message(): {core.detail_error(e)}")

                if usr_msg_result is False:
                    await self.context.chat.add({"role": "user", "content": user_message})
                    return {"type": "module_intercept"}
                elif usr_msg_result is not None:
                    user_message = usr_msg_result

        # apply multimodal content if applicable
        user_message = await self._process_multimodal(message=user_message, files=files)

        # and add the user's message to context
        add_success = await self.context.chat.add({"role": "user", "content": user_message})
        if not add_success:
            return {"type": "error", "content": "Unknown error while adding user message to context"}

        # reconnect if needed
        result = await self.manager.API.attempt_connect()
        if result is not True:
            return {"type": "error", "content": str(result)}

        # build the context window
        context = await self.context.get(system_prompt=True, end_prompt=True)

        # and return the results for use in send() and send_stream()
        return {"type": "ready", "user_message": user_message, "context": context}

    async def _send_postprocess(self, assistant_message):
        await self.context.chat.add(assistant_message)

        # run module event hooks
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_assistant_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_assistant_message):
                        await module.on_assistant_message(assistant_message.get("content", ""))
                    else:
                        module.on_assistant_message(assistant_message.get("content", ""))
                except Exception as e:
                    self.log("module error", f"{module_name}: in on_assistant_message(): {core.detail_error(e)}")

    def _build_final_assistant_message(self, final_content = [], final_reasoning = []):
        assistant_message = {
            "role": "assistant",
            "content": "".join(final_content)
        }

        if final_reasoning:
            assistant_message["reasoning_content"] = "".join(final_reasoning)

        return assistant_message

    async def throw_stream_error(self, error):
        """
        helper method to make throwing errors during a stream consistent
        since it's easy to forget to add an error to context in addition to yielding it..
        """
        # add the error message to context
        await self.context.chat.add({"role": "assistant", "content": f"Error: {error}"})

        # and pass it on to yield
        return {"type": "error", "content": error}

    async def send(self, message: str, files: list = None, commands_authorized=False):
        """sends a message to the AI from within the current channel"""

        # preprocessing (API connection logic, command processing, user message module hooks, etc)
        processed = await self._send_preprocess(message, files, commands_authorized)
        match processed["type"]:
            case "cmd_response":
                return self.format_message({"role": "assistant", "content": processed["content"]})
            case "blank":
                return
            case "module_intercept":
                return
            case "error":
                return {"role": "assistant", "content": processed["content"]}

        # request the AI response and add it to context
        response = await self.manager.API.send(processed["context"])

        # handle any errors
        if isinstance(response, core.api.APIError):
            self.log("api", response)
            return {"role": "assistant", "content": str(response)}

        # make a copy of the response message and edit it
        assistant_message = dict(response)
        assistant_message["role"] = "assistant"

        tool_calls = assistant_message.get("tool_calls")
        if tool_calls:
            # process() does all the toolcalling, but it also returns the raw toolcall stream for our own use
            async for sub_token in self.tc_manager.process(
                assistant_message,
                push=True
            ):
                # push handles all the output
                pass

            return None

        # postprocessing ( mainly assistant message module hooks, but this can be extended later :) )
        await self._send_postprocess(assistant_message)
        return self.format_message(assistant_message)

    async def send_stream(self, message: str, files: list = None, commands_authorized=False):
        """sends a message to the AI from within the current channel, streaming version"""

        # preprocessing (API connection logic, command processing, user message module hooks, etc)
        processed = await self._send_preprocess(message, files, commands_authorized)

        match processed["type"]:
            case "cmd_response":
                # immediately yield both the user message and the command response, so that they both display
                yield {"type": "user_message", "content": message, "is_cmd": True}
                yield {"type": "content", "content": processed["content"], "is_cmd": True}
                return
            case "blank":
                yield {"type": "content", "content": "BLANK"}
                return
            case "module_intercept":
                # let modules intercept messages, stopping the rest of the chain and doing whatever with the contents of the message
                # in on_user_message()
                return
            case "error":
                yield await self.throw_stream_error(processed["content"])
                return

        user_message = processed.get("user_message") #alias for readability

        # yield user message as a special token for display in UI's (because user message can be modified by module hooks)
        yield {"type": "user_message", "content": user_message}
        
        # estimate tokens used for user message
        user_message_token_estimation = 0
        if self.context.chat.using_api_token_data:
            # if using API token count
            user_msg_tokens = await self.context.chat.count_tokens([{"role": "user", "content": user_message}])
            user_message_token_estimation = await self.context.chat.get_token_usage()+user_msg_tokens

            # add to existing API token count
            await self.context.chat.set_token_usage(user_message_token_estimation)
        else:
            # just fully estimate
            try:
                user_message_token_estimation = await self.context.chat.count_tokens()
            except Exception as e:
                self.log_error("Error while trying to estimate token use", e)
                yield await self.throw_stream_error(f"Error while trying to estimate token use: {core.detail_error(e)}")
                # abort
                return

        # yield so it updates throughout all channels that display token count
        yield {"type": "token_usage", "content": user_message_token_estimation, "source": "estimation"}

        final_content = []
        final_reasoning = []
        tc_response = None
        tool_calls_occurred = False
        fetched_token_usage = False

        # and stream the response to the caller of this method
        try:
            stream = self.manager.API.send_stream(processed.get("context"))
        except Exception as e:
            yield await self.throw_stream_error(f"Error while starting stream: {core.detail_error(e)}")
            return

        async for token in stream:
            # always yield the token to the caller
            yield token

            token_type = token.get("type")

            # handle any errors
            if token_type == "error":
                self.log(self.name, f"Error: {token.get('content')}")
                yield token

                # add the content that has been accumulated so far, so that we don't lose incomplete messages
                assistant_message = self._build_final_assistant_message(final_content, final_reasoning)
                await self.context.chat.add(assistant_message)

                return

            if token_type == "content":
                # this is a normal piece of streamed text
                final_content.append(token.get("content"))
            elif token_type == "reasoning":
                final_reasoning.append(token.get("content"))
            elif token_type == "tool_call_delta":
                # yay toolcall arg streaming!
                pass
            elif token_type == "tool_calls":
                tool_calls_occurred = True

                toolcall_request = await self.tc_manager._build_recursive_request(token, final_content, final_reasoning)

                # we add the accumulated content tokens so far to the assistant_content argument
                async for sub_token in self.tc_manager.process(toolcall_request):
                    yield sub_token
                # tc_manager.process() will loop until the AI no longer deems tool calls necessary
            elif token_type == "tool":
                # this is a toolcall response
                pass
            elif token_type == "token_usage":
                # this is the final token usage count, usually emitted at the end of the stream
                token_usage = token.get("content")
                if isinstance(token_usage, int):
                    # set the flag so that token counting is always using API data
                    if not self.context.chat.using_api_token_data:
                        self.context.chat.using_api_token_data = True

                    # cache this so chat.get_token_usage() returns this value
                    await self.context.chat.set_token_usage(token_usage)

                    fetched_token_usage = True

        if not fetched_token_usage:
            # yield an estimated token usage if the API didn't provide one
            yield {"type": "token_usage", "content": await self.context.chat.count_tokens(), "source": "estimation"}

        if not tool_calls_occurred and final_content: # don't add an extra message at the end of a toolcalling chain
            assistant_message = self._build_final_assistant_message(final_content, final_reasoning)
            await self._send_postprocess(assistant_message)

    async def format_stream_for_text(self, stream, chunk_size=None, use_markdown=True, strings: dict = None):
        """
        helper function so that channels don't need to implement this themselves...
        takes care of properly displaying all the agentic turns
        and nicely formatting it so it looks close to the webUI's presentation of it
        """
        def text_to_token(text):
            return {"type": "content", "content": text}

        currently_reasoning = False
        show_reasoning = self.config.get("show_reasoning")
        last_token_was_newline = False
        char_counter = 0

        if not strings:
            if use_markdown:
                strings = {
                    "thinking_header": "**Thinking**",
                    "thinking_str": "*thinking..*",
                    "conclusion_header": "**Conclusion**",
                    "processing_tool": "(processing results..)",
                    "thinking_newline": "\n> "
                }
            else:
                strings = {
                    "thinking_header": "--- Thinking ---",
                    "thinking_str": "thinking..",
                    "conclusion_header": "--- Conclusion ---",
                    "processing_tool": "\n(processing results..)",
                    "thinking_newline": "\n"
                }

        string_type = "markdown" if use_markdown else "no_markdown"

        async for token in stream:
            token_type = token.get("type")
            content = token.get("content", "")

            if token_type == "prompt_progress":
                yield token

            # # collapse consecutive newlines
            try:
                # format the reasoning to look all fancy
                if show_reasoning:
                    newline_str = "\n" if not currently_reasoning else strings["thinking_newline"]
                else:
                    newline_str = "\n"

                # collapse more than 2 newlines to just 2
                content = regex.sub(r'\n{3,}', '\n\n', content)
                content = content.replace("\n", newline_str)
            except:
                pass

            # ensure formatting displays correctly even when split into chunks
            if chunk_size and char_counter >= chunk_size:
                # signal to our caller that we're starting a new chunk
                yield {"type": "new_chunk", "content": ""}
                char_counter = 0

                if currently_reasoning and show_reasoning and use_markdown:
                    yield text_to_token("> ")
                    char_counter += len("> ") # what we just emitted counts as a token

            # show thinking header
            if token_type == "reasoning" and not currently_reasoning:
                if show_reasoning:
                    # think_str = "\n## Thinking:\n> "
                    think_str = strings["thinking_header"]
                else:
                    think_str = strings["thinking_str"]
                currently_reasoning = True

                char_counter += len(think_str)
                yield text_to_token(think_str)

                char_counter += len(strings["thinking_newline"])
                yield text_to_token(strings["thinking_newline"])

            # show conclusion header
            if token_type == "content" and show_reasoning and currently_reasoning:
                header_str = "\n"+strings["conclusion_header"]
                if use_markdown:
                    # add an extra newline for markdown's newline quirks
                    header_str = "\n"+header_str

                char_counter += len(header_str)
                yield text_to_token(header_str)

                char_counter += len("\n")
                yield text_to_token("\n")

            if token_type in ["content", "tool_calls", "tool"] and currently_reasoning:
                # we can have multiple reasoning blocks
                currently_reasoning = False

            # show tool result text
            # if token_type == "tool":
            #     tool_result_str = strings["processing_tool"]
            #     char_counter += len(tool_result_str)
            #     yield text_to_token(tool_result_str)

            if self.config.get("stream_tool_calls") and token_type == "tool_call_delta":
                # Extract the accumulated tool call from the delta
                tc_list = token.get("tool_calls", [])
                if tc_list:
                    tc = tc_list[0]
                    # Render the partial/full tool call fancy style
                    tool_delta_str = await self._render_tool_token(tc.function.name, tc.function.arguments)

                    # fix fake newlines
                    tool_delta_str = tool_delta_str.replace("\\n", "\n")

                    char_counter += len(tool_delta_str)
                    yield text_to_token(tool_delta_str)
            elif token_type == "tool":
                char_counter += len("\n\n")
                yield text_to_token("\n\n")
            elif not self.config.get("stream_tool_calls") and token_type == "tool_calls":
                char_counter += len("\n")
                yield text_to_token("\n")

                tool_calls = token.get("tool_calls")
                for tool_call in tool_calls:
                    tool_str = self.tc_manager.display_call(tool_call)+"\n"
                    char_counter += len(tool_str)
                    yield text_to_token(tool_str)

                yield text_to_token("\n")
                char_counter += len("\n")

            if token_type == "content":
                yield text_to_token(content)
                char_counter += len(content)
            if token_type == "reasoning" and show_reasoning:
                char_counter += len(content)
                yield text_to_token(content)

    async def group_stream(self, stream):
        """
        groups incoming tokens into "turns" using the TurnCollector defined in core/turns.py

        a turn is a group of assistant messages, such as reasoning, content, toolcalls, and so on,
        that have all been grouped together into one object, for display in your preferred UI.

        this used to be exclusive to the webUI, but i've ported it over to the core, so that it
        can be reused across channels
        """
        async for partial_turn in self.turncollector.group_stream(stream):
            yield partial_turn

    async def group_history(self):
        """
        takes a list of messages and turns it into turns that are identical to the ones shown by get_turns_stream()
        for displaying message history in the same grouped turns format
        """
        return self.turncollector.group_history(await self.context.chat.get())
