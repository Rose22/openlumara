import core

class Models(core.module.Module):
    """switch between AI models"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.models = None

    async def on_system_prompt(self):
        """Returns a list of AI/LLM models available to switch to"""
        if not self.models:
            models = await self.manager.API.list_models()
            if not models:
                return None
            self.models = models

        current_model = self.manager.API.get_model()
        if len(self.models) > 1:
            output = f"Current model: {current_model}\nModels you can switch to using the models_switch() toolcall: "
            output += ", ".join(self.models)
        else:
            self._header = "current model"
            output = current_model

        return output

    @core.module.command("model")
    async def model(self, args: list):
         """switch to model <name>"""
         if not args:
            return f"Current model: {self.manager.API.get_model()}"

         return await self.switch(" ".join(args).strip())

    @core.module.command("models")
    async def models(self, args: list):
        """list models"""
        if not self.models:
            models = await self.manager.API.list_models()
            if not models:
                return "Failed to fetch models"
            self.models = models

        return "\n".join(self.models)

    async def switch(self, name: str):
        if not self.models:
            return False

        found = False
        found_id = None
        for model_id in self.models:
            if model_id == name.strip().lower():
                found = True
                found_id = model_id

        if not found:
            return "model does not exist. use models_list() first"

        core.config.config["model"]["name"] = found_id
        core.config.config.save()

        self.manager.API.set_model(found_id)

        return f"model has been switched to {found_id}"

