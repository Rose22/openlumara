import core
import modules
import os
import sys
import platform
import datetime
import asyncio
import json
import json_repair
import inspect
import re

class Manager:
    """the central class that manages everything"""

    # --- main ---
    def __init__(self):
        self._async_tasks = set()
        self.API = None # connect later with .connect()
        self.savedata = core.storage.StorageDict("save", "msgpack")
        self.channels = {}
        self.channel = None # current active channel. gets dynamically switched around
        self.modules = {}
        self.tools = []

    def connect(self, *args, **kwargs):
        args = (self,)+args
        try:
            self.API = core.api_client.APIClient(*args, **kwargs)
        except Exception as e:
            core.log("error", f"error connecting to API: {e}")
            exit(1)

        # Retrieve specific model details
        #model_info = self.API._AI.models.retrieve(model_id)
        # models = self.API._AI.models.list()
        # for model in models.data:
        #     print(model)

        return self.API

    def _remove_async_task(self, task):
        self._async_tasks.discard(task)
        core.log("task", f"background task completed: {task.get_name()}")

    async def run(self):
        """main loop"""
        # load channels
        if not core.config.get("channels"):
            print("ERROR: At least one channel must be enabled in the config! Try the `cli` channel for a basic terminal UI.")
            exit(1)

        core.log("init", "loading channels")
        import channels
        for channel in channels.get_all():
            # only load enabled channels
            channel_name_snakecase = core.modules.get_name(channel)
            if channel_name_snakecase in core.config.get("channels", []):
                chan = channel(self)
                self.channels[channel_name_snakecase] = chan

        # start channels
        for channel_name, channel in self.channels.items():
            self._async_tasks.add(asyncio.create_task(channel.run()))
            core.log("init", f"started channel {channel_name}")

        if not self.channel:
            # attempt to restore last used channel from save data
            last_channel = self.savedata.get("last_channel")
            if last_channel and last_channel in self.channels.keys():
                self.channel = self.channels[last_channel]

        # load modules
        if core.config.get("modules"):
            core.log("init", "loading modules")
            loaded_module_names = []
            for module in modules.get_all():
                # only load enabled modules
                module_name_snakecase = core.modules.get_name(module)
                if module_name_snakecase in core.config.get("modules", []):
                    loaded_module = await self.add_module_class(module)
                    # run startup methods
                    if hasattr(loaded_module, "on_ready"):
                        await loaded_module.on_ready()
                    if hasattr(loaded_module, "on_background"):
                        if not core.module.is_empty_coroutine(loaded_module.on_background):
                            task = asyncio.create_task(loaded_module.on_background(), name=module_name_snakecase)
                            task.add_done_callback(self._remove_async_task)
                            self._async_tasks.add(task)
                            core.log("init", f"started background task {module_name_snakecase}")

                    loaded_module_names.append(module_name_snakecase)
            core.log("init", f"modules loaded: {', '.join(loaded_module_names)}")
        else:
            core.log("init", "all modules disabled in config")

        if not core.config.get("context_window"):
            core.log("init", "context window is disabled")

        print()
        print("\n".join(await self.get_status()))
        print("---\n")

        # run everything
        await asyncio.gather(*self._async_tasks)

    async def get_system_prompt(self):
        nonagentic_modules = ("character", "time")
        system_prompt = []

        #W automatically insert system prompts returned by modules (such as memory)
        sysprompt_top = []
        sysprompt_middle = []
        sysprompt_bottom = []
        for module_name, module in self.modules.items():
            if not core.config.get("tools", False) and module_name not in nonagentic_modules:
                # skip most prompts if tools are turned off
                continue

            module_sysprompt = await module.on_system_prompt()

            if module_sysprompt and (module_name not in core.config.get("modules_disable_prompts", [])):
                # default to module name
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "_header") and module._header:
                    # but allow overriding the header
                    sysprompt_header = module._header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"

                if module_name in ("memory", "identity"):
                    sysprompt_top.append(prompt_chunk)
                elif module_name in ("time", "system"):
                    sysprompt_bottom.append(prompt_chunk)
                else:
                    sysprompt_middle.append(prompt_chunk)

        system_prompt = sysprompt_top+sysprompt_middle+sysprompt_bottom

        if system_prompt:
            return "\n\n".join(system_prompt)
        else:
            return ""

    async def get_end_prompt(self):
        #W automatically insert system prompts returned by modules (such as memory)
        histend_prompt = []
        for module_name, module in self.modules.items():
            module_sysprompt = await module.on_end_prompt()

            if module_sysprompt and (module_name not in core.config.get("modules_disable_end_prompts", [])):
                prompt_chunk = f"# {' '.join(module_name.split('_')).capitalize()}\n{str(module_sysprompt).strip()}"
                histend_prompt.append(prompt_chunk)

        if histend_prompt:
            return "\n\n".join(histend_prompt)
        else:
            return ""

    async def get_status(self):
        status_list = []
        status_list.append("== server ==")
        status_list.append("API server: " + str(core.config.get("api_url")))
        if "webui" in core.config.get("channels"):
            status_list.append(f"WebUI: {core.config.get('webui_host')}:{core.config.get('webui_port')}")
        status_list.append("AI model: " + str(self.API.get_model()))

        status_list.append("")

        status_list.append("== context size ==")
        ctx_string = ""
        context_size = await self.API.get_context_size()
        for key, value in context_size.items():
            ctx_string += f"{key}: {value}\n"
        status_list.append(ctx_string)

        return status_list

    # --- tools ---
    def parse_tool_docstring(self, docstring):
        """
        Parses Google-style docstring to extract param descriptions
        and returns a cleaned docstring without the Args/Returns sections.
        """
        if not docstring:
            return {}, ""

        descriptions = {}
        lines = docstring.split("\n")
        clean_lines = []

        skip_section = False
        section_headers = {"Args:", "Returns:", "Raises:", "Note:", "Example:"}

        for line in lines:
            stripped = line.strip()

            # Check if we're entering a section to skip
            if any(stripped.startswith(header) for header in section_headers):
                skip_section = True
                continue

            # Check if we're still in a skip section (indented line)
            if skip_section:
                # Empty line or unindented line means end of section
                if stripped == "" or (line and not line[0].isspace() and stripped):
                    # But if it's another section header, stay in skip mode
                    if not any(stripped.startswith(h) for h in section_headers):
                        skip_section = False
                        if stripped:
                            clean_lines.append(line)
                continue

            clean_lines.append(line)

        # Now parse Args section separately for descriptions
        in_args = False
        current_param = None
        current_desc = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("Args:"):
                in_args = True
                continue

            if in_args:
                if any(stripped.startswith(h) for h in {"Returns:", "Raises:", "Note:", "Example:"}):
                    if current_param and current_desc:
                        descriptions[current_param] = " ".join(current_desc)
                    break

                if not stripped:
                    continue

                # Match: "param_name: description" or "param_name (type): description"
                match = re.match(r"(\w+)(?:\s*\([^)]*\))?\s*:\s*(.+)", stripped)
                if match:
                    # Save previous param if exists
                    if current_param and current_desc:
                        descriptions[current_param] = " ".join(current_desc)

                    current_param = match.group(1)
                    current_desc = [match.group(2)]
                elif current_param and stripped:
                    # Continuation of previous param description
                    current_desc.append(stripped)

        # Save last param
        if current_param and current_desc:
            descriptions[current_param] = " ".join(current_desc)

        # Clean up the description (remove leading/trailing whitespace, empty lines)
        clean_doc = "\n".join(clean_lines).strip()

        return descriptions, clean_doc

    async def add_module_class(self, module):
        """
        Adds tools to the manager based on a class with functions.
        To make tools, just make a class like so:
        class Mymodule(core.tools.Tools):
            def search_web(query: str):
                self.channel.send(your_websearch(query))
        """

        loaded_module = module(self)

        # create .channel alias in module, always refers to current channel
        # doesnt actually work. will find a solution maybe, for now just use self.manager.channel inside modules
        loaded_module.channel = self.channel

        class_display_name = core.modules.get_name(module)
        self.modules[class_display_name] = loaded_module

        for func_name in dir(module):
            if func_name.startswith("_"):
                # skip private methods and other private properties
                continue

            if func_name == "result" or func_name.startswith("on_"):
                # builtin function
                continue

            try:
                func_obj = getattr(module, func_name)
            except:
                continue

            if not callable(func_obj):
                continue

            # if there's a docstring, make sure to pass that on to the LLM
            docstring = ""
            if "__doc__" in dir(func_obj):
                param_descriptions, docstring = self.parse_tool_docstring(func_obj.__doc__)

            # dynamically load class methods from classes
            func_params = dict(inspect.signature(func_obj).parameters)

            # only get class methods with a self parameter
            if not func_params.get("self"):
                core.log("error", f"class method {func_name} skipped because it didn't have required `self` argument.")
                continue

            # remove "self" arg from func
            del(func_params["self"])

            func_params_translated = {}
            required_args = []
            # add method arguments (parameters) to the tool call object
            for param_name, param in func_params.items():
                # detect the type of a parameter
                param_annotation = param.annotation
                if param_annotation == inspect.Parameter.empty:
                    param_type = "string"
                elif param_annotation == str:
                    param_type = "string"
                elif param_annotation == int:
                    param_type = "integer"
                elif param_annotation == bool:
                    param_type = "boolean"
                elif param_annotation == list:
                    param_type = "array"
                elif param_annotation == dict:
                    param_type = "object"

                # add params without a default value to the required params list
                if param.default == inspect.Parameter.empty:
                    required_args.append(param_name)

                func_params_translated[param_name] = {"type": param_type, "description": param_descriptions.get(param_name)}

            # build toolcall object
            tool = {
                "type": "function",
                "function": {
                    "name": f"{class_display_name}_{func_name}",
                    "description": docstring,
                    "parameters": {
                        "type": "object",
                        "properties": func_params_translated,
                        "required": required_args,
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            }

            self.tools.append(tool)

        return loaded_module

    async def handle_tool_calls(self, tool_calls, use_context=True):
        # 1. Repair JSON and normalize tool calls
        repaired_tool_calls = []
        for tool_call in tool_calls:
            tool_call_dict = tool_call.to_dict()
            raw_args = tool_call_dict['function']['arguments']

            if isinstance(raw_args, dict):
                modified_args = raw_args
            elif isinstance(raw_args, str):
                try:
                    modified_args = json_repair.loads(raw_args)
                except Exception as e:
                    core.log("error", f"JSON repair failed: {e}")
                    modified_args = {}
            else:
                modified_args = {}

            if not isinstance(modified_args, dict):
                modified_args = {}

            tool_call_dict['function']['arguments'] = json.dumps(modified_args)
            repaired_tool_calls.append(tool_call_dict)

        # 2. Append the Assistant Message (with tool_calls) to history
        # This uses our safe insertion logic to prevent Assistant->Assistant errors
        await self.API.insert_message(
            role="assistant",
            content="",
            raw_message={
                "role": "assistant",
                "tool_calls": repaired_tool_calls
            }
        )

        # 3. Execute tools and append results IMMEDIATELY
        for tool_call_dict in repaired_tool_calls:
            tool_name = tool_call_dict['function']['name']
            tool_args = json_repair.loads(tool_call_dict['function']['arguments'])

            # CRITICAL FIX: Extract the ID here for this specific tool call
            tool_call_id = tool_call_dict['id'] 

            # Find the module
            module_instance = None
            module_instance_display_name = None

            for module_name, module_obj in self.modules.items():
                class_display_name = core.modules.get_name(module_obj)
                translated_tool_name = tool_name.replace(f"{class_display_name}_", "")

                if hasattr(module_obj, translated_tool_name):
                    module_instance = module_obj
                    module_instance_display_name = class_display_name
                    break

            if module_instance:
                translated_tool_name = tool_name.replace(f"{module_instance_display_name}_", "")
                func_callable = getattr(module_instance, translated_tool_name)

                # Logging
                arg_display = []
                for key, value in tool_args.items():
                    val_str = str(value)
                    if len(val_str) > 50: val_str = f"{val_str[:50]}.."
                    arg_display.append(f"{key}={val_str}")
                core.log("toolcall", f"calling tool {tool_name}({', '.join(arg_display)})")

                try:
                    func_response = await func_callable(**tool_args)

                    # FIX: Smart serialization to prevent double-quoting or broken JSON
                    if isinstance(func_response, str):
                        # It's already a string, use it directly. Do NOT json.dumps() it again.
                        clean_content = func_response
                    elif isinstance(func_response, (list, dict)):
                        # It's structured data, dump it once to a JSON string
                        clean_content = json.dumps(func_response)
                    else:
                        # Fallback for integers, booleans, etc.
                        clean_content = str(func_response)

                    # Safety: Remove any null bytes or problematic control chars that break parsers
                    clean_content = clean_content.replace('\x00', '')

                    await self.API.insert_message(
                        role="tool_output",
                        content=clean_content,
                        tool_call_id=tool_call_id
                    )
                except Exception as e:
                    core.log("error", f"Tool execution error: {e}")
                    # Even on error, we must return a tool message to close the turn
                    await self.API.insert_message(
                        role="tool_output",
                        content=f"error: {str(e)}",
                        tool_call_id=tool_call_id
                    )
            else:
                core.log("error", f"Module not found for tool: {tool_name}")
                # If tool not found, still need to close the turn to avoid API error
                await self.API.insert_message(
                    role="tool_output",
                    content=f"error: Tool '{tool_name}' not found.",
                    tool_call_id=tool_call_id
                )

        # 5. Check for cancellation
        if self.API.cancel_request:
            if self.channel:
                await self.channel.announce("toolcalling chain cancelled", "info")
            return None

        # 6. Build the prompt for the NEXT turn
        # Now the history ends with: ... -> Assistant(tool_call) -> Tool(result)
        # This is a VALID state for the API to accept a new user/assistant turn.
        prompt = [
            {"role": "system", "content": "If the tool response provides sufficient answers, tell the user the results. If not, consider if you need to use another tool? If so, call it."}
        ] + self.API._messages

        await self.API.trim_messages(num_tokens=self.API.count_tokens_local(prompt))

        try:
            # Send the request. The API will now see a complete tool turn and generate normal text.
            return await self.API._recv(
                await self.API._request(prompt, tools=self.tools),
                use_tools=True,
                add_message=False,
                use_context=use_context
            )
        except Exception as e:
            core.log("error", f"error while handling tool calls: {e}")
            if self.channel:
                await self.channel.announce(f"error while handling tool calls: {e}", "error")
            return None
