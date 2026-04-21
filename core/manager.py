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
import subprocess

class Manager:
    """the central class that manages everything"""

    # --- main ---
    def __init__(self, cmdline_args):
        self._async_tasks = set()
        self.args = cmdline_args # store commandline args
        self.API = core.api_client.APIClient(self) # connect later with .connect()
        self.savedata = {}
        self.channels = {}
        self.channel = None # current active channel. gets dynamically switched around
        self.modules = {}
        self.tools = []
        self.pure_mode = False
        self.coding_mode = False

        self._restart_requested = False

    def _remove_async_task(self, task):
        self._async_tasks.discard(task)
        core.log("task", f"background task completed: {task.get_name()}")

    async def run(self):
        """main loop"""

        if self.args.pure:
            self.pure_mode = True
        elif self.args.coder:
            self.coding_mode = True

        if not core.quiet:
            core.log("core", "Starting OpenLumara")

        self.savedata = core.storage.StorageDict("save", "msgpack")

        # retrieve enabled channels from config
        enabled_channels = core.config.get("channels").get("enabled", [])
        if self.args.cli:
            enabled_channels = ["cli"]

        # retrieve enabled modules from config
        enabled_modules = core.config.get("modules").get("enabled", [])
        enabled_user_modules = core.config.get("user_modules", {}).get("enabled", [])
        loaded_module_names = []

        if self.pure_mode:
            enabled_modules = []
            enabled_user_modules = []
            enabled_user_modules = []
        elif self.coding_mode:
            enabled_modules = ["coder"]
            enabled_user_modules = []

        if not enabled_channels:
            print("ERROR: At least one channel must be enabled in the config! Try the `cli` channel for a basic terminal UI.")
            exit(1)

        core.log("core", "Loading channels")
        import channels
        for channel in core.modules.load(channels, core.channel.Channel, filter=enabled_channels):
            channel_name = core.modules.get_name(channel)
            if channel_name not in enabled_channels:
                continue

            # add an instance of the channel's class to self.channels
            self.channels[channel_name] = channel(self)

        # start channels (execute their .run() method)
        for channel_name, channel in self.channels.items():
            self._async_tasks.add(asyncio.create_task(channel.run()))
            core.log("core", f"Started channel {channel_name}")

        if not self.channel:
            # attempt to restore last used channel from save data
            last_channel = self.savedata.get("last_channel")
            if last_channel and last_channel in self.channels.keys():
                self.channel = self.channels[last_channel]

        if enabled_modules:
            core.log("core", "Loading core modules")

            # load modules
            import modules
            for module in core.modules.load(modules, core.module.Module, filter=enabled_modules):
                if core.modules.get_name(module) not in enabled_modules:
                    continue

                await self.add_module_class(module)
                loaded_module = module(self)
                await loaded_module._start()

                self.modules[loaded_module.name] = loaded_module
                loaded_module_names.append(loaded_module.name)

            # load user modules
            import user_modules
            core.log("core", "Loading user modules")
            for module in core.modules.load(user_modules, core.module.Module, filter=enabled_user_modules):
                if core.modules.get_name(module) not in enabled_user_modules:
                    continue

                loaded_module = await self.add_module_class(module, is_user_module=True)
                await loaded_module._start()

                self.modules[loaded_module.name] = loaded_module
                loaded_module_names.append(loaded_module.name)

            core.log("core", f"Modules loaded: {', '.join(loaded_module_names)}")
        else:
            core.log("core", "all modules disabled in config")

        # Attempt API connection but don't fail if it doesn't work
        await self._initialize_api_connection()

        # run everything
        core.log("core", "Startup complete")

        if "webui" in enabled_channels:
            host = core.config.get("channels").get("settings").get("webui").get("host")
            port = core.config.get("channels").get("settings").get("webui").get("port")
            print()
            print(f"Please open the WebUI at http://{host}:{port}")

        try:
            await asyncio.gather(*self._async_tasks, return_exceptions=False)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            if self._restart_requested:
                return "restart"

            # gracefully shut down
            await self.shutdown()

        return None

    async def restart(self):
        core.log("core", "Restarting server..")
        self._restart_requested = True
        await self.shutdown()

    async def shutdown(self):
        core.log("core", "Shutting down..")

        # shutdown modules
        for module_name, module in self.modules.items():
            if hasattr(module, "on_shutdown"):
                try:
                    if asyncio.iscoroutinefunction(module.on_shutdown):
                        await module.on_shutdown()
                    else:
                        module.on_shutdown()
                except Exception as e:
                    core.log("warning", f"Error shutting down {module_name}: {e}")

        # shutdown channels
        for channel_name, channel in self.channels.items():
            if hasattr(channel, "on_shutdown"):
                core.log("core", f"Shutting down channel {channel_name}")
                try:
                    if asyncio.iscoroutinefunction(channel.on_shutdown):
                        await channel.on_shutdown()
                    else:
                        channel.on_shutdown()
                except Exception as e:
                    core.log("warning", f"Error shutting down {channel_name}: {e}")

        # Cancel all running tasks so gather() returns
        for task in list(self._async_tasks):
            task.cancel()

        core.log("core", "Shutdown complete")

    async def _initialize_api_connection(self):
        """Initialize API connection with user-friendly error handling."""
        core.log("API", "Connecting to AI..")

        connected = await self.API.connect()
        if not connected:
            error = self.API.get_last_error() or "Unknown error"
            core.log("API", f"Failed to connect: {error}")
            core.log("API", "OpenLumara will continue in disconnected mode.")
            core.log("API", "Use the /reconnect command to retry after fixing your configuration.")

    async def reconnect_api(self):
        """Manually trigger API reconnection. Returns status dict."""
        core.log("API", "Attempting to reconnect...")

        connected = await self.API.reconnect()
        if connected:
            core.log("API", "Reconnected successfully")
            return {
                "success": True,
                "message": "Successfully connected to API"
            }
        else:
            error = self.API.get_last_error() or "Unknown error"
            return {
                "success": False,
                "error": error,
                "action": "Please check your API settings and try again."
            }

    def get_api_status(self):
        """Get current API connection status for display."""
        return self.API.get_connection_status()

    async def get_system_prompt(self):
        # Allow generating system prompt even when disconnected
        # (modules may still need to provide context)
        if self.pure_mode:
            return ""

        system_prompt = []

        active_character = None
        if self.channel:
            active_character = await self.channel.context.chat.get_data("character")

        # automatically insert system prompts returned by modules (such as memory)
        sysprompt_top = []
        sysprompt_middle = []
        sysprompt_bottom = []
        for module_name, module in self.modules.items():
            if not core.config.get("model").get("use_tools", False) and module_name not in core.modules.nonagentic:
                # skip most prompts if tools are turned off
                continue

            if active_character and module_name != "characters" and "characters" in self.modules.keys():
                # if a character is currently active, display ONLY the character system prompt
                char_disable_agent_prompts = self.modules["characters"].config.get("disable_agent_prompts_when_character_active")
                if char_disable_agent_prompts:
                    continue

            module_sysprompt = await module.on_system_prompt()

            if module_sysprompt and (module_name not in core.config.get("modules").get("disabled_prompts", [])):
                # default to module name
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "_header") and module._header:
                    # but allow overriding the header
                    sysprompt_header = module._header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"

                if module_name in ("agent_framework_awareness", "identity", "memory"):
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

    async def get_end_prompt(self, prevent_recursion=False):
        # don't return endprompt if characters module is active
        active_character = None
        if self.channel:
            active_character = await self.channel.context.chat.get_data("character")
        if active_character:
            return None

        # automatically insert system prompts returned by modules (such as memory)
        histend_prompt = []
        for module_name, module in self.modules.items():
            if prevent_recursion and module_name == "tokens":
                # if we try to count the system prompt's tokens from the function that counts tokens.. we get recursion
                continue

            if not core.config.get("model").get("use_tools", False) and module_name not in core.modules.nonagentic:
                # skip most prompts if tools are turned off
                continue

            module_sysprompt = await module.on_end_prompt()

            if module_sysprompt and (module_name not in core.config.get("modules").get("disabled_end_prompts", [])):
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "_header") and module._header:
                    # but allow overriding the header
                    sysprompt_header = module._header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"
                histend_prompt.append(prompt_chunk)

        if histend_prompt:
            return "\n\n".join(histend_prompt)
        else:
            return ""

    async def get_status(self):
        status_list = []
        status_list.append("== server ==")

        # API status section
        api_status = self.get_api_status()
        if api_status["connected"]:
            status_list.append("API Status: Connected")
        else:
            status_list.append("API Status: Disconnected")
            if api_status["error"]:
                status_list.append(f"  Error: {api_status['error']}")
            if not api_status["url_configured"]:
                status_list.append("  Warning: API URL not configured")
            if not api_status["key_configured"]:
                status_list.append("  Warning: API key not configured")

        status_list.append("API server: " + str(core.config.get("api").get("url", "Not configured")))
        if "webui" in core.config.get("channels").get("enabled"):
            status_list.append(f"WebUI: {core.config.get('channels').get('settings').get('webui').get('host')}:{core.config.get('channels').get('settings').get('webui').get('port')}")
        status_list.append("AI model: " + str(self.API.get_model() or "Not set"))

        if self.channel is not None:
            status_list.append("")

            status_list.append("== context size ==")
            ctx_string = ""
            context_size = await self.channel.context.get_size()
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

    async def add_module_class(self, module, is_user_module=False):
        """
        Adds tools to the manager based on a class with functions.
        To make tools, just make a class like so:
        class Mymodule(core.tools.Tools):
            def search_web(query: str):
                self.channel.send(your_websearch(query))
        """

        loaded_module = module(self, is_user_module)

        if self.pure_mode:
            return loaded_module

        for func_name in vars(module):
            if func_name.startswith("_"):
                # skip private methods and other private properties
                continue

            if func_name == "result" or func_name.startswith("on_"):
                # builtin function
                continue

            if func_name in loaded_module.disabled_tools:
                continue

            try:
                func_obj = getattr(module, func_name)
            except:
                continue

            if not callable(func_obj):
                continue

            if getattr(func_obj, "_is_command", False):
                # decorated command in a module
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

                func_params_translated[param_name] = {"type": param_type, "description": param_descriptions.get(param_name, "")}

            # build toolcall object
            tool = {
                "type": "function",
                "function": {
                    "name": f"{loaded_module.name}_{func_name}",
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
