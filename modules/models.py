import asyncio

import core


class Models(core.module.Module):
    """Lets you or the AI switch between AI models.

    By default that's just a config change. With enable_model_load_unload on it
    unloads the previously selected model and loads the target through the llama.cpp
    router instead, so switching works on a VRAM-constrained box.
    """

    settings = {
        "insert_current_model_into_system_prompt": {
            "description": "Whether to make the AI aware of what model it's currently running on. Can help it stay grounded!",
            "default": True
        },
        "insert_available_models_into_system_prompt": {
            "description": "Whether to make the AI aware of what models are available for it to switch to. Allows you to simply ask the AI to switch to whatever model you want (example: `switch to Qwen3.5-9B`) and it'll just do it ",
            "default": False
        },
        "enable_model_load_unload": {
            "type": "boolean",
            "description": "Enable dynamic model loading/unloading via the llama.cpp router. When disabled, /model only changes config.",
            "default": False
        },
        "unload_wait_seconds": {
            "type": "number",
            "description": "Seconds to wait between unloading the old model and loading the new one. Needed for VRAM to clear.",
            "default": 10
        },
    }

    async def on_ready(self):
        self.models = None
        self._switch_lock = asyncio.Lock()

        if self.config.get("insert_available_models_into_system_prompt"):
            self.disabled_tools.append("get_available")

    async def on_system_prompt(self):
        output = ""

        current_model = self.manager.API.get_model()

        if self.config.get("insert_current_model_into_system_prompt"):
            output += f"Current model: {current_model}"

        if self.config.get("enable_model_load_unload"):
            loaded = await self.manager.API.get_loaded_models()
            if isinstance(loaded, core.api.APIError):
                output += f"\n\n(Unable to query loaded models: {loaded})"
            elif loaded:
                output += f"\nCurrently loaded (in VRAM): {', '.join(loaded)}"

        if self.config.get("insert_available_models_into_system_prompt"):
            await self._load_models()
            if self.models and len(self.models) > 1:
                output += f"\n\nModels you can switch to using the models_switch() toolcall: "
                output += ", ".join(self.models)

        return output

    async def _load_models(self):
        if self.models:
            return

        if self.config.get("enable_model_load_unload"):
            models = await self.manager.API.list_router_models()
        else:
            models = await self.manager.API.list_models()

        if not models:
            return None
        if isinstance(models, core.api.APIError):
            return None
        self.models = models

    async def get_available(self):
        """Returns a list of AI/LLM models available to switch to"""
        await self._load_models()

        output = []

        for model in self.models:
            output.append(str(model))

        return self.result(output)

    @core.module.command("model")
    async def model(self, args: list):
         """Switches to model <name>.
         Args:
             args: the model name or empty to show current model
         """
         if not args:
            return f"Current model: {self.manager.API.get_model()}"

         return await self.switch(" ".join(args).strip())

    @core.module.command("models")
    async def models(self, args: list):
        """Lists available models."""
        await self._load_models()
        if not self.models:
            return "Unable to fetch model list."
        return "\n".join(self.models)+"\n\nUse `/model <name>` to switch to your model of choice"

    @core.module.command("model_status")
    async def model_status(self, args: list):
        """Shows currently loaded model(s) and available models."""
        output = []
        current = self.manager.API.get_model()
        output.append(f"Current model (config): {current}")

        if self.config.get("enable_model_load_unload"):
            loaded = await self.manager.API.get_loaded_models()
            if isinstance(loaded, core.api.APIError):
                output.append(f"Currently loaded: unavailable ({loaded})")
            elif loaded:
                output.append(f"Currently loaded (in VRAM): {', '.join(loaded)}")
            else:
                output.append("Currently loaded: none")

        await self._load_models()
        if self.models:
            output.append(f"Available models: {', '.join(self.models)}")
        return "\n".join(output)

    async def switch(self, name: str):
        """Switches you to a different AI model"""
        await self._load_models()

        if not self.models:
            return None

        found = False
        found_id = None
        for model_id in self.models:
            if model_id.strip().lower() == name.strip().lower():
                found = True
                found_id = model_id

        if not found:
            return "model does not exist. use models_get_available() first"

        if self.config.get("enable_model_load_unload"):
            result = await self._switch_with_load_unload(found_id, self.manager.API.get_model())
            if isinstance(result, str):
                return result
            return f"model has been switched to {found_id}"

        core.config.config["model"]["name"] = found_id
        core.config.config.save()

        self.manager.API.set_model(found_id)

        return f"model has been switched to {found_id}"

    async def apply_config_model(self, previous: str = None):
        """Make sure the model in core config is the one loaded in VRAM.

        Called by the web UI after a settings save. previous is the model that
        was active before the change; only unload that one. No-op unless
        enable_model_load_unload is on.
        """
        if not self.config.get("enable_model_load_unload"):
            return None

        target = core.config.get("model", "name")
        if not target:
            return None

        await self._load_models()
        if not self.models:
            return None

        await self._switch_with_load_unload(target, previous)
        return None

    async def _switch_with_load_unload(self, found_id: str, previous: str = None):
        """Unload the previously selected model, wait for VRAM, then load the target."""
        if not previous:
            previous = self.manager.API.get_model()

        async with self._switch_lock:
            loaded = await self.manager.API.get_loaded_models()
            if isinstance(loaded, core.api.APIError):
                self.log(self.name, f"Load/unload unavailable, falling back to config-only switch: {loaded}")
                self._config_only_switch(found_id)
                return f"switched to {found_id} in config only (couldn't reach the router): {loaded}"

            # fast path: the target is already the one sitting in VRAM
            if any(m.strip().lower() == found_id.strip().lower() for m in loaded):
                self._config_only_switch(found_id)
                return None

            unloaded = False
            if previous:
                for m in loaded:
                    if m.strip().lower() == previous.strip().lower():
                        self.log(self.name, f"Unloading previous model: {m}")
                        unload = await self.manager.API.unload_model(m)
                        if isinstance(unload, core.api.APIError):
                            self.log(self.name, f"Failed to unload {m}: {unload}")
                        else:
                            unloaded = True
                        break

            if unloaded:
                wait = self.config.get("unload_wait_seconds") or 10
                if wait > 0:
                    self.log(self.name, f"Waiting {wait} seconds for VRAM to clear...")
                    await asyncio.sleep(wait)

            self.log(self.name, f"Loading model: {found_id}")
            load = await self.manager.API.load_model(found_id)
            if isinstance(load, core.api.APIError):
                self.log(self.name, f"Failed to load {found_id}: {load}. Config updated, VRAM state unknown.")
                self._config_only_switch(found_id)
                return f"switched to {found_id} in config only, load failed: {load}"

            self._config_only_switch(found_id)
            return None

    def _config_only_switch(self, found_id: str):
        core.config.config["model"]["name"] = found_id
        core.config.config.save()
        self.manager.API.set_model(found_id)