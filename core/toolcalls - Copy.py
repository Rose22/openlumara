import core
import json
import json_repair
import asyncio
from concurrent.futures import ProcessPoolExecutor

class ToolcallManager:
    def __init__(self, channel):
        self.channel = channel

    def display_call(self, tool_data):
        """format a toolcalling response into a nice string for display to the user"""

        try:
            if hasattr(tool_data, 'function'):
                func_name = getattr(tool_data.function, 'name', 'unknown')
                raw_args = getattr(tool_data.function, 'arguments', '{}')
            elif isinstance(tool_data, dict) and 'function' in tool_data:
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
            core.log("toolcall", f"Error formatting tool call: {e}")
            return "🔧 Calling tool..."

    def _repair_tool_calls(self, tool_calls):
        repaired_tool_calls = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                tool_call = tool_call.model_dump(warnings=False)
            raw_args = tool_call['function']['arguments']

            if isinstance(raw_args, dict):
                modified_args = raw_args
            elif isinstance(raw_args, str):
                try:
                    modified_args = json_repair.loads(raw_args)
                except Exception as e:
                    core.log("error", f"JSON repair failed: {e}")
                    modified_args = {}
            else:
                core.log("error", f"unexpected arguments type: {type(raw_args)}")
                modified_args = {}

            if not isinstance(modified_args, dict):
                core.log("error", f"Arguments not a dict: {modified_args}")
                modified_args = {}

            tool_call['function']['arguments'] = json.dumps(modified_args)
            repaired_tool_calls.append(tool_call)
        return repaired_tool_calls

    async def _repair_toolcall_token(self, token):
        repaired_tool_calls = []
        tool_calls = token.get("tool_calls")

        if tool_calls:
            repaired_tool_calls = self._repair_tool_calls(tool_calls)
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
        await self.channel.context.chat.add(assistant_message)

        # push if needed
        if push:
            await self.channel.push(assistant_message)

        timeout_val = float(core.config.get("core", "tool_timeout", default=10.0))

        # execute each tool and add their responses
        for tool_call_dict in repaired_tool_calls:
            tool_name = tool_call_dict['function']['name']
            tool_args = json_repair.loads(tool_call_dict['function']['arguments'])

            module_instance = None
            module_instance_display_name = None

            # find the module that has the requested tool
            # and store the instance and name of that module
            for module_name, module_obj in self.channel.manager.modules.items():
                class_display_name = core.modules.get_name(module_obj)

                # remove the module name from the tool name
                module_identifier = f"{class_display_name}_"
                translated_tool_name = tool_name[len(module_identifier):]

                if hasattr(module_obj, translated_tool_name):
                    module_instance = module_obj
                    module_instance_display_name = class_display_name
                    break

            if module_instance:
                # remove the module name from the tool name
                module_identifier = f"{module_instance_display_name}_"
                translated_tool_name = tool_name[len(module_identifier):]

                if (
                    tool_name not in self.channel.manager.tool_names
                    or
                    translated_tool_name in module_instance.disabled_tools
                ):
                    # don't allow disabled tools to be called
                    rejected_msg = json.dumps({"content": "That tool has been disabled by the user.", "status": "error"})
                    await self.channel.context.chat.add({
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": rejected_msg
                    })
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": rejected_msg}
                    continue

                # and use it to get the function object for that tool
                func_callable = getattr(module_instance, translated_tool_name)

                # build a fancy toolcall display string
                tool_call_str = self.display_call(tool_call_dict)

                core.log("toolcall", tool_call_str)

                func_response = None
                try:
                    # do the function call and get it's result
                    async def _run_tool():
                        return await func_callable(**tool_args)

                    # add a timeout so that tools can't hang the application forever
                    func_response = await asyncio.wait_for(_run_tool(), timeout=timeout_val)

                except asyncio.TimeoutError as e:
                    err_msg = core.detail_error(e) if core.debug else str(e)
                    func_response = module_instance.result(f"Tool timed out after {timeout_val}s", success=False)
                    core.log("toolcall", func_response.get("content"))
                except Exception as e:
                    err_msg = core.detail_error(e) if core.debug else str(e)
                    func_response = module_instance.result(f"Error while executing tool: {err_msg}", success=False)
                    core.log("toolcall", func_response.get("content"))
                finally:
                    func_response_str = None

                    # don't double-escape strings
                    if isinstance(func_response, str):
                        func_response_str = func_response
                    else:
                        func_response_str = json.dumps(func_response)

                    # build the openai toolcall response object
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": func_response_str
                    }

                    # yield it so it can be displayed immediately
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": func_response_str}

                    # add the tool response to the context window
                    await self.channel.context.chat.add(tool_response)

                    # push it if needed
                    # if push:
                    #     await self.channel.push(tool_response)
            else:
                core.log(
                    "toolcall",
                    f"tried to call tool {tool_name} but couldn't find it"
                )

        if self.channel.manager.API.cancel_request:
            await self.channel.announce("toolcalling chain cancelled", "info")
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
                if self.channel.manager.API.cancel_request:
                    await self.channel.announce("toolcalling chain cancelled", "info")
                    return

                token_type = token.get("type")

                if token_type == "content":
                    final_content.append(token.get("content"))
                    yield token
                elif token_type == "reasoning":
                    final_reasoning.append(token.get("content"))
                    yield token
                elif token_type in ["tool_call_delta", "tool", "tool_calls", "prompt_progress", "timings"]:
                    yield token

                if token_type == "token_usage":
                    usage = token.get("content")
                    if usage is not None:
                        # set the flag so that token counting is always using API data
                        if not self.channel.context.chat.using_api_token_data:
                            self.channel.context.chat.using_api_token_data = True

                        await self.channel.context.chat.set_token_usage(usage)
                        # yield it to the frontend so the token bar updates in real-time
                        yield token

                if token_type == "tool_calls":
                    had_recursive_call = True
                    toolcall_request = await self._build_recursive_request(token, final_content, final_reasoning)

                    async for sub_token in self.process(
                        toolcall_request,
                        recursion_counter=recursion_counter,
                        push=push
                    ):
                        if self.channel.manager.API.cancel_request:
                            await self.channel.announce("toolcalling chain cancelled", "info")
                            return
                        yield sub_token

            # only add final message if we didn't make a recursive call
            # (the innermost call handles adding the final message)
            if not had_recursive_call:
                final_content_str = "".join(final_content)
                final_reasoning_str = "".join(final_reasoning)

                if final_content_str or final_reasoning_str:
                    final_msg = {"role": "assistant", "content": final_content_str}

                    if final_reasoning_str:
                        final_msg["reasoning_content"] = final_reasoning_str

                    await self.channel.context.chat.add(final_msg)
                    if push:
                        await self.channel.push(final_msg)

        except Exception as e:
            core.log_error(f"Error while handling tool calls", e)
            await self.channel.announce(
                f"Error while handling tool calls: {e}",
                "error"
            )
