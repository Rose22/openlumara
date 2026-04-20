import core
import json
import json_repair

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

    async def process(self, tool_calls, initial_content=""):
        """
        process tool calls from an API response..
        initial_content is the "normal" non-toolcall content, the text that the AI wants to say that's not toolcalls
        """

        # this is, once again, a very badly documented thing in openAI's chat completions docs
        # and so i had to use a ton of AI assistance to get this to work well
        # if you ask me, this stuff should be handled in inference servers like llamacpp,
        # NOT by the frontends, because this is just reinventing the wheel..
        # like why do **i** need to repair the json? that should be the server's responsibility...
        # whatever. we deal with it as best we can here

        # fix broken JSON and convert things where needed
        repaired_tool_calls = self._repair_tool_calls(tool_calls)

        # build openAI-compliant assistant message
        assistant_message = {
            "role": "assistant",
            "tool_calls": repaired_tool_calls
        }
        if initial_content:
            assistant_message["content"] = initial_content

        # add it to context
        await self.channel.context.chat.add(assistant_message)

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
                translated_tool_name = tool_name.replace(f"{class_display_name}_", "")

                if hasattr(module_obj, translated_tool_name):
                    module_instance = module_obj
                    module_instance_display_name = class_display_name
                    break

            if module_instance:
                # remove the module name from the tool name
                translated_tool_name = tool_name.replace(
                    f"{module_instance_display_name}_", ""
                )
                # and use it to get the function object for that tool
                func_callable = getattr(module_instance, translated_tool_name)

                # build a fancy toolcall display string
                tool_call_str = self.display_call(tool_call_dict)

                # core.log("toolcall", tool_call_str)

                try:
                    # do the function call and get it's result
                    func_response = await func_callable(**tool_args)

                    # then build the openai toolcall response object
                    func_response_str = json.dumps(func_response)
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": func_response_str
                    }

                    # yield it so it can be displayed immediately
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": func_response_str}

                except Exception as e:
                    core.log_error("error", e)

                    # build an openai-compliant tool error object
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": f"error: {str(e)}"
                    }

                    # yield it so it can be displayed immediately
                    yield {"type": "tool", "tool_call_id": tool_call_dict['id'], "content": f"error: {str(e)}"}

                # add the tool response to the context window
                await self.channel.context.chat.add(tool_response)
            else:
                core.log(
                    "toolcall",
                    f"tried to call tool {tool_name} but couldn't find it"
                )

        if self.channel.manager.API.cancel_request:
            await self.channel.announce("toolcalling chain cancelled", "info")
            return

        # # build the toolcalling prompt
        # try:
        #     # attempt to get chat message history
        #     context = await self.channel.context.chat.get()
        # except:
        #     # in case we don't have a chat, just use a blank messages array
        #     context = {}

        # prompt = [
        #     {
        #         "role": "system",
        #         "content": (
        #             "If the tool response provides sufficient answers, "
        #             "explain the results to the user. If not, call another tool."
        #         )
        #     }
        # ] + context

        final_content = []
        final_reasoning = []
        had_recursive_call = False

        try:
            async for token in self.channel.manager.API.send_stream(
                await self.channel.context.get(end_prompt=False),
                tools=self.channel.manager.tools
            ):
                token_type = token.get("type")

                if token_type == "content":
                    final_content.append(token.get("content"))
                    yield token
                elif token_type == "reasoning":
                    final_reasoning.append(token.get("content"))
                    yield token
                elif token_type in ["tool_call_delta", "tool", "tool_calls"]:
                    yield token

                if token_type == "tool_calls":
                    had_recursive_call = True
                    tool_calls = token.get("content")
                    repaired_tool_calls = []
                    if tool_calls:
                        repaired_tool_calls = self._repair_tool_calls(tool_calls)
                        repaired_token = token.copy()
                        repaired_token["content"] = repaired_tool_calls
                        yield repaired_token
                    else:
                        yield token

                    # the AI has decided to call more tools, so we make a recursive call
                    async for sub_token in self.process(
                        repaired_tool_calls if tool_calls else [],
                        initial_content=None
                    ):
                        yield sub_token

                if token_type == "usage":
                    pass

            if not final_content:
                if final_reasoning:
                    # replace content with reasoning if there was no content
                    final_content = f"The AI made a tool call, but returned no message.\nReasoning: {''.join(final_reasoning)}"
                else:
                    final_content = "Made a tool call"

            # only add final message if we didn't make a recursive call
            # (the innermost call handles adding the final message)
            if final_content and not had_recursive_call:
                await self.channel.context.chat.add({
                    "role": "assistant",
                    "content": "".join(final_content)
                })

        except Exception as e:
            core.log("error", f"Error while handling tool calls: {e}")
            await self.channel.announce(
                f"Error while handling tool calls: {e}",
                "error"
            )
