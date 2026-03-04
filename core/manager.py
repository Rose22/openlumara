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
        self.API = None # connect later with .connect()
        self.scheduler = core.scheduler.Scheduler()
        self.channels = {}
        self.channel = None # current active channel. gets dynamically switched around
        self.modules = {}
        self.module_instances = {}
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

        return self.API

    async def run(self):
        """main loop"""
        tasks = []

        # start scheduler
        tasks.append(asyncio.create_task(self.scheduler.run()))

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
            tasks.append(asyncio.create_task(channel.run()))
            core.log("init", f"started channel {channel_name}")

        # load modules
        if core.config.get("modules"):
            core.log("init", "loading modules")
            loaded_module_names = []
            for module in modules.get_all():
                # only load enabled modules
                module_name_snakecase = core.modules.get_name(module)
                if module_name_snakecase in core.config.get("modules", []):
                    await self.add_module_class(module)
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
        await asyncio.gather(*tasks)

    async def get_system_prompt(self):
        system_prompt = []

        #W automatically insert system prompts returned by modules (such as memory)
        sysprompt_top = []
        sysprompt_middle = []
        sysprompt_bottom = []
        for module_name, module in self.modules.items():
            module_sysprompt = await module.on_system_prompt()

            if module_sysprompt and (module_name not in core.config.get("modules_disable_prompts", [])):
                prompt_chunk = f"# {' '.join(module_name.split('_')).capitalize()}\n{str(module_sysprompt).strip()}"

                if module_name in ("memory", "identity"):
                    sysprompt_top.append(prompt_chunk)
                elif module_name in ("time", "system"):
                    sysprompt_bottom.append(prompt_chunk)
                else:
                    sysprompt_middle.append(prompt_chunk)

        if self.channel:
            chan = core.module.get_name(self.channel)
            sysprompt_bottom.append(f"current channel: {chan}")

        system_prompt = sysprompt_top+sysprompt_middle+sysprompt_bottom

        if system_prompt:
            prompt_length = len("".join(system_prompt).split())
            prompt_length_text = "System prompt length: {prompt_length} words."
            prompt_length += len(prompt_length_text.split())
            prompt_length_text = prompt_length_text.replace("{prompt_length}", str(prompt_length))

            system_prompt.append(prompt_length_text)

            return "\n\n".join(system_prompt)
        else:
            return ""

    async def get_status(self):
        status_list = []
        status_list.append("== server ==")
        status_list.append("API server: " + str(core.config.get("api_url")))
        if "webui" in core.config.get("channels"):
            status_list.append(f"WebUI: {core.config.get('webui_host')}:{core.config.get('webui_port')}")
        status_list.append("AI model: " + str(core.config.get("model")))

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
        await loaded_module.on_ready()
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
                continue

            # remove "self" arg from func
            del(func_params["self"])

            func_params_translated = {}
            # add method arguments (parameters) to the tool call object
            for param_name, param in func_params.items():
                # translate parameter type name to the correct format
                param_split = str(param).split(":")
                param_name = param_split[0].strip()
                param_type = "str"
                if len(param_split) > 1:
                    param_type = param_split[1].split()[0].strip()

                param_type_map = {
                    "str": "string",
                    "int": "integer",
                    "list": "array",
                    "dict": "object",
                    "bool": "boolean"
                    # TODO: support more types
                }

                for word, replacement in param_type_map.items():
                    if param_type == word:
                        param_type = replacement

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
                        #"required": [key for key in func_params.keys()],
                        "required": [],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            }

            self.tools.append(tool)

    async def handle_tool_calls(self, tool_calls):
        results = []

        # add toolcalls to context
        tools_called = {
            "role": "assistant",
            "tool_calls": [tool_call.to_dict() for tool_call in tool_calls]
        }
        self.API._turns.append(tools_called)

        # call any tool calls based on the stored tool call function
        for tool_call in tool_calls:
            # does the method exist within any of the loaded classes?
            module_instance = None
            for module_name, module_obj in self.modules.items():
                # translate the class name to be like the way it displays to the user
                class_display_name = core.modules.get_name(module_obj)
                # ditto for the function name
                translated_tool_name = str(tool_call.function.name).replace(f"{class_display_name}_", "")

                if hasattr(module_obj, translated_tool_name):
                    # get reference to it from the already instantiated class
                    module_instance = module_obj
                    module_instance_display_name = class_display_name

            if module_instance:
                # use the user-displayed class name to strip the function name of it
                # earlier on we prefixed the name of each tool with the class's display name so that the 
                # LLM knows which class a tool belongs to (e.g. memory_get = MemoryTool class's get() method)
                translated_tool_name = str(tool_call.function.name).replace(f"{module_instance_display_name}_", "")

                # get the class method object
                func_callable = getattr(module_instance, translated_tool_name)

                # format its arguments in a JSON format the llm will understand
                arg_obj = json_repair.loads(tool_call.function.arguments)
                arg_display = []
                for arg_name, arg_value in arg_obj.items():
                    arg_display.append(str(arg_value))
                arg_display = ", ".join(arg_display)
                if len(arg_display) > 100:
                    arg_display = f"{arg_display[:100]}.."
                announce_string = f"calling tool {tool_call.function.name}({arg_display})"
                if self.channel:
                    await self.channel.announce(announce_string)
                else:
                    core.log("toolcall", announce_string)

                # call the class method
                try:
                    func_response = await func_callable(**arg_obj)
                    # and add the method's return value to the LLM's context window as a tool call response
                    tool_response = {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(str(func_response))}
                except Exception as e:
                    core.log("toolcall", f"error: {str(e)}")
                    tool_response = {"role": "tool", "tool_call_id": tool_call.id, "content": f"error: {str(e)}"}

                self.API._turns.append(tool_response)
            else:
                core.log("toolcall", f"tried to call tool {tool_call.function.name} but couldnt find it?!")

        # get user's last request from turns
        user_last_turn = {}
        for turn in self.API._turns:
            if turn.get("role") == "user":
                user_last_turn = turn

        if not self.API.cancel_request:
            prompt = self.API._turns+[{"role": "system", "content": "If the tool response provides sufficient answers, tell the user the results. If not, consider if you need to use another tool? If so, call it."}]
        else:
            if self.channel:
                await self.channel.announce("toolcalling chain cancelled", "info")
            return None

        try:
            return await self.API._recv(
                self.API._request(prompt, tools=self.tools),
                use_tools=True,
                add_turn=False
            )
        except Exception as e:
            core.log_error(f"error while processing tool results", e)
            if self.channel:
                await self.channel.announce(f"error while processing tool results: {e}", "error")
