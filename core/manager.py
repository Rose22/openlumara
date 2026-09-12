import core
import modules
import os
import sys
import datetime
import time
import asyncio
import json_repair
import inspect
import re

global_instance = None

class Manager:
    """the central class that manages everything"""

    # --- main ---
    def __init__(self, cmdline_args):
        self._async_tasks = set()
        self.args = cmdline_args # store commandline args
        self.API = core.api.APIClient(self) # connect later with .connect()
        self.savedata = {}

        self.channels = {}
        self.channel = None # current active channel. gets dynamically switched around

        self.modules = {}
        self.user_modules = {}
        self.broken_modules = [] # tracks modules that threw errors and skips them so that it doesn't break the whole framework

        self.pure_mode = False
        self.coding_mode = False

        self._restart_requested = False
        self._prevent_double_shutdown = False

        self.log_buffer = []
        self.started = False

    # --- tools properties ---
    @property
    def tools(self):
        return self.channel.tool_loader.active_tools if self.channel else []

    @tools.setter
    def tools(self, value):
        if self.channel:
            self.channel.tool_loader.active_tools = value

    @property
    def tool_names(self):
        return self.channel.tool_loader.active_names if self.channel else []

    @tool_names.setter
    def tool_names(self, value):
        if self.channel:
            self.channel.tool_loader.active_names = value

    def _remove_async_task(self, task):
        self._async_tasks.discard(task)
        self.log("task", f"background task completed: {task.get_name()}")

    def log(self, category: str, message: str):
        """propagate the output to every channel"""
        if (
            not self.started
            or
            "cli" not in self.channels.keys()
        ) and not core.quiet:
            cat_str = rf"[{category.upper()}] " if category else ""
            print(f"{cat_str}{message}", flush=True)
            self.log_buffer.append((category, message))
            return

        for name, channel in self.channels.items():
            channel.on_log(category, message)

    def log_error(self, message: str, e: Exception):
        """propagate the output to every channel"""
        for name, channel in self.channels.items():
            channel.log_error(message, e)

    def _drain_log_buffers(self):
        if self.log_buffer:
            for category, message in self.log_buffer:
                for name, channel in self.channels.items():
                    if name == "cli":
                        # skip
                        continue

                    channel.on_log(category, message)

            self.log_buffer.clear()

    async def _load_channels(self, storage, channels, enabled_channels, is_user_channels=False):
        # install dependencies
        newly_installed_channels = []
        if not self.args.disable_auto_installer:
            system_changed = False
            for chan_name in enabled_channels:
                try:
                    await core.modules.install_module_deps(channels, chan_name, self)
                except Exception as e:
                    core.log(chan_name, f"Error while installing channel dependencies: {core.detail_error(e)}")
                    continue

                newly_installed_channels.append(chan_name)

            if newly_installed_channels:
                # reload config
                core.config.load()

        is_user_str = "user " if is_user_channels else ""
        channels_to_load = list(core.modules.load(channels, core.channel.Channel, filter=enabled_channels, reload=True))

        for channel in channels_to_load:
            channel_name = core.modules.get_name(channel)

            # skip loading the CLI channel if we don't have a terminal to output to
            if channel_name == "cli" and not sys.stdout.isatty():
                continue

            # add an instance of the channel's class to self.channels
            try:
                new_chan = channel(self, is_user_channel=is_user_channels)
                await new_chan.init()
            except Exception as e:
                core.log(channel_name, f"Error while loading channel: {core.detail_error(e)}")
                continue

            # run installation hook
            if channel_name in newly_installed_channels:
                try:
                    await new_chan.on_install()
                except Exception as e:
                    core.log(channel_name, f"Error while installing channel: {core.detail_error(e)}")
                    continue

            storage[channel_name] = new_chan
            self.log("core", f"loaded {is_user_str}channel : {channel_name}")

        return True

    async def _load_modules(self, storage, modules, enabled_modules, is_user_modules=False):
        # install dependencies
        newly_installed_modules = []
        if not self.args.disable_auto_installer:
            for mod_name in enabled_modules:
                try:
                    await core.modules.install_module_deps(modules, mod_name, self)
                except Exception as e:
                    core.log(mod_name, f"Error while installing module dependencies: {core.detail_error(e)}")
                    continue

                newly_installed_modules.append(mod_name)

            if newly_installed_modules:
                # reload config
                core.config.load()

        # import/load only the enabled modules
        for module in core.modules.load(modules, core.module.Module, filter=enabled_modules, reload=True):
            loaded_module = await self.add_module_class(module, is_user_module=is_user_modules)

            # run installation hook
            if loaded_module.name in newly_installed_modules:
                try:
                    await loaded_module.on_install()
                except Exception as e:
                    core.log(loaded_module.name, f"Error during module install: {core.detail_error(e)}")
                    continue

            try:
                await loaded_module._start()
            except Exception as e:
                core.log(loaded_module.name, f"Error during module internal _start() method: {core.detail_error(e)}")
                continue

            await self.load_module_tools(loaded_module)

            storage[loaded_module.name] = loaded_module

            is_user_str = "user " if is_user_modules else ""
            self.log("core", f"loaded {is_user_str}module : {loaded_module.name}")

    async def run(self):
        """main loop"""

        startup_timestamp = time.time()

        should_swallow_exceptions = (not core.debug)
        self._prevent_double_shutdown = False

        if self.args.pure:
            self.pure_mode = True
        elif self.args.coder:
            self.coding_mode = True

        if not core.quiet:
            self.log("core", "Starting OpenLumara")

        self.savedata = core.storage.StorageDict("save", "msgpack")

        # retrieve enabled channels from config
        enabled_channels = core.config.get("channels", "enabled", [])
        enabled_user_channels = core.config.get("user_channels", "enabled", [])
        if self.args.cli:
            enabled_channels = ["cli"]
            enabled_user_channels = []

        if (not enabled_channels and not enabled_user_channels):
            print("ERROR: At least one channel must be enabled in the config! Try the `cli` channel for a basic terminal UI.", flush=True)
            exit(1)

        # retrieve enabled modules from config
        enabled_modules = core.config.get("modules", "enabled", [])
        enabled_user_modules = core.config.get("user_modules", "enabled", [])
        loaded_module_names = []

        if self.pure_mode:
            enabled_modules = []
            enabled_user_modules = []
        elif self.coding_mode:
            enabled_modules = ["coder"]
            enabled_user_modules = []

        import channels
        import modules

        if enabled_user_channels:
            import user_channels
        if enabled_user_modules:
            import user_modules

        if not core.quiet:
            self.log("core", "Loading core channels..")
        await self._load_channels(self.channels, channels, enabled_channels)

        if not self.channel:
            # attempt to restore last used channel from save data
            last_channel = self.savedata.get("last_channel")
            if last_channel and last_channel in self.channels.keys():
                self.channel = self.channels[last_channel]
            else:
                target_channel = "cli"
                self.channel = self.channels.get('cli')
                if not self.channel:
                    # just default to the first channel in the list
                    target_channel = enabled_channels[0]
                    self.channel = self.channels.get(target_channel)

                self.savedata["last_channel"] = target_channel
                self.savedata.save()

        if enabled_user_channels:
            self.log("core", "Loading user channels..")
            await self._load_channels(self.channels, user_channels, enabled_user_channels, is_user_channels=True)

        # make our instance accessible even without a reference
        global global_instance
        global_instance = self

        self.log("core", "Loading modules..")
        if enabled_modules:
            await self._load_modules(self.modules, modules, enabled_modules)

        if enabled_user_modules:
            self.log("core", "Loading user modules..")
            await self._load_modules(self.modules, user_modules, enabled_user_modules, is_user_modules=True)

        # If dynamic tool loading is disabled, load all tools at startup
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            self.log("core", "Dynamic tool loading is disabled. Loading all tools at startup.")
            for channel in self.channels.values():
                channel.tool_loader.load_all_tools()
        else:
            # Dynamic loading is on: preload the hardcoded default tools on top
            # of the meta tools so a few frequently-used tools are always ready.
            for channel in self.channels.values():
                # all modules are loaded now: sync the tools_load description
                # with the final list of enabled modules
                channel.tool_loader.refresh_meta_tool_descriptions()
                channel.tool_loader.load_default_tools()
                # Now that the catalog is populated, restore any tools that were
                # persisted in the auto-resumed chat's metadata. During autoload()
                # the catalog was still empty so the initial restore_chat_tools()
                # call in _set_current() couldn't load anything.
                channel.tool_loader.restore_chat_tools()

        if not self.args.disable_auto_installer:
            # uninstall dependencies for disabled modules (only if deps are still installed)
            disabled_channels = core.config.get("channels", "disabled", [])
            disabled_user_channels = core.config.get("user_channels", "disabled", [])
            disabled_modules = core.config.get("modules", "disabled", [])
            disabled_user_modules = core.config.get("user_modules", "disabled", [])

            system_changed = False
            if enabled_channels:
                for chan_name in disabled_channels:
                    uninstalled = await core.modules.uninstall_module_deps(channels, chan_name, self)
                    if uninstalled and not system_changed:
                        system_changed = True

            if enabled_user_channels:
                for chan_name in disabled_user_channels:
                    uninstalled = await core.modules.uninstall_module_deps(user_channels, chan_name, self)
                    if uninstalled and not system_changed:
                        system_changed = True

            if enabled_modules:
                for mod_name in disabled_modules:
                    uninstalled = await core.modules.uninstall_module_deps(modules, mod_name, self)
                    if uninstalled and not system_changed:
                        system_changed = True

            if enabled_user_modules:
                for mod_name in disabled_user_modules:
                    uninstalled = await core.modules.uninstall_module_deps(user_modules, mod_name, self)
                    if uninstalled and not system_changed:
                        system_changed = True

            if system_changed:
                # reload config
                core.config.load()

        elapsed_timestamp = time.time() - startup_timestamp
        self.log("core", f"Startup completed in {elapsed_timestamp:.2f}s")
        self.log("", "-"*40)

        # Attempt API connection but don't fail if it doesn't work
        self.log("API", "Connecting..")

        connected = await self.API.connect()
        if isinstance(connected, core.api.APIError):
            self.log("API", str(connected))

        # start the channels (execute their .run() method)
        for channel_name, channel in self.channels.items():
            if channel_name == "cli":
                # skip so that we can load it as the last one manually at the end
                continue

            self.log("core", f"Starting channel: {channel_name}")

            await channel.on_ready()
            self._async_tasks.add(asyncio.create_task(channel.run()))
            self._async_tasks.add(asyncio.create_task(channel._start_push_queue()))

        # _load_channels() automatically detects if we're in a TTY or not, so if not,
        # cli is not in the channels dict and this will be skipped
        if "cli" in self.channels.keys():
            self.log("core", f"Starting channel: CLI")

            cli_chan = self.channels["cli"]
            await cli_chan.on_ready()
            self._async_tasks.add(asyncio.create_task(cli_chan.run()))
            self._async_tasks.add(asyncio.create_task(cli_chan._start_push_queue()))

        # send all print()'ed logs to the channels as actual log events
        self._drain_log_buffers()

        self.started = True

        try:
            # actually run everything
            await asyncio.gather(*self._async_tasks, return_exceptions=should_swallow_exceptions)
        except KeyboardInterrupt:
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if core.debug:
                import traceback
                traceback.print_exc()
        finally:
            # gracefully shut down
            await self.shutdown()

        if self._restart_requested:
            return "restart"

        return None

    async def restart(self):
        self.log("core", "Restarting server..")
        self._restart_requested = True
        await self.shutdown()

    async def shutdown(self):
        if self._prevent_double_shutdown:
            return False

        # if we call manager.shutdown() somewhere in the framework,
        # stop the automatic shutdown at the end of run() from running
        self._prevent_double_shutdown = True

        self.log("core", "Shutting down..")

        # shutdown modules
        for module_name, module in self.modules.items():
            if hasattr(module, "on_shutdown"):
                try:
                    if asyncio.iscoroutinefunction(module.on_shutdown):
                        await module.on_shutdown()
                    else:
                        module.on_shutdown()
                except Exception as e:
                    self.log_error(f"Error shutting down {module_name}", e)

        # shutdown channels
        for channel_name, channel in self.channels.items():
            if hasattr(channel, "on_shutdown"):
                self.log("core", f"Shutting down channel {channel_name}")

                try:
                    await channel._shutdown()

                    if asyncio.iscoroutinefunction(channel.on_shutdown):
                        await channel.on_shutdown()
                    else:
                        channel.on_shutdown()
                except Exception as e:
                    self.log_error(f"Error shutting down {channel_name}", e)

        # remove the global instance
        global global_instance
        global_instance = None

        # Cancel all running tasks so gather() returns
        for task in list(self._async_tasks):
            try:
                task.cancel()
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.log("warning", f"Error waiting for task {task.get_name()} to finish: {e}")

        # wait so that everything's properly gone
        await asyncio.sleep(1)

        self.started = False
        self.log("core", "Shutdown complete")

    async def toggle_module(self, module_name: str, autorestart=True):
        modules = core.config.config["modules"]
        user_modules = core.config.config["user_modules"]

        toggled = False
        new_state = False

        for module_list in [modules, user_modules]:
            enabled = module_list["enabled"]
            disabled = module_list["disabled"]

            if module_name in enabled:
                enabled.remove(module_name)
                disabled.append(module_name)
                toggled = True
                new_state = False
            elif module_name in disabled:
                disabled.remove(module_name)
                enabled.append(module_name)
                toggled = True
                new_state = True
            else:
                continue

        if toggled:
            core.config.config.save()

            if autorestart:
                if self.channel:
                    await self.channel.push(f"{module_name.capitalize()} module {'enabled' if new_state else 'disabled'}. Restarting to apply change..")
                await asyncio.sleep(0.1)
                await self.channel.manager.restart()

        return toggled

    async def toggle_channel(self, channel_name: str, autorestart=True):
        channels = core.config.config["channels"]
        user_channels = core.config.config["user_channels"]

        toggled = False
        new_state = False

        for channel_list in [channels, user_channels]:
            enabled = channel_list["enabled"]
            disabled = channel_list["disabled"]

            if channel_name in enabled:
                enabled.remove(channel_name)
                disabled.append(channel_name)
                toggled = True
                new_state = False
            elif channel_name in disabled:
                disabled.remove(channel_name)
                enabled.append(channel_name)
                toggled = True
                new_state = True
            else:
                continue

        if toggled:
            core.config.config.save()

            if autorestart:
                if self.channel:
                    await self.channel.push(f"{channel_name.capitalize()} channel {'enabled' if new_state else 'disabled'}. Restarting to apply change..")
                await asyncio.sleep(0.1)
                await self.channel.manager.restart()

        return toggled

    async def reload_module(self, module_name: str):
        """
        Reload a specific module by re-running its setup and re-registering tools.
        """
        if module_name not in self.modules:
            self.log("core", f"Module {module_name} not loaded, cannot reload")
            return False

        module = self.modules[module_name]
        self.log("core", f"Reloading module: {module_name}")

        # remove old tools for this module
        await self.unload_module_tools(module)

        # run the module shutdown hook
        try:
            await module.on_shutdown()
        except Exception as e:
            self.log("core", f"Error running on_shutdown for {module_name}: {core.detail_error(e)}")

        # re-run the module's setup (on_ready usually contains the config-dependent initialization logic)
        try:
            await module.on_ready()
        except Exception as e:
            self.log("core", f"Error running on_ready for {module_name}: {core.detail_error(e)}")
            return False

        # re-add the module tools based on the new state (after on_ready's modifications)
        await self.load_module_tools(module)

        # make sure any hardcoded default tools belonging to this module get re-preloaded
        for channel in self.channels.values():
            channel.tool_loader.load_default_tools()

        return True

    async def get_system_prompt(self):
        # only run on_system_prompt if the manager has a channel reference
        if not self.channel:
            return ""

        if self.pure_mode:
            return ""

        system_prompt = []

        active_character = None
        if self.channel:
            active_character = self.channel.context.chat.get("metadata").get("character")

        # automatically insert system prompts returned by modules (such as memory)
        sysprompt_top = []
        sysprompt_middle = []
        sysprompt_bottom = []

        for module_name, module in self.modules.items():
            if not core.config.get("model").get("use_tools", False) and module_name not in core.modules.nonagentic:
                # skip most prompts if tools are turned off
                continue

            if module_name in self.broken_modules:
                continue

            char_modules_exempt = ["characters"]
            if (
                self.modules.get("writing_style") and
                self.modules.get("characters") and
                self.modules["characters"].config.get("use_writing_style")
            ):
                char_modules_exempt.append("writing_style")

            if active_character and module_name not in char_modules_exempt and "characters" in self.modules.keys():
                # if a character is currently active, display ONLY the character system prompt
                char_disable_agent_prompts = self.modules["characters"].config.get("disable_agent_prompts_when_character_active")

                if char_disable_agent_prompts:
                    continue

            try:
                module_sysprompt = await module.on_system_prompt()
            except Exception as e:
                self.log("module error", f"{module_name}: in on_system_prompt(): {core.detail_error(e)}")
                self.broken_modules.append(module_name)
                continue

            if module_sysprompt and (module_name not in core.config.get("modules").get("disabled_prompts", [])):
                # default to module name
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "header") and module.header:
                    # but allow overriding the header
                    sysprompt_header = module.header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"

                if module_name in ("agent_framework_awareness", "identity", "memory", "writing_style"):
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
        # only run if the manager has a channel reference
        if not self.channel:
            return None

        # don't return endprompt if characters module is active
        active_character = None
        if self.channel:
            active_character = self.channel.context.chat.get("metadata").get("character")

        # automatically insert system prompts returned by modules (such as memory)
        histend_prompt = []
        for module_name, module in self.modules.items():
            if module_name in self.broken_modules:
                continue

            # if a character is active, use only the character module's endprompt
            if active_character and module_name != "characters":
                continue

            if prevent_recursion and module_name == "token_threshold":
                # if we try to count the system prompt's tokens from the function that counts tokens.. we get recursion
                continue

            if not core.config.get("model").get("use_tools", False) and module_name not in core.modules.nonagentic:
                # skip most prompts if tools are turned off
                continue

            try:
                module_sysprompt = await module.on_end_prompt()
            except Exception as e:
                self.log("module error", f"{module_name}: in on_end_prompt(): {core.detail_error(e)}")
                self.broken_modules.append(module_name)
                continue

            if module_sysprompt:
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "header") and module.header:
                    # but allow overriding the header
                    sysprompt_header = module.header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"
                histend_prompt.append(prompt_chunk)

        if histend_prompt:
            return "\n\n".join(histend_prompt)
        else:
            return ""

    async def get_settings_structure(self):
        if not self.modules:
            return {}

        settings_structure = {}
        for name, module in self.modules.items():
            settings_structure[name] = module.settings

        return settings_structure

    # --- tools ---
    async def load_module_tools(self, module):
        """Register a module's tools in the catalog (no longer adds to active set)."""
        for channel in self.channels.values():
            channel.tool_loader.register_module(module)
            # keep the dynamic tools_load description in sync with enabled modules
            channel.tool_loader.refresh_meta_tool_descriptions()

    async def unload_module_tools(self, module):
        """Unregister a module's tools from the catalog and active set."""
        for channel in self.channels.values():
            channel.tool_loader.unregister_module(module)
            channel.tool_loader.refresh_meta_tool_descriptions()
        return True

    async def add_module_class(self, module, is_user_module=False):
        """
        Adds tools to the manager based on a class with functions.
        To make tools, just make a class like so:
        class Mymodule(core.tools.Tools):
            def search_web(query: str):
                self.channel.send(your_websearch(query))
        """

        loaded_module = module(self, is_user_module=is_user_module, channel=self.channel)

        if self.pure_mode:
            return loaded_module

        return loaded_module
