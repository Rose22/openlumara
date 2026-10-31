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

    # just like with modules, channels can be grouped into a category in supported UI's
    category = ""

    def __init__(self, manager, is_user_channel=False):
        self.manager = manager
        self.name = core.modules.get_name(self) # shorthand alias
        self.commands = core.commands.Commands(self)
        self._last_cmd_was_temporary = False

        self.queued_message = None # used for mid-stream steering of the AI's next action
        self.sending_message = False # used to track whether the channel is currently sending/streaming a message
        
        self.context = core.context.Context(self) # each channel has its own context window
        # the path to a channel's chat is: channel -> context -> chat

        self.console_buffer = [] # used to log system messages

        self.tc_manager = core.toolcalls.ToolcallManager(self)
        self.turncollector = core.turns.TurnCollector(self)
        self.tool_loader = core.tool_loader.ToolLoader(self)
        self.tool_loader.register_meta_tools()

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

        # gate that holds deferred pushes while a toolcall chain is running.
        self._chain_idle = asyncio.Event()
        self._chain_idle.set()

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

    async def on_system_prompt(self):
        """called when building the system prompt. return a string from this to set a channel-specific system prompt"""
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
                # wait with pushing messages into the channel until the turn is complete
                message, defer = await self.push_queue.get()
                if defer:
                    await self._chain_idle.wait()
                    # add to context only after the gate opens, so the message
                    # lands strictly after the assistant's final message
                    await self.context.chat.messages.add(message)

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

    async def accumulate_stream(self, stream, content, reasoning):
        """this is used to collect the tokens from a stream so they can be returned as a final message object"""
        async for token in stream:
            token_type = token.get("type")
            if token_type == "content":
                content.append(token.get("content"))
            elif token_type == "reasoning":
                reasoning.append(token.get("content"))
            yield token

    async def push_stream(self, stream):
        """
        call this from any channel in order to send a stream into the channel without needing the user's input
        for example: self.push_stream(self.send_stream('blah'))

        the channel's overridable on_stream() method will then take the pushed stream and loop through its tokens
        (if it is defined)

        returns the final message as a chat completions message object that
        can be used however you wish
        """
        content = []
        reasoning = []

        # this is just a wrapper that accumulates the tokens,
        # so call the real event callback
        await self.on_stream(self.accumulate_stream(stream, content, reasoning))

        msg = {"role": "assistant"}
        if reasoning:
            msg["reasoning_content"] = "".join(reasoning)
        if content:
            msg["content"] = "".join(content)

        return msg

    async def on_stream(self, stream):
        """
        overridable method that takes a stream object and lets you loop through the tokens in it in order to render them

        this is a way to decouple user input from stream receiving so that
        things like context compression and modules can send streamed requests
        that display the streamed tokens directly to the user,
        so that the user doesn't have to wait for a request to finish
        """
        pass

    async def push(self, message, defer=True):
        """push a message to the push queue, which will instantly display it in all channels"""

        if not hasattr(self, "push_queue"):
            return False

        # message can be either a str or a dict.
        # if dict, just use it as-is
        # otherwise, turn it into an openAI message dict
        if not isinstance(message, dict):
            message = {"role": "assistant", "content": str(message)}

        # deferred messages are added to context by _push_consumer() once the
        # turn is done, so they can't end up between the toolcall chain and
        # the final message
        if not defer:
            await self.context.chat.messages.add(message)

        await self.push_queue.put((message, defer))

    def _queued_descriptor(self, queued_message):
        """converts a queued steering message to plaintext"""
        text = self._extract_content(queued_message)
        if not text:
            filenames = [f for f in (queued_message.get("_metadata") or {}).get("filenames", []) if f]
            text = ", ".join(filenames) if filenames else "[attachment]"
        return {"content": text, "is_cmd": False}

    def _merge_user_messages(self, existing, new_message):
        """
        merge two chat completions user messages into one.
        text merges with a newline, multimodal content merges as blocks.
        """
        if not existing:
            return new_message

        def to_blocks(content):
            if isinstance(content, list):
                return content
            return [{"type": "text", "text": content or ""}]

        existing_content = existing.get("content")
        new_content = new_message.get("content")

        if isinstance(existing_content, str) and isinstance(new_content, str):
            existing["content"] = existing_content + "\n" + new_content
        else:
            existing["content"] = (
                to_blocks(existing_content)
                + [{"type": "text", "text": "\n"}]
                + to_blocks(new_content)
            )

        # merge attachment metadata so previews keep working
        new_meta = new_message.get("_metadata")
        if new_meta:
            meta = existing.setdefault("_metadata", {"filenames": []})
            meta["filenames"] = meta.get("filenames", []) + new_meta.get("filenames", [])

        return existing

    async def queue_steering_message(self, message, files=None, commands_authorized=False):
        """
        called by send()/send_stream() (and channels) when a message arrives
        while a turn is already in progress.

        commands cannot be merged into a user message, so they run right
        away. anything else becomes a chat completions user message dict
        and merges into self.queued_message: consecutive steering stacks up
        inside that single message. it gets injected at the next toolcall
        round boundary (drain_queued_message), or answered immediately as a
        fresh request if the chain has already ended (see the continuation
        loops in send()/send_stream()).

        returns a {"content": str, "is_cmd": bool} descriptor with the full
        merged queue state for channel UI's (None if nothing was queued).
        """
        # legacy dict handling, same as _send_preprocess()
        if isinstance(message, dict):
            message = message.get("content", "")

        cmd_prefix = core.config.get("core", "cmd_prefix").strip().lower()
        if isinstance(message, str) and message.strip().lower().startswith(cmd_prefix):
            try:
                await self.commands.process_input(message, authorized=commands_authorized)
            except Exception as e:
                self.log(self.name, f"Error while executing steering command: {core.detail_error(e)}")
            return None

        new_message = await self._process_multimodal(message=message, files=files)
        if new_message is None:
            return None

        # no awaits between here and the assignment, so two steering
        # messages racing in can never clobber each other
        self.queued_message = self._merge_user_messages(self.queued_message, new_message)
        return self._queued_descriptor(self.queued_message)

    async def drain_queued_message(self):
        """
        inject the queued steering message into the active context.

        called by ToolcallManager.process() at round boundaries of the
        agentic loop: after every tool response of the current round has
        landed in context and before the next request is composed. That is
        the only safe point - the OpenAI format requires tool messages to
        immediately follow their assistant tool_calls message, so a user
        message can never be injected between a call and its response.

        Returns a list of {"content": str, "is_cmd": bool} descriptors
        (0 or 1 entries) so channels can update their steering queue.
        """
        if self.queued_message is None:
            return []

        queued = self.queued_message
        self.queued_message = None

        # defer=False: push() adds it to context synchronously (so it is
        # part of the next round's context.get()) and displays it in the
        # channel immediately, mid-chain
        await self.push(queued, defer=False)

        return [self._queued_descriptor(queued)]

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
    @staticmethod
    def _sniff_mime(data: bytes) -> str:
        """Guess mime type from magic bytes"""
        if not data:
            return "application/octet-stream"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
        if data.startswith(b"BM"):
            return "image/bmp"
        if data[:4] in (b"II*\x00", b"MM\x00*"):
            return "image/tiff"
        if data.startswith(b"%PDF-"):
            return "application/pdf"
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return "audio/wav"
        if data[:4] == b"\x1a\x45\xdf\xa3":
            return "audio/webm"  # matroska/webm EBML header
        if data[4:8] == b"ftyp":
            brand = data[8:12]
            if brand in (b"M4A ", b"M4B ", b"M4P ", b"mp42", b"isom", b"iso2"):
                return "audio/mp4"
        if data[0] == 0xFF and len(data) > 1 and (data[1] & 0xF6) == 0xF0:
            return "audio/aac"  # ADTS frame sync
        if data.startswith(b"OggS"):
            return "audio/ogg"  # opus/vorbis/speex all share this container
        if data.startswith(b"fLaC"):
            return "audio/flac"
        if data[4:8] == b"ID3\x0a" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
            return "audio/mpeg"
        return "application/octet-stream"

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

            block = await self._module_file_to_block(filename, file_data)
            if block is not None:
                content_blocks.append(block)
                filenames.append(filename)
                continue

            mime_type = self._sniff_mime(file_data)

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
                    from pypdf import PdfReader
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

    async def _module_file_to_block(self, filename: str, file_data: bytes):
        """ask modules whether one of them wants to turn an uploaded file into a content block.
        the first block returned wins, None (the default) lets the built-in handlers do their thing."""
        for module_name, module in self.manager.modules.items():
            try:
                block = await module.on_file_to_block(filename, file_data)
            except Exception as e:
                self.log("module error", f"{module_name}: in on_file_to_block(): {core.detail_error(e)}")
                continue

            if block:
                return block

        return None

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

        self.context._overflow_warned = False

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

        # mark the start of the current agentic loop
        self.agentic_loop_start = len(await self.context.chat.messages.get()) - 1

        # reconnect if needed
        result = await self.manager.API.attempt_connect()
        if result is not True:
            return {"type": "error", "content": str(result)}

        # build the context window
        context = await self.context.get(system_prompt=True, end_prompt=True)

        # and return the results for use in send() and send_stream()
        return {"type": "ready", "user_message": user_message_processed.get("content"), "context": context}

    async def _send_postprocess(self, assistant_message, add_to_context=True):
        if add_to_context:
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

    async def send(self, message: str, files: list = None, commands_authorized=False, add_to_context=True, **kwargs):
        """sends a message to the AI from within the current channel"""
        
        if self.sending_message:
            await self.queue_steering_message(message, files=files, commands_authorized=commands_authorized)
            return

        # reset push defer flag
        self._chain_idle.clear()
        
        # set send flag
        self.sending_message = True
        
        try:
            result = await self._send_inner(message, files=files, commands_authorized=commands_authorized, add_to_context=add_to_context, **kwargs)

            while self.queued_message is not None:
                queued = self.queued_message
                self.queued_message = None
                result = await self._send_inner(
                    queued.get("content"),
                    files=None,
                    commands_authorized=commands_authorized,
                    add_to_context=add_to_context,
                    **kwargs
                )

            return result
        finally:
            self._chain_idle.set()
            self.sending_message = False
            if self.queued_message is not None:
                await self.drain_queued_message()

    async def _send_inner(self, message: str, files: list = None, commands_authorized=False, add_to_context=True, **kwargs):
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
        response = await self.manager.API.send(processed["context"], **kwargs)

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
            final_message = None

            async for sub_token in self.tc_manager.process(
                assistant_message,
                push=True
            ):
                if sub_token.get("type") == "final":
                    final_message = sub_token.get("content")

            if final_message:
                await self._send_postprocess(final_message)
                return self.format_message(final_message)
            return None

        # postprocessing ( mainly assistant message module hooks, but this can be extended later :) )
        await self._send_postprocess(assistant_message, add_to_context=add_to_context)
        return self.format_message(assistant_message)

    async def send_stream(self, message: str, files: list = None, commands_authorized=False, add_to_context=True, **kwargs):
        """sends a message to the AI from within the current channel, streaming version"""

        if self.sending_message:
            # queue the message as a steering message
            await self.queue_steering_message(message, files=files, commands_authorized=commands_authorized)
            return
            
        # reset push defer flag
        self._chain_idle.clear()
        
        # set send flag
        self.sending_message = True
        
        try:
            async for token in self._send_stream_inner(message, files=files, commands_authorized=commands_authorized, add_to_context=add_to_context, **kwargs):
                yield token

            while self.queued_message is not None:
                queued = self.queued_message
                self.queued_message = None

                async for token in self._send_stream_inner(
                    queued.get("content"),
                    files=None,
                    commands_authorized=commands_authorized,
                    add_to_context=add_to_context,
                    emit_user_message=False,
                    steering_descriptor=self._queued_descriptor(queued),
                    **kwargs
                ):
                    yield token
        finally:
            self._chain_idle.set()
            self.sending_message = False
            if self.queued_message is not None:
                await self.drain_queued_message()

    async def _send_stream_inner(self, message: str, files: list = None, commands_authorized=False, add_to_context=True, emit_user_message=True, steering_descriptor=None, **kwargs):
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

        # preprocessing added the merged message to context,
        # so it is now safe for channel UI's to pop it from their
        # steering queue and resync their view of the chat
        if steering_descriptor is not None:
            yield {"type": "queue_flushed", "content": [steering_descriptor], "end_of_chain": True}

        user_message = processed.get("user_message") #alias for readability

        # yield user message as a special token for display in UI's (because user message can be modified by module hooks)
        if emit_user_message:
            yield {"type": "user_message", "content": user_message}
        
        # estimate tokens used for user message
        user_message_token_estimation = 0
        try:
            user_message_token_estimation = await self.context.get_total_tokens()
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
            stream = self.manager.API.send_stream(processed.get("context"), **kwargs)
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
                        if token_usage > 0:
                            # cache the API's reported token usage
                            # all context measurement methods will then use it from this point on
                            await self.context.record_api_usage(token_usage)

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

        if tool_calls_occurred:
            # if tool calls occurred, tc_manager has already added the final
            # message to context, so we can publish and abort early here
            yield {
                "type": "token_usage",
                "content": await self.context.get_total_tokens(),
                "source": "API" if fetched_token_usage else "estimation",
            }
            return

        assistant_message = self._build_final_assistant_message(final_content, final_reasoning)
        await self._send_postprocess(assistant_message, add_to_context=add_to_context)

        yield {
            "type": "token_usage",
            "content": await self.context.get_total_tokens(),
            "source": "API" if fetched_token_usage else "estimation",
        }

    async def format_stream_for_text(self, stream, chunk_size=None, use_markdown=True, strings: dict = None, show_indicators=True):
        """
        Formats a step-based stream into text deltas for text-based channels.
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

        currently_reasoning = False
        shown_reasoning_indicator = False

        step_state = {}
        final_text = {}

        # Per-tool-call tracking: {tool_id: {key: formatted_value}}
        last_tool_state = {}

        # separator bookkeeping: which (field, step) emitted text last
        # (mirrors the old segment-type transition rule)
        last_key = None
        first_growth = True
        
        # track characters for chunk boundaries
        char_counter = 0
        
        async def check_chunk_boundary():
            nonlocal char_counter
            if chunk_size and char_counter >= chunk_size:
                yield {"type": "new_chunk", "content": ""}
                char_counter = 0

        # ROSE22 TODO: turn this into an actual step-based display somehow despite
        # not being able to edit UI elements when using this function...??????
        async def emit_step_text(step):
            nonlocal last_key, first_growth, currently_reasoning
            nonlocal shown_reasoning_indicator, char_counter

            sn = step.get("step") or 0
            st = step_state.setdefault(
                sn,
                {"reasoning": "", "content": "", "step_obj": {}},
            )
            st["step_obj"] = step

            live_final = final_text.get(sn, "")
            step_content = step.get("content") or ""
            if live_final and step_content:
                content = step_content + "\n\n" + live_final
            else:
                content = live_final or step_content

            async def transition(field):
                nonlocal last_key, first_growth, char_counter
                if last_key == (field, sn):
                    return
                if not first_growth and strings.get("separator"):
                    async for _ in check_chunk_boundary():
                        yield _
                    yield text_to_token("\n"+strings["separator"]+"\n")
                    char_counter += len("\n"+strings["separator"]+"\n")
                last_key = (field, sn)
                first_growth = False

            reasoning = step.get("reasoning_content") or ""
            r_delta = (
                reasoning[len(st["reasoning"]):]
                if reasoning.startswith(st["reasoning"])
                else reasoning
            )

            if r_delta:
                async for _ in transition("reasoning"):
                    yield _

                if show_reasoning:
                    if not currently_reasoning:
                        # create a new chunk if needed
                        async for _ in check_chunk_boundary():
                            yield _

                        yield text_to_token(strings["thinking_header"])
                        char_counter += len(strings["thinking_header"])
                        yield text_to_token(strings["thinking_newline"])
                        char_counter += len(strings["thinking_newline"])
                    currently_reasoning = True

                    delta = r_delta.replace("\n", strings["thinking_newline"])
                    async for _ in check_chunk_boundary():
                        yield _
                    yield text_to_token(delta)
                    char_counter += len(delta)
                elif not shown_reasoning_indicator:
                    if show_indicators:
                        async for _ in check_chunk_boundary():
                            yield _

                        yield text_to_token("thinking..\n")
                        char_counter += len("thinking..\n")
                    shown_reasoning_indicator = True
                st["reasoning"] = reasoning

            c_delta = (
                content[len(st["content"]):]
                if content.startswith(st["content"])
                else content
            )
            if c_delta:
                async for _ in transition("content"):
                    yield _

                shown_reasoning_indicator = False
                if currently_reasoning:
                    async for _ in check_chunk_boundary():
                        yield _

                    yield text_to_token(strings["conclusion_header"])
                    char_counter += len(strings["conclusion_header"])
                    yield text_to_token("\n")
                    char_counter += len("\n")
                    currently_reasoning = False

                async for _ in check_chunk_boundary():
                    yield _
                yield text_to_token(c_delta)
                char_counter += len(c_delta)
                st["content"] = content

            # tool calls: one header per call, then per-argument deltas
            tool_calls = step.get("tool_calls") or []
            if tool_calls:
                async for _ in transition("tool_calls"):
                    yield _

            for tc in tool_calls:
                tc_id = tc.get("id", "")
                if not tc_id:
                    continue

                meta = tc.get("_metadata") or {}
                tool_name = (
                    (tc.get("function") or {}).get("name")
                    or meta.get("display_name")
                    or "unknown"
                )
                args_str = (tc.get("function") or {}).get("arguments", "")

                prev_state = last_tool_state.get(tc_id, {})
                prev_name = prev_state.get("_name")

                if prev_name != tool_name:
                    # New tool or name changed - print header
                    header = strings["tool_call_header"].format(tool_name=tool_name)
                    async for _ in check_chunk_boundary():
                        yield _
                    yield text_to_token("\n")
                    char_counter += len("\n")
                    yield text_to_token(header)
                    char_counter += len(header)

                try:
                    current_args = partial_json_parser.loads(args_str, allow_partial=partial_json_parser.Allow.ALL)
                    if not isinstance(current_args, dict):
                        current_args = {}
                except Exception:
                    current_args = {}

                prev_args = prev_state.get("_args", {})

                all_keys = set(list(prev_args.keys()) + list(current_args.keys()))
                for key in all_keys:
                    prev_val = prev_args.get(key)
                    current_val = current_args.get(key)

                    if prev_val is None:
                        # New key - print the whole key: value
                        val_str = json.dumps(current_val) if isinstance(current_val, (dict, list)) else str(current_val)
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
                        # Key removed (shouldn't happen during streaming)
                        pass
                    else:
                        prev_val_str = json.dumps(prev_val) if isinstance(prev_val, (dict, list)) else str(prev_val)
                        current_val_str = json.dumps(current_val) if isinstance(current_val, (dict, list)) else str(current_val)

                        if prev_val_str != current_val_str:
                            # Value changed - yield the delta
                            if current_val_str.startswith(prev_val_str):
                                delta = current_val_str[len(prev_val_str):]
                            else:
                                delta = current_val_str
                            if delta:
                                async for _ in check_chunk_boundary():
                                    yield _
                                yield text_to_token(delta)
                                char_counter += len(delta)

                last_tool_state[tc_id] = {
                    "_name": tool_name,
                    "_args": current_args
                }

        async for event in self.group_stream(stream):
            event_type = event.get("type")

            # always yield the raw token for manual processing by the channel
            if event_type == "token":
                yield event.get("content")
                continue

            if event_type == "step":
                step = event.get("content")
                if isinstance(step, dict):
                    async for out in emit_step_text(step):
                        yield out

            elif event_type == "final":
                # re-render every step whose live final text changed
                touched = set(final_text)
                final_text.clear()
                for message in event.get("content") or []:
                    sn = message.get("step") or 0
                    final_text[sn] = message.get("content") or ""
                    touched.add(sn)

                for sn in sorted(touched):
                    st = step_state.get(sn)
                    step_obj = (st or {}).get("step_obj")
                    if step_obj is None:
                        # a pure content answer: render it standalone
                        step_obj = {"step": sn, "content": "", "reasoning_content": ""}
                    async for out in emit_step_text(step_obj):
                        yield out



    async def group_stream(self, stream):
        """
        groups incoming tokens into step events using the
        TurnCollector defined in core/turns.py

        yields {"type": "token"}, {"type": "step"}, and {"type": "final"} objects
        see TurnCollector.group_stream for the full description!

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
