import core

class Models(core.module.Module):
    """Lets you or the AI switch between AI models"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.models = None

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
        return "\n".join(self.models)

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

