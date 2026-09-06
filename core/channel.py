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
        # the path to a channel's chat is: channel -> context -> chat

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

    async def init(self):
        """async class constructor. gets called by manager._load_channels()"""
        await self.context.chat.autoload()

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

        # flush any debounced message saves so nothing is lost
        try:
            await self.context.chat.messages.save()
        except Exception as e:
            self.log("core", f"error flushing message saves during shutdown: {e}")

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
            await self.context.chat.messages.add(message)
            await self.push_queue.put(message)
        else:
            await self.context.chat.messages.add({"role": "assistant", "content": str(message)})
            await self.push_queue.put({"role": "assistant", "content": str(message)})

    async def announce(self, message: str, type: str = "info"):
        """
        Convenience helper to announce a message across the channel or push queue.
        Supports channels defining custom _announce handlers (e.g. Matrix).
        """
        if hasattr(self, "_announce") and callable(self._announce):
            return await self._announce(message, type=type)
        return await self.push(message)

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

        # if the message was a list... this was already multimodal, so dont modify
        if isinstance(message, list):
            return {"role": "user", "content": message}

        if not message and not files:
            # wtf why would you do that
            return None

        # if no files were provided, just return the content unmodified
        if not files:
            return {"role": "user", "content": message}

        filenames = []

        # otherwise add the text message as a text block
        if message:
            content_blocks.append({"type": "text", "text": message})
            filenames.append("") # so that indexes match

        format_map = {
            "audio/wav": "wav", "audio/mp3": "mp3", "audio/mpeg": "mp3",
            "audio/ogg": "ogg", "audio/flac": "flac",
            "audio/webm": "webm", "audio/mp4": "mp4", "audio/aac": "mp4",
        }

        message_dict = {"role": "user"}

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

            filenames.append(filename)

        if content_blocks:
            message_dict["content"] = content_blocks
            message_dict["_metadata"] = {"filenames": filenames}
            return message_dict

        return {"role": "user", "content": message}

    def format_message(self, orig_message: dict):
        if not orig_message:
            return {"role": "assistant", "content": ""}

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

        # sometimes legacy parts of the openlumara framework still send dicts.
        # that is not supposed to happen, and i need to find the code that does it
        # so, TODO: find the legacy code that calls channel.send()/send_stream() with dicts
        # but for now.. to avoid breaking everything, i'll convert
        if isinstance(user_message, dict):
            user_message = user_message.get("content", "")

        if isinstance(user_message, str):
            # process any commands
            is_cmd = user_message.strip().lower().startswith(
                core.config.get("core", "cmd_prefix").strip().lower()
            )

            if is_cmd:
                try:
                    cmd_response = await self.commands.process_input(user_message, authorized=commands_authorized)
                except Exception as e:
                    self.log(self.name, f"Error while executing command: {core.detail_error(e)}")
                    # no need to add a message to context here, as process_input() already does that
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
                        await self.context.chat.messages.add({"role": "user", "content": user_message})
                        return {"type": "module_intercept"}
                    elif usr_msg_result is not None:
                        user_message = usr_msg_result

        # apply multimodal content if applicable
        user_message_processed = await self._process_multimodal(message=user_message, files=files)

        # and add the user's message to context
        add_success = await self.context.chat.messages.add(user_message_processed)
        if not add_success:
            return {"type": "error", "content": "Unknown error while adding user message to context"}

        # reconnect if needed
        result = await self.manager.API.attempt_connect()
        if result is not True:
            return {"type": "error", "content": str(result)}

        # build the context window
        context = await self.context.get(system_prompt=True, end_prompt=True)

        # and return the results for use in send() and send_stream()
        return {"type": "ready", "user_message": user_message_processed.get("content"), "context": context}

    async def _send_postprocess(self, assistant_message):
        await self.context.chat.messages.add(assistant_message)

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

    def _build_final_assistant_message(self, final_content = None, final_reasoning = None):
        # python has a bug where, if you pass a default value in the function definition,
        # all calls to the function then share the reference to that value,
        # which, well, pollutes future calls...

        if final_content is None:
            final_content = []
        if final_reasoning is None:
            final_reasoning = []

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
        await self.context.chat.messages.add({"role": "assistant", "content": f"Error: {error}"})

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
        # this also adds the user's message to context, so we don't need to do that in this function
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
                # immediately yield the user message
                yield {"type": "user_message", "content": message, "is_cmd": True}
                yield await self.throw_stream_error(processed["content"])
                return

        user_message = processed.get("user_message") #alias for readability

        # yield user message as a special token for display in UI's (because user message can be modified by module hooks)
        yield {"type": "user_message", "content": user_message}
        
        # estimate tokens used for user message.
        # the context was just built in _send_preprocess, so count it directly
        # instead of rebuilding the whole thing via get_total_tokens()
        user_message_token_estimation = 0
        try:
            user_message_token_estimation = await self.context.count_tokens(processed.get("context"))
            if self.manager.tools:
                user_message_token_estimation += await self.context.count_tokens(self.manager.tools)
        except Exception as e:
            self.log_error("Error while trying to estimate token use", e)
            yield await self.throw_stream_error(f"Error while trying to estimate token use: {core.detail_error(e)}")
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

        try:
            async for token in stream:
                token_type = token.get("type")

                # handle any errors
                if token_type == "error":
                    self.log(self.name, f"Error: {token.get('content')}")

                    # add the content that has been accumulated so far, so that we don't lose incomplete messages
                    assistant_message = self._build_final_assistant_message(final_content, final_reasoning)
                    await self.context.chat.messages.add(assistant_message)

                    yield await self.throw_stream_error(token.get("content"))
                    return

                # always yield the token to the caller
                yield token

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

                    # the AI has decided to call a tool, so now we start the recursive toolcall loop (aka agentic loop)
                    # AI calls tool -> gets response -> decides whether it needs to call more tools -> does so if needed -> gets response -> rinse and repeat
                    async for sub_token in self.tc_manager.process(toolcall_request):
                        if sub_token.get("type") == "final":
                            # this is the final message in the recursive toolcalling loop, so we add it to context
                            await self.context.chat.messages.add(sub_token.get("content"))

                        yield sub_token
                elif token_type == "tool":
                    # this is a toolcall response.. we only need to yield it
                    pass
                elif token_type == "token_usage":
                    # this is the final token usage count, usually emitted at the end of the stream
                    token_usage = token.get("content")
                    if isinstance(token_usage, int):
                        # set the flag so that token counting is always using API data
                        if not self.context.using_api_token_data:
                            self.context.using_api_token_data = True

                        # cache this in the chat's metadata
                        await self.context.chat.set("token_usage", token_usage)

                        fetched_token_usage = True
        except asyncio.CancelledError:
            # if the stream is cancelled at this level, we need to handle the accumulated content in a special way

            if tool_calls_occurred:
                # since at this point, tc_manager.process() has added a bunch of messages with content, reasoning, and toolcalls and their responses to context
                # tc_manager.process() takes care of it, finalizing the last message and adding it to context
                # so we just abort
                return
            else:
                # otherwise, we actually want the normal assistant message adding path to be taken
                pass
        except Exception as e:
            yield await self.throw_stream_error(str(e))

        if not fetched_token_usage:
            # yield an estimated token usage if the API didn't provide one
            # (count the already-built context rather than rebuilding it)
            try:
                estimate = await self.context.count_tokens(processed.get("context"))
                if self.manager.tools:
                    estimate += await self.context.count_tokens(self.manager.tools)
            except Exception:
                estimate = 0
            yield {"type": "token_usage", "content": estimate, "source": "estimation"}

        # and finally, once the stream has completed, add the finished assistant message to context
        if tool_calls_occurred:
            # if tool calls occurred, we don't want the reasoning from the first message to be added to context
            # (that would cause a duplicate)
            # so we abort early
            return

        assistant_message = self._build_final_assistant_message(final_content, final_reasoning)
        await self._send_postprocess(assistant_message)

    async def format_stream_for_text(self, stream, chunk_size=None, use_markdown=True, strings: dict = None, show_indicators=True):
        """
        Formats a stream of turn segments into text deltas for text-based channels.
        """
        def text_to_token(text):
            return {"type": "formatted", "content": text}

        show_reasoning = self.config.get("show_reasoning")
        
        if not strings:
            if use_markdown:
                strings = {
                    "thinking_header": "**Thinking**",
                    "thinking_newline": "\n> ",
                    "conclusion_header": "",
                    "separator": "",
                    "tool_call_header": "🔧 calling tool *{tool_name}*"
                }
            else:
                strings = {
                    "thinking_header": "Thinking:",
                    "thinking_newline": "\n-> ",
                    "conclusion_header": "",
                    "separator": "-"*8,
                    "tool_call_header": "🔧 calling tool {tool_name}"
                }

        first_turn = True
        last_turn_type = None
        currently_reasoning = False
        shown_reasoning_indicator = False
        
        # Per-tool-call tracking: {tool_id: {key: formatted_value}}
        last_tool_state = {}
        last_content = {}
        
        # track characters for chunk boundaries
        char_counter = 0
        
        async def check_chunk_boundary():
            nonlocal char_counter
            if chunk_size and char_counter >= chunk_size:
                yield {"type": "new_chunk", "content": ""}
                char_counter = 0

        async for token in self.group_stream(stream):
            # always yield the raw token for manual processing by the channel
            if token.get("type") == "token":
                yield token.get("content")

            if token.get("type") != "turn":
                continue
            
            segment = token.get("content")
            if not segment:
                continue
            
            segment_type = segment.get("type")
            
            if segment.get("role") != "assistant":
                continue
            
            if segment_type != last_turn_type:
                if first_turn:
                    first_turn = False
                else:
                    if strings.get("separator"):
                        # create a new chunk if needed
                        async for _ in check_chunk_boundary():
                            yield _
                        yield text_to_token("\n"+strings["separator"]+"\n")
                        char_counter += len("\n"+strings["separator"]+"\n")

                last_content = {}
                
                if segment_type == "reasoning" and show_reasoning:
                    currently_reasoning = True
                    # create a new chunk if needed
                    async for _ in check_chunk_boundary():
                        yield _

                    yield text_to_token(strings["thinking_header"])
                    char_counter += len(strings["thinking_header"])
                    yield text_to_token(strings["thinking_newline"])
                    char_counter += len(strings["thinking_newline"])
                elif segment_type == "content" and currently_reasoning:
                    currently_reasoning = False
                    # create a new chunk if needed
                    async for _ in check_chunk_boundary():
                        yield _

                    yield text_to_token(strings["conclusion_header"])
                    char_counter += len(strings["conclusion_header"])
                    yield text_to_token("\n")
                    char_counter += len("\n")
                elif segment_type == "tool_calls":
                    # Will be handled per-tool below
                    pass

            if segment_type == "reasoning":
                if show_reasoning:
                    current = segment.get("reasoning_content") or ""
                    delta = current[len(last_content.get("reasoning", "")):]
                    if delta:
                        # create a new chunk if needed
                        async for _ in check_chunk_boundary():
                            yield _

                        delta = delta.replace("\n", strings["thinking_newline"])
                        yield text_to_token(delta)
                        char_counter += len(delta)
                    if "last_content" not in dir():
                        last_content = {}
                    last_content["reasoning"] = current
                elif not shown_reasoning_indicator:
                    if show_indicators:
                        # create a new chunk if needed
                        async for _ in check_chunk_boundary():
                            yield _

                        yield text_to_token("thinking..\n")
                        char_counter += len("thinking..\n")
                    shown_reasoning_indicator = True

            elif segment_type == "content":
                shown_reasoning_indicator = False

                current = segment.get("content") or ""
                content_index = 0

                if last_content:
                    content_index = len(last_content.get("content", ""))

                delta = current[content_index:]
                if delta:
                    # create a new chunk if needed
                    async for _ in check_chunk_boundary():
                        yield _
                    yield text_to_token(delta)
                    char_counter += len(delta)
                if "last_content" not in dir():
                    last_content = {}
                last_content["content"] = current

            elif segment_type == "tool_calls":
                tool_calls = segment.get("tool_calls") or []
                
                for tc in tool_calls:
                    tc_id = tc.get("id", "")
                    if not tc_id:
                        continue
                        
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    args_str = tc.get("function", {}).get("arguments", "")
                    
                    # Check if we need to print the tool header (new tool or name changed)
                    prev_state = last_tool_state.get(tc_id, {})
                    prev_name = prev_state.get("_name")
                    
                    if prev_name != tool_name:
                        # New tool or name changed - print header
                        header = strings["tool_call_header"].format(tool_name=tool_name)
                        # create a new chunk if needed
                        async for _ in check_chunk_boundary():
                            yield _
                        yield text_to_token("\n")
                        char_counter += len("\n")
                        yield text_to_token(header)
                        char_counter += len(header)
                    
                    # Parse the current arguments as partial JSON
                    try:
                        current_args = partial_json_parser.loads(args_str, allow_partial=partial_json_parser.Allow.ALL)
                        if not isinstance(current_args, dict):
                            current_args = {}
                    except Exception:
                        current_args = {}
                    
                    # Get previous parsed args
                    prev_args = prev_state.get("_args", {})
                    
                    # Compare keys and yield deltas
                    all_keys = set(list(prev_args.keys()) + list(current_args.keys()))
                    for key in all_keys:
                        prev_val = prev_args.get(key)
                        current_val = current_args.get(key)
                        
                        if prev_val is None:
                            # New key - print the whole key: value
                            val_str = json.dumps(current_val) if isinstance(current_val, (dict, list)) else str(current_val)
                            # create a new chunk if needed
                            async for _ in check_chunk_boundary():
                                yield _

                            yield text_to_token("\n")
                            char_counter += len("\n")
                            yield text_to_token(f"**{key}**: ")
                            char_counter += len(f"**{key}**: ")
                            yield text_to_token(val_str)
                            char_counter += len(val_str)
                            yield text_to_token("\n")
                            char_counter += len("\n")
                        elif current_val is None:
                            # Key removed (shouldn't happen during streaming but handle it)
                            pass
                        else:
                            # Key exists in both - check for value change
                            prev_val_str = json.dumps(prev_val) if isinstance(prev_val, (dict, list)) else str(prev_val)
                            current_val_str = json.dumps(current_val) if isinstance(current_val, (dict, list)) else str(current_val)
                            
                            if prev_val_str != current_val_str:
                                # Value changed - yield the delta
                                if current_val_str.startswith(prev_val_str):
                                    delta = current_val_str[len(prev_val_str):]
                                else:
                                    delta = current_val_str
                                if delta:
                                    # create a new chunk if needed
                                    async for _ in check_chunk_boundary():
                                        yield _
                                    yield text_to_token(delta)
                                    char_counter += len(delta)
                    
                    # Update state
                    last_tool_state[tc_id] = {
                        "_name": tool_name,
                        "_args": current_args
                    }

            last_turn_type = segment_type

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
        return await self.turncollector.group_history(await self.context.chat.messages.get())
