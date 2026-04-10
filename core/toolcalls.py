import core
import json
import json_repair

class ToolcallManager:
    def __init__(self, channel):
        self.channel = channel

    async def process(self, tool_calls, initial_content=""):
        """
        Process tool calls from a streamed response.

        Args:
            tool_calls: The tool calls to process
            initial_content: Content that was streamed before tool calls

        Yields response tokens after executing tools.
        """
        # Fix broken JSON and convert to dicts
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

        # Build assistant message with both content and tool_calls
        assistant_message = {
            "role": "assistant",
            "tool_calls": repaired_tool_calls
        }
        if initial_content:
            assistant_message["content"] = initial_content

        # Add assistant message to context
        await self.channel.context.chat.add(assistant_message)

        # Execute each tool and add their responses
        for tool_call_dict in repaired_tool_calls:
            tool_name = tool_call_dict['function']['name']
            tool_args = json_repair.loads(tool_call_dict['function']['arguments'])

            module_instance = None
            module_instance_display_name = None

            for module_name, module_obj in self.channel.manager.modules.items():
                class_display_name = core.modules.get_name(module_obj)
                translated_tool_name = tool_name.replace(f"{class_display_name}_", "")

                if hasattr(module_obj, translated_tool_name):
                    module_instance = module_obj
                    module_instance_display_name = class_display_name
                    break

            if module_instance:
                translated_tool_name = tool_name.replace(
                    f"{module_instance_display_name}_", ""
                )
                func_callable = getattr(module_instance, translated_tool_name)

                arg_display = []
                for key, value in tool_args.items():
                    value = str(value)
                    if len(value) > 50:
                        value = f"{value[:50]}.."
                    arg_display.append(f"{key}={value}")
                arg_display_str = ", ".join(arg_display)
                announce_string = f"calling tool {tool_name}({arg_display_str})"

                core.log("toolcall", announce_string)

                try:
                    func_response = await func_callable(**tool_args)
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": json.dumps(str(func_response))
                    }
                except Exception as e:
                    core.log("toolcall", f"error: {str(e)}")
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call_dict['id'],
                        "content": f"error: {str(e)}"
                    }

                await self.channel.context.chat.add(tool_response)
            else:
                core.log(
                    "toolcall",
                    f"tried to call tool {tool_name} but couldn't find it"
                )

        if self.channel.manager.API.cancel_request:
            await self.channel.announce("toolcalling chain cancelled", "info")
            return

        # Build context and stream response
        context = await self.channel.context.get(system_prompt=False)
        prompt = [
            {
                "role": "system",
                "content": (
                    "If the tool response provides sufficient answers, "
                    "explain the results to the user. If not, call another tool."
                )
            }
        ] + context

        final_content = []
        final_reasoning = []
        had_recursive_call = False

        try:
            async for token in self.channel.manager.API.send_stream(
                prompt,
                tools=self.channel.manager.tools
            ):
                token_type = token.get("type")
                if token_type == "content":
                    final_content.append(token.get("content"))
                    yield token
                elif token_type == "reasoning":
                    # only collect reasoning, in case there was no normal message content. dont yield.
                    final_reasoning.append(token.get("content"))
                elif token_type == "tool_calls":
                    yield token

                    # Mark that we made a recursive call
                    had_recursive_call = True
                    # Pass accumulated content to recursive call
                    async for sub_token in self.process(
                        token.get("content"),
                        initial_content="".join(final_content)
                    ):
                        yield sub_token
                elif token_type == "usage":
                    pass

            if not final_content:
                final_content = final_reasoning

            # Only add final message if we didn't make a recursive call
            # (the innermost call handles adding the final message)
            if final_content and not had_recursive_call:
                await self.channel.context.chat.add({
                    "role": "assistant",
                    "content": "".join(final_content)
                })

        except Exception as e:
            core.log("error", f"error while handling tool calls: {e}")
            await self.channel.announce(
                f"error while handling tool calls: {e}",
                "error"
            )
