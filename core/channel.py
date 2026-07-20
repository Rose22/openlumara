import core
import core.commands
import os
import sys
import time
import json
import asyncio
import json_repair
import re
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

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # merge the base class's settings with the subclass settings.
        # this way, we can define settings ALL channels should have
        for b in cls.__mro__[1:]:
            if hasattr(b, "settings"):
                cls.settings = b.settings | cls.settings
                break

    async def _shutdown(self):
        """internal shutdown function. gets called by the manager before on_shutdown()"""

        self._shutting_down = True
        if self._queue_task:
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass

    async def _set_as_active_channel(self):
        if self.manager.channel is self:
            return
        self.manager.channel = self
        self.manager.savedata["last_channel"] = self.name
        self.manager.savedata.save()

        # give all modules a way to access this channel
        for module_name, module in self.manager.modules.items():
            module.channel = self

    def _get_disconnection_message(self):
        status = self.manager.get_api_status()
        error = status.get("error", "Unknown error")

        message_parts = []

        if error:
            message_parts.append(f"Error: {error}")

        if not status.get("url_configured"):
            message_parts.append("Please configure your API URL in config/config.yml")
        elif not status.get("key_configured"):
            message_parts.append("Please configure your API key in config/config.yml")

        return "\n".join(message_parts)

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

    async def _start_push_queue(self):
        if not hasattr(self, "on_push"):
            return
        self._queue_task = asyncio.create_task(self._push_consumer())

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

    # async def _poll_loop(self):
    #     """constantly polls the chat history to see if anything new arrived, and triggers on_message for every new message"""
    #     if not hasattr(self, "on_message"):
    #         return False
    #
    #     self.log(self.name, "started message polling loop")
    #
    #     while not getattr(self, "_shutting_down", False):
    #         try:
    #             # check for new messages
    #             new_messages = await self.context.chat.get_new()
    #
    #             if new_messages:
    #                 for message in new_messages:
    #                     # trigger the event
    #                     await self.on_message(self.format_message(message))
    #
    #             await asyncio.sleep(0.1)
    #
    #         except Exception as e:
    #             self.log(self.name, f"error in poll loop: {str(e)}")
    #             # if we hit an error, back off for a second so we don't spam the logs
    #             await asyncio.sleep(1)

    async def send(self, message: dict, commands_authorized=False):
        """sends a message to the AI from within the current channel"""

        user_message = message #alias for readability

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        # process any /commands
        if isinstance(user_message.get("content"), str):
            cmd_response = None
            is_cmd = user_message.get("content", "").strip().lower().startswith(
                core.config.get("core", "cmd_prefix").strip().lower()
            )

            if is_cmd and user_message.get("role", "user") == "user":
                try:
                    cmd_response = await self.commands.process_input(user_message, authorized=commands_authorized)
                except Exception as e:
                    self.log_error("error while executing command", e)
                    return {"role": "assistant", "content": str(e)}

                if cmd_response:
                    return {"role": "assistant", "content": cmd_response}
                else:
                    return {"role": "assistant", "content": "BLANK"}

        # run module event hooks
        usr_msg_result = None
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_user_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_user_message):
                        usr_msg_result = await module.on_user_message(user_message.get("content", ""))
                    else:
                        usr_msg_result = module.on_user_message(user_message.get("content", ""))
                except Exception as e:
                    self.log("module error", f"{module_name}: in on_user_message(): {core.detail_error(e)}")

                if usr_msg_result is False:
                    # when returning False from the user message hook,
                    # we stop the chain here, allowing the hook to basically intercept the message
                    # and prevent the AI from returning its own response to the message
                    await self.context.chat.add(user_message)
                    return
                elif usr_msg_result is not None:
                    # allow modifying user message by returning the modified message as a string
                    user_message['content'] = usr_msg_result

        # add sent message to context
        add_success = await self.context.chat.add(user_message)

        if not add_success:
            return None

        # if not a command, send the message to the AI and return it's response
        # reconnect if needed
        result = await self.manager.API.attempt_connect()
        if result is not True:
            self.log("API", str(result))
            return {"role": "assistant", "content": str(result)}

        # then get the full context window
        context = await self.context.get(system_prompt=True, end_prompt=True)

        # and then request the AI response and add it to context
        response = await self.manager.API.send(context)

        # handle any errors
        if isinstance(response, core.api.APIError):
            self.log("api", response)
            return {"role": "assistant", "content": str(response)}

        # make a copy of the response message and edit it
        assistant_message = dict(response)
        assistant_message["role"] = "assistant"

        tool_calls = assistant_message.get("tool_calls")

        # convert any toolcalls to a dict so that JSON serialization doesnt die
        if tool_calls:
            toolcalls_converted = []

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    tool_call = tool_call.model_dump(warnings=False)
                toolcalls_converted.append(tool_call)

            assistant_message["tool_calls"] = toolcalls_converted

        if tool_calls:
            # process() does all the toolcalling, but it also returns the raw toolcall stream for our own use
            async for sub_token in self.tc_manager.process(
                assistant_message,
                push=True
            ):
                # push handles all the output
                pass

        # add to context
        if not tool_calls:
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

        if tool_calls:
            return None

        return self.format_message(assistant_message)

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

    async def send_stream(self, message: dict, commands_authorized=False):
        """sends a message to the AI from within the current channel, streaming version"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        user_message = message #alias for readability

        # process any /commands
        if isinstance(message.get("content"), str):
            cmd_response = None
            is_cmd = message.get("content", "").strip().lower().startswith(
                core.config.get("core", "cmd_prefix").strip().lower()
            )

            if is_cmd and message.get("role", "user") == "user":
                # immediately yield the user's message for display in frontend channels
                yield {"type": "user_message", "content": user_message.get("content")}

                # then process
                try:
                    cmd_response = await self.commands.process_input(user_message, authorized=commands_authorized)
                except Exception as e:
                    self.log_error("error while executing command", core.detail_error(e))

                    await self.context.chat.add(user_message)
                    yield await self.throw_stream_error(str(core.detail_error(e)))
                    return

                if cmd_response:
                    # insert and return the command response without sending it to the AI
                    # return the entire thing as one token so that it's instant

                    # we don't add to context here because process_input already does that! oopsie..
                    yield {"type": "content", "content": str(cmd_response), "is_cmd": True}
                    # we add a special is_cmd field so that channels can pick up on it and display it in a special way
                    # (the old webui used to just check for the presence of a '/' at the start of the string..)
                    # which obviously is really bad lol
                    # especially since everything is supposed to work across the core, NOT just the webui
                    return

        # run user message module event hooks
        # before we even send to the API, so that we can immediately yield the message for display in frontend channels
        usr_msg_result = None
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_user_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_user_message):
                        usr_msg_result = await module.on_user_message(user_message.get("content", ""))
                    else:
                        usr_msg_result = module.on_user_message(user_message.get("content", ""))
                except Exception as e:
                    self.log("module error", f"{module_name}: in on_user_message(): {core.detail_error(e)}")

                if usr_msg_result is False:
                    # when returning False from the user message hook,
                    # we stop the chain here, allowing the hook to basically intercept the message
                    # and prevent the AI from returning its own response to the message
                    await self.context.chat.add(user_message)
                    return
                elif usr_msg_result is not None:
                    # allow modifying user message by returning the modified message as a string
                    user_message['content'] = usr_msg_result

        # yield user message as a special token for display in UI's (because user message can be modified by module hooks)
        yield {"type": "user_message", "content": user_message.get("content")}
        
        # add user's message to context
        add_success = await self.context.chat.add(user_message)
        if not add_success:
            yield await self.throw_stream_error("Unknown error while adding user message to context")
            return

        # reconnect if needed
        result = await self.manager.API.attempt_connect()
        if result is not True:
            yield await self.throw_stream_error(str(result))
            self.log("API", str(result))
            return

        # estimate tokens used for user message
        user_message_token_estimation = 0
        if self.context.chat.using_api_token_data:
            # if using API token count
            user_msg_tokens = await self.context.chat.count_tokens([user_message])
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

        # get the new context window with the added message
        context = await self.context.get(system_prompt=True, end_prompt=True)

        final_content = []
        final_reasoning = []
        tc_response = None
        tool_calls_occurred = False
        fetched_token_usage = False

        # and stream the response to the caller of this method
        try:
            stream = self.manager.API.send_stream(context)
        except Exception as e:
            yield self.throw_stream_error(f"Error while starting stream: {core.detail_error(e)}")
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

    def _render_tool_token(self, name: str, args_str: str) -> str:
        delta = ""

        # 1. Handle tool switch
        if name != self._tool_state["name"]:
            self._tool_state["name"] = name
            self._tool_state["raw_args"] = ""
            self._tool_state["keys_state"] = {}
            return f"\n**Calling tool: {name}**\n"

        # 2. Try parsing JSON for key-value formatting
        data = {}
        try:
            # Try the fast/easy way first: full parse
            parsed = json_repair.loads(args_str)
            if isinstance(parsed, dict):
                data = parsed
            else:
                # If it's not a dict, it might be a partial dict that json_repair 
                # couldn't quite fix into a dict. Let's try the regex fallback.
                raise ValueError("Not a dict")
        except Exception:
            # Fallback to robust partial parsing if json_repair fails to produce a dict
            # This mimics the WebUI's ability to extract keys even from incomplete JSON
            key_pattern = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:\s*')
            matches = list(key_pattern.finditer(args_str))
            
            for i, match in enumerate(matches):
                key = match.group(1)
                value_start = match.end()
                
                # Determine the end of the value
                if i + 1 < len(matches):
                    next_match_start = matches[i+1].start()
                    potential_value_str = args_str[value_start:next_match_start].rstrip().rstrip(',')
                else:
                    potential_value_str = args_str[value_start:]
                
                # Use json_repair to try and get the value by wrapping it in a dict
                try:
                    # Try to get the value by wrapping it in a dict
                    repaired = json_repair.loads(f'{{"v": {potential_value_str}}}')
                    if isinstance(repaired, dict) and "v" in repaired:
                        data[key] = repaired["v"]
                    else:
                        # Fallback: strip quotes and trailing JSON structural characters
                        val = potential_value_str.lstrip()
                        if val.startswith('"'):
                            val = val[1:]
                        val = val.rstrip('"} ,]')
                        data[key] = val
                except Exception:
                    # Final fallback: strip quotes and trailing JSON structural characters
                    val = potential_value_str.lstrip()
                    if val.startswith('"'):
                        val = val[1:]
                    val = val.rstrip('"} ,]')
                    data[key] = val

        # 3. Generate the delta based on the current (potentially partial) data
        for key, value in data.items():
            # Convert value to string for comparison and display
            if isinstance(value, (dict, list)):
                val_str = json.dumps(value)
            else:
                val_str = str(value)
            
            prev_val = self._tool_state["keys_state"].get(key)

            if prev_val is None:
                # New key: append header and current value
                delta += f"\n**{key}**: "
                if val_str:
                    delta += val_str
                self._tool_state["keys_state"][key] = val_str
            elif val_str != prev_val:
                # Existing key: append only the new part of the value
                if val_str.startswith(prev_val):
                    delta += val_str[len(prev_val):]
                else:
                    # If the value changed completely, just append the new value.
                    # This is a fallback for delta channels.
                    delta += val_str
                self._tool_state["keys_state"][key] = val_str

        self._tool_state["raw_args"] = args_str
        return delta

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
                content = re.sub(r'\n{3,}', '\n\n', content)
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
                char_counter += len("\n")
                yield text_to_token("\n")

                # Extract the accumulated tool call from the delta
                tc_list = token.get("tool_calls", [])
                if tc_list:
                    tc = tc_list[0]
                    # Render the partial/full tool call fancy style
                    tool_delta_str = self._render_tool_token(tc.function.name, tc.function.arguments)

                    # fix fake newlines
                    tool_delta_str = tool_delta_str.replace("\\n", "\n")

                    char_counter += len(tool_delta_str)
                    yield text_to_token(tool_delta_str)
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

    async def run(self):
        # stub, meant for derivative channels to override
        pass

    async def on_ready(self):
        """
        called when the entire framework has fully initialized
        (when the message "[CORE] Startup complete" shows up)
        """
        pass

    async def on_push(self, message: dict):
        raise NotImplementedError

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
