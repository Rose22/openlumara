import core

class Models(core.module.Module):
    """Lets you or the AI switch between AI models"""

    settings = {
        "insert_current_model_into_system_prompt": {
            "description" :"Whether to make the AI aware of what model it's currently running on. Can help it stay grounded!",
            "default": True
        },
        "insert_available_models_into_system_prompt": {
            "description": "Whether to make the AI aware of what models are available for it to switch to. Allows you to simply ask the AI to switch to whatever model you want (example: `switch to Qwen3.5-9B`) and it'll just do it ",
            "default": False
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.models = None

        if self.config.get("insert_available_models_into_system_prompt"):
            self.disabled_tools.append("get_available")

    async def on_system_prompt(self):
        output = ""

        if self.config.get("insert_current_model_into_system_prompt"):
            current_model = self.manager.API.get_model()
            output += f"Current model: {current_model}"

        current_model = self.manager.API.get_model()
        
        if self.config.get("insert_available_models_into_system_prompt"):
            if not self.models:
                models = await self.manager.API.list_models()
                if not models:
                    return output if output else None
                self.models = models

            if len(self.models) > 1:
                output += f"\n\nModels you can switch to using the models_switch() toolcall: "
                output += ", ".join(self.models)
        else:
            self._header = "current model"
            output = current_model

        return output

    async def _load_models(self):
        if not self.models:
            models = await self.manager.API.list_models()
            if not models:
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
       0
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
        return "\n".join(self.models)+"\n\nUse `/model <name>` to switch to your model of choice"

    async def switch(self, name: str):
        """Switches you to a different AI model"""
        if not self.models:
            models = await self.manager.API.list_models()
            if not models:
                return None
            self.models = models

        found = False
        found_id = None
        for model_id in self.models:
            if model_id.strip().lower() == name.strip().lower():
                found = True
                found_id = model_id

        if not found:
            return "model does not exist. use models_get_available() first"

        core.config.config["model"]["name"] = found_id
        core.config.config.save()

        self.manager.API.set_model(found_id)

        return f"model has been switched to {found_id}"

