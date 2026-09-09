import core
import json
import json_repair
import asyncio
import copy

class ToolcallManager:
    def __init__(self, channel):
        self.channel = channel

    def display_call(self, tool_data):
        """format a toolcalling response into a nice string for display to the user"""

        try:
            if 'function' in tool_data:
                func_name = tool_data['function'].get('name', 'unknown')
                raw_args = tool_data['function'].get('arguments', '{}')
            else:
                return "🔧 Calling tool..."

            if isinstance(raw_args, str):
                try:
                    args_dict = json_repair.loads(raw_args)
                except Exception:
                    args_dict = {}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            arg_strs = []
            for key, value in args_dict.items():
                value_str = str(value)
                if len(value_str) > 30:
                    value_str = value_str[:30] + ".."
                value_str = value_str.replace('"', "'")
                arg_strs.append(f'{key}="{value_str}"')

            return f"🔧 {func_name}({', '.join(arg_strs)})"
        except Exception as e:
            self.channel.log("toolcall", f"Error formatting tool call: {e}")
            return "🔧 Calling tool..."

    def _repair_tool_calls(self, tool_calls):
        repaired_tool_calls = []
        for tool_call in tool_calls:
            raw_args = tool_call['function']['arguments']

            if isinstance(raw_args, dict):
                modified_args = raw_args
            elif isinstance(raw_args, str):
                try:
                    modified_args = json_repair.loads(raw_args)
                except Exception as e:
                    self.channel.log("error", f"JSON repair failed: {e}")
                    modified_args = {}
            else:
                self.channel.log("error", f"unexpected arguments type: {type(raw_args)}")
                modified_args = {}

            if not isinstance(modified_args, dict):
                self.channel.log("error", f"Arguments not a dict: {modified_args}")
                modified_args = {}

            tool_call['function']['arguments'] = json.dumps(modified_args)
            repaired_tool_calls.append(tool_call)
        return repaired_tool_calls

    async def _repair_toolcall_token(self, token):
        repaired_tool_calls = []
        tool_calls = token.get("tool_calls")

        if tool_calls:
            repaired_tool_calls = self._repair_tool_calls(copy.deepcopy(tool_calls))
            repaired_token = token.copy()
            repaired_token["tool_calls"] = repaired_tool_calls
            return repaired_token
        else:
            return token

    async def _build_recursive_request(self, token, final_content = "", final_reasoning = ""):
        repaired_token = await self._repair_toolcall_token(token)

        toolcall_request = {"role": "assistant"}
        if final_content:
            toolcall_request["content"] = "".join(final_content)
        if final_reasoning:
            toolcall_request["reasoning_content"] = "".join(final_reasoning)

        toolcall_request["tool_calls"] = repaired_token.get("tool_calls")

        return toolcall_request

    async def process(self, assistant_message, push=False, recursion_counter=0):
        """
        process tool calls from an API response..
        assistant_content is the "normal" non-toolcall content, the text that the AI wants to say that's not toolcalls
        """

        # this is, once again, a very badly documented thing in openAI's chat completions docs
        # and so i had to use a ton of AI assistance to get this to work well
        # if you ask me, this stuff should be handled in inference servers like llamacpp,
        # NOT by the frontends, because this is just reinventing the wheel..
        # like why do **i** need to repair the json? that should be the server's responsibility...
        # whatever. we deal with it as best we can here

        # fix broken JSON and convert things where needed
        if not assistant_message.get("tool_calls"):
            return

        repaired_tool_calls = self._repair_tool_calls(assistant_message["tool_calls"])

        # add it to context
        await self.channel.context.chat.messages.add(assistant_message)

        # push if needed
        if push:
            await self.channel.push(assistant_message)

        timeout_val = float(core.config.get("core", "tool_timeout", default=10.0))
        tool_loader = self.channel.tool_loader

        # execute each tool and add their responses
        for tool_call_dict in repaired_tool_calls:
            tool_name = tool_call_dict['function']['name']
            tool_args = json_repair.loads(tool_call_dict['function']['arguments'])

            # --- 1. Meta tool check (FIRST, before module scan) ---
            dynamic_loading = core.config.get("model", "dynamic_tool_loading", default=True)
            if tool_name in tool_loader.meta_tool_names:
                if not dynamic_loading:
                    rejected_msg = json.dumps({
                        "content": "Dynamic tool loading is disabled. Meta tools (tools_lookup, tools_load) are not available. You have access to all available tools without needing to load them.",
                        "status": "error"
                    })
                    await self.channel.context.chat.messages.add({
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": rejected_msg
                    })
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": rejected_msg}
                    continue
                func_callable = tool_loader.get_meta_callable(tool_name)
                make_result = lambda msg, success=False: {"status": "success" if success else "error", "content": msg}
                # fall through to shared execution block
            else:
                # --- 2. Module scan ---
                module_instance = None
                method_name = None

                for module_name, module_obj in self.channel.manager.modules.items():
                    class_display_name = core.modules.get_name(module_obj)
                    module_prefix = f"{class_display_name}_"

                    if tool_name.startswith(module_prefix):
                        method_name = tool_name[len(module_prefix):]
                        if hasattr(module_obj, method_name):
                            module_instance = module_obj
                            break

                if module_instance is None:
                    # --- 3. No module matched (hallucinated name) ---
                    self.channel.log("toolcall", f"tried to call tool {tool_name} but couldn't find it")

                    if not dynamic_loading:
                        rejected_msg = json.dumps({
                            "content": f"Tool named {tool_name} does not exist.",
                            "status": "error"
                        })
                    else:
                        rejected_msg = json.dumps({
                            "content": f"No tool named {tool_name} exists. Use tools_lookup to find available tools.",
                            "status": "error"
                        })

                    await self.channel.context.chat.messages.add({
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": rejected_msg
                    })
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": rejected_msg}
                    continue

                # Check disabled tools FIRST (higher priority than "not loaded")
                if method_name in module_instance.disabled_tools:
                    rejected_msg = json.dumps({"content": "That tool has been disabled by the user.", "status": "error"})
                    await self.channel.context.chat.messages.add({
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": rejected_msg
                    })
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": rejected_msg}
                    continue

                # Check if tool is loaded
                if tool_name not in self.channel.manager.tool_names:
                    if not dynamic_loading:
                        rejected_msg = json.dumps({
                            "content": f"Tool {tool_name} is not available. This tool may be disabled or unavailable.",
                            "status": "error"
                        })
                    else:
                        rejected_msg = json.dumps({
                            "content": f"Tool {tool_name} is not loaded. Load it first by calling tools_load with names=[\"{tool_name}\"], then call it again.",
                            "status": "error"
                        })
                    await self.channel.context.chat.messages.add({
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": rejected_msg
                    })
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": rejected_msg}
                    continue

                # Tool is valid and loaded — get callable
                func_callable = getattr(module_instance, method_name)

            # --- Shared execution block ---
            tool_call_str = self.display_call(tool_call_dict)
            self.channel.log("toolcall", tool_call_str)

            func_response = None
            try:
                async def _run_tool():
                    return await func_callable(**tool_args)

                func_response = await asyncio.wait_for(_run_tool(), timeout=timeout_val)
                if func_response is None:
                    # bypass the usual response flow and just abort the chain
                    continue

            except asyncio.TimeoutError as e:
                err_msg = core.detail_error(e) if core.debug else str(e)
                # For meta tools, we don't have module_instance.result, so format manually
                if tool_name in tool_loader.meta_tool_names:
                    func_response = {"status": "error", "content": f"Tool timed out after {timeout_val}s"}
                else:
                    func_response = module_instance.result(f"Tool timed out after {timeout_val}s", success=False)
                self.channel.log("toolcall", func_response.get("content"))
            except Exception as e:
                err_msg = core.detail_error(e) if core.debug else str(e)
                if tool_name in tool_loader.meta_tool_names:
                    func_response = {"status": "error", "content": f"Error while executing tool: {err_msg}"}
                else:
                    func_response = module_instance.result(f"Error while executing tool: {err_msg}", success=False)
                self.channel.log("toolcall", func_response.get("content"))

            func_response_str = None
            if isinstance(func_response, str):
                func_response_str = func_response
            else:
                func_response_str = json.dumps(func_response)

            tool_response = {
                "role": "tool",
                "tool_call_id": tool_call_dict['id'],
                "content": func_response_str
            }

            yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": func_response_str}
            await self.channel.context.chat.messages.add(tool_response)

        if self.channel.manager.API.cancel_request:
            await self.channel.push("toolcalling chain cancelled")
            return

        final_content = []
        final_reasoning = []
        had_recursive_call = False

        reasoning_push_buffer = ""

        try:
            async for token in self.channel.manager.API.send_stream(
                await self.channel.context.get(system_prompt=True, end_prompt=False),
                tools=self.channel.manager.tools
            ):
                token_type = token.get("type")

                if token_type == "content":
                    final_content.append(token.get("content"))
                    yield token
                elif token_type == "reasoning":
                    final_reasoning.append(token.get("content"))
                    yield token
                elif token_type in ["tool_call_delta", "tool", "tool_calls", "prompt_progress", "timings"]:
                    yield token

                if token_type == "tool_calls":
                    # re-calculate current token use and yield it
                    yield {"type": "token_usage", "content": await self.channel.context.get_total_tokens()}

                    had_recursive_call = True
                    toolcall_request = await self._build_recursive_request(token, final_content, final_reasoning)

                    async for sub_token in self.process(
                        toolcall_request,
                        recursion_counter=recursion_counter,
                        push=push
                    ):
                        yield sub_token

            # if we're finally out of the recursive call loop (so, this was the last toolcall)
            # we return the final message for the caller (usually the channel) to do stuff with
            if not had_recursive_call and (final_content or final_reasoning):
                final_msg = {"role": "assistant", "content": "".join(final_content)}
                if final_reasoning:
                    final_msg["reasoning_content"] = "".join(final_reasoning)

                yield {"type": "final", "content": final_msg}

                # set the agentic loop marker so that context.py knows where to start removing reasoning from toolcall messages
                self.channel.agentic_loop_start = len(await self.channel.context.chat.messages.get())-1

        except asyncio.CancelledError:
            # cancellation during recursive toolcalling, so we just take the content/reasoning accumulated so far and add it to context
            if final_content or final_reasoning:
                final_msg = {"role": "assistant", "content": "".join(final_content)}
                if final_reasoning:
                    final_msg["reasoning_content"] = "".join(final_reasoning)

                await self.channel.context.chat.messages.add(final_msg)
        except Exception as e:
            self.channel.log_error(f"Error while handling tool calls", e)
            await self.channel.push(
                f"Error while handling tool calls: {e}"
            )
