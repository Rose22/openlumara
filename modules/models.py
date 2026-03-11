import core

class Models(core.module.Module):
    """switch between AI models"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.models = None

    async def on_system_prompt(self):
        """Returns a list of AI/LLM models available to switch to"""
        if not self.models:
            self.models = await self.manager.API._AI.models.list()
        models_str = ", ".join([model.id for model in self.models.data])
        current_model = self.manager.API.get_model()
        return f"Current model: {current_model}\nModels you can switch to using the models_switch() toolcall: {models_str}"

    @core.module.command("model")
    async def model(self, args: list):
         """switch to model <name>"""
         if not args:
            return f"Current model: {self.manager.API.get_model()}"

         return await self.switch(args[0].strip())

    @core.module.command("models")
    async def models(self, args: list):
        """list models"""

        if not self.models:
            self.models = await self.manager.API._AI.models.list()

        model_list = "\n".join([model.id for model in self.models.data])
        return model_list

    async def switch(self, name: str):
        if not self.models:
            self.models = await self.manager.API._AI.models.list()

        found = False
        found_id = None
        for model in self.models.data:
            if model.id.lower() == name.strip().lower():
                found = True
                found_id = model.id

        if not found:
            return "model does not exist. use models_list() first"

        core.config.config["model"]["name"] = found_id
        core.config.config.save()

        self.manager.API.set_model(found_id)

        return f"model has been switched to {found_id}"

